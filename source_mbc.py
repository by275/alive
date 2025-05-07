import time
from collections import OrderedDict

from .model import ChannelItem, ProgramItem
from .setup import P
from .source_base import SourceBase, URLCacher

logger = P.logger
package_name = P.package_name
ModelSetting = P.ModelSetting


class SourceMBC(SourceBase):
    source_id = "mbc"
    code = {
        "MBC": "0",
        "P_everyone": "2",
        "P_drama": "1",
        "P_music": "3",
        "P_on": "6",
        "P_allthekpop": "4",
        "FM": "sfm",
        "FM4U": "mfm",
        "ALLTHAT": "chm",
    }
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
        url = "https://control.imbc.com/Schedule/PCONAIR"
        data = self.apisess.get(url).json()
        for cate in ["TVList", "RadioList"]:
            for item in data[cate]:
                if item["ScheduleCode"] not in self.code:
                    continue
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
                        self.code[item["ScheduleCode"]],
                        item["TypeTitle"],
                        None,
                        cate == "TVList",
                        program=p,
                    )
                    ret.append(c)
                except Exception:
                    logger.exception("라이브 채널 분석 중 예외: %s", item)
        self.channels = OrderedDict((c.channel_id, c) for c in ret)

    def get_data(self, channel_id: str) -> dict:
        path = "OnAirURLUtil" if channel_id == "0" else "OnAirPlusURLUtil"
        now = int(time.time() * 1000)  # timestamp in ms
        url = f"https://mediaapi.imbc.com/Player/{path}?ch={channel_id}&type=PC&t={now}"
        data = self.apisess.get(url).json()
        return data

    def __get_url(self, channel_id: str) -> str:
        if not self.channels[channel_id].is_tv:  # radio
            url = f"https://sminiplay.imbc.com/aacplay.ashx?channel={channel_id}&protocol=M3U8&agent=webapp"
            return self.apisess.get(url).text
        return self.get_data(channel_id)["MediaInfo"]["MediaURL"]

    def make_m3u8(self, channel_id: str, mode: str, quality: str) -> tuple[str, str]:
        url = self.get_url(channel_id)
        if not self.channels[channel_id].is_tv:
            return "redirect", url
        stype = "proxy"  # chunk를 받아올 때도 referer가 필요하기 때문에 proxy만 가능
        return stype, self.get_m3u8(url)
