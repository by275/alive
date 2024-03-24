import time
from collections import OrderedDict
from typing import Tuple

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
        self.apisess = self.new_session(add_headers={"Referer": "https://onair.imbc.com/"})
        # session for playlists
        self.plsess = self.new_session()
        # cached playlist url
        self.get_playlist = ttl_cache(self.ttl)(self.__get_playlist)

    def get_channel_list(self) -> None:
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
        self.channel_list = OrderedDict(ret)

    def get_data(self, channel_id: str) -> dict:
        path = "OnAirURLUtil" if channel_id == "0" else "OnAirPlusURLUtil"
        url = f"https://mediaapi.imbc.com/Player/{path}?ch={channel_id}&type=PC&t={int(time.time())}"
        data = self.apisess.get(url).json()
        return data

    def __get_playlist(self, channel_id: str) -> str:
        url = self.get_data(channel_id)["MediaInfo"]["MediaURL"]
        return url.replace("playlist.m3u8", "chunklist.m3u8")

    def get_url(self, channel_id: str, mode: str, quality: str = None) -> Tuple[str, str]:
        if len(channel_id) == 3:  # radio
            url = f"https://sminiplay.imbc.com/aacplay.ashx?channel={channel_id}&protocol=M3U8&agent=webapp"
            data = self.apisess.get(url).text
            return "redirect", data
        return "return_after_read", self.get_playlist(channel_id)

    def repack_playlist(self, url: str, mode: str = None) -> str:
        data = self.plsess.get(url).text
        return self.sub_ts(data, url.split("chunklist.m3u8")[0])
