import json
from collections import OrderedDict
from typing import Tuple

from .model import ChannelItem, ProgramItem
from .setup import P
from .source_base import SourceBase, ttl_cache

logger = P.logger
package_name = P.package_name
ModelSetting = P.ModelSetting


class SourceKBS(SourceBase):
    source_id = "kbs"
    ttl = 60 * 60 * 48  # 48시간

    def __init__(self):
        # session for api
        self.apisess = self.new_session()
        # cached playlist url
        self.get_m3u8 = ttl_cache(self.ttl)(self.__get_m3u8)

    def __parse_var(self, text: str, identifiers: Tuple[str, str]) -> dict:
        left = text.find(identifiers[0]) + len(identifiers[0])
        right = text.find(identifiers[1], left)
        return json.loads(text[left:right].replace("\\", ""))

    def get_channel_list(self) -> None:
        ret = []
        include_vod_ch = ModelSetting.get_bool("kbs_include_vod_ch")
        url = "http://onair.kbs.co.kr"
        data = self.apisess.get(url).text
        data = self.__parse_var(data, ("var channelList = JSON.parse('", "');"))
        for channel in data["channel"]:
            for cm in channel["channel_master"]:
                if "_" in cm["channel_code"]:
                    continue  # 지역민방 제외 목적
                if not include_vod_ch and cm["channel_code"].startswith("nvod"):
                    continue
                if cm["channel_type"] == "DMB":
                    continue
                try:
                    p = ProgramItem(image=cm["image_path_video_thumbnail"])
                    c = ChannelItem(
                        self.source_id,
                        cm["channel_code"],
                        cm["title"],
                        cm["image_path_channel_logo"],
                        cm["channel_type"] == "TV",
                        program=p,
                    )
                    ret.append([c.channel_id, c])
                except Exception:
                    logger.exception("라이브 채널 분석 중 예외: %s", cm)
        self.channel_list = OrderedDict(ret)

    def get_data(self, channel_id: str) -> dict:
        tmp = f"https://cfpwwwapi.kbs.co.kr/api/v1/landing/live/channel_code/{channel_id}"
        return self.apisess.get(tmp).json()

    def __get_m3u8(self, channel_id: str) -> str:
        url = self.get_data(channel_id)["channel_item"][0]["service_url"]
        self.expires_in(url)  # debug
        return url

    def get_url(self, channel_id: str, mode: str, quality: str = None) -> str:
        return "redirect", self.get_m3u8(channel_id)
