import time
from collections import OrderedDict
from datetime import datetime

from .model import ChannelItem, ProgramItem
from .setup import P
from .source_base import SourceBase, URLCacher

logger = P.logger
package_name = P.package_name
ModelSetting = P.ModelSetting

CODE_MAP = {  # maps ScheduleCode to channel id
    "MBC": "0",
    "P_everyone": "2",
    "P_drama": "1",
    "P_music": "3",
    "P_on": "6",
    "MBCNET": "17",
    "FM": "sfm",
    "FM4U": "mfm",
    "ALLTHAT": "chm",
}


class SourceMBC(SourceBase):
    source_id = "mbc"
    ttl = 180  # 3분

    def __init__(self):
        # session for api
        proxy_url = ModelSetting.get("mbc_proxy_url") if ModelSetting.get_bool("mbc_use_proxy") else None
        self.apisess = self.new_session(proxy_url=proxy_url, add_headers={"Referer": "https://onair.imbc.com/"})
        # session for playlists
        plproxy = proxy_url if ModelSetting.get_bool("mbc_use_proxy_for_playlist") else None
        self.plsess = SourceBase.new_session(proxy_url=plproxy, add_headers={"Referer": "https://onair.imbc.com/"})
        # caching master playlist url
        self.get_url = URLCacher(self.ttl)(self.__get_url)

    def load_channels(self) -> None:
        ret = []
        now = datetime.now()
        t = f"{now.day}{now.hour}{now.minute}"
        url = f"https://control.imbc.com/Schedule/ONAIRWITHNVOD?t={t}"
        data = self.apisess.get(url).json()
        for item in data:
            try:
                p = ProgramItem(
                    title=item["Title"],
                    image=item["OnAirImage"],
                    stime=item["FullStartTime"],
                    etime=item["FullEndTime"],
                    targetage=int(item["TargetAge"] or "0"),
                    onair=item["IsOnAirNow"] is None or bool(item["IsOnAirNow"]),
                )
                c = ChannelItem(
                    self.source_id,
                    CODE_MAP[item["ScheduleCode"]],
                    item["TypeTitle"],
                    None,
                    item["Type"] != "RADIO",
                    program=p,
                )
                ret.append(c)
            except Exception:
                logger.exception("라이브 채널 분석 중 예외: %s", item)
        self.channels = OrderedDict((c.channel_id, c) for c in ret)

    def get_data(self, channel_id: str) -> dict:
        mapping = {
            "0": f"OnAirURLUtil?ch={channel_id}",  # MBC
            "17": f"NVodURLUtil?chid={channel_id}",  # MBCNET
        }
        path = mapping.get(channel_id, f"OnAirPlusURLUtil?ch={channel_id}")

        now = int(time.time() * 1000)
        url = f"https://mediaapi.imbc.com/Player/{path}&type=PC&t={now}"
        data = self.apisess.get(url).json()
        if channel_id == "17":
            return data
        return data["MediaInfo"]

    def __get_url(self, channel_id: str) -> str:
        if not self.channels[channel_id].is_tv:  # radio
            url = f"https://sminiplay.imbc.com/aacplay.ashx?channel={channel_id}&protocol=M3U8&agent=webapp"
            return self.apisess.get(url).text
        return self.get_data(channel_id)["MediaURL"]

    def make_m3u8(self, channel_id: str, mode: str, quality: str) -> tuple[str, str | dict]:
        url = self.get_url(channel_id)
        if not self.channels[channel_id].is_tv:
            return "redirect", url
        stype = "proxy"  # chunk를 받아올 때도 referer가 필요하기 때문에 proxy만 가능
        return stype, self.get_m3u8(url)
