import time
from collections import OrderedDict

from .model import ChannelItem, ProgramItem
from .setup import P
from .source_base import SourceBase, ttl_cache

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
        self.plsess = self.new_session(proxy_url=plproxy, add_headers={"Referer": "https://onair.imbc.com/"})
        # cached playlist url
        self.get_m3u8 = ttl_cache(self.ttl)(self.__get_m3u8)

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
                    ret.append([c.channel_id, c])
                except Exception:
                    logger.exception("라이브 채널 분석 중 예외: %s", item)
        self.channels = OrderedDict(ret)

    def get_data(self, channel_id: str) -> dict:
        path = "OnAirURLUtil" if channel_id == "0" else "OnAirPlusURLUtil"
        now = int(time.time() * 1000)  # timestamp in ms
        url = f"https://mediaapi.imbc.com/Player/{path}?ch={channel_id}&type=PC&t={now}"
        data = self.apisess.get(url).json()
        return data

    def __get_m3u8(self, channel_id: str) -> str:
        if len(channel_id) == 3:  # radio
            url = f"https://sminiplay.imbc.com/aacplay.ashx?channel={channel_id}&protocol=M3U8&agent=webapp"
            return self.apisess.get(url).text
        url = self.get_data(channel_id)["MediaInfo"]["MediaURL"]
        return url.replace("playlist.m3u8", "chunklist.m3u8")

    def repack_m3u8(self, url: str) -> str:
        m3u8 = self.plsess.get(url).text
        return self.sub_ts(m3u8, url.split("chunklist.m3u8")[0])

    def make_m3u8(self, channel_id: str, mode: str, quality: str) -> tuple[str, str]:
        stype = "proxy" if mode == "web_play" else ModelSetting.get("mbc_streaming_type")
        stype = "redirect" if len(channel_id) == 3 else stype
        url = self.get_m3u8(channel_id)
        if stype == "redirect":
            return stype, url
        data = self.repack_m3u8(url)
        if stype == "direct":
            return stype, data
        return stype, self.relay_ts(data, self.source_id, proxy=self.plsess.proxies.get("http"))  # proxy, web_play
