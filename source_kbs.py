import json
from collections import OrderedDict

from .model import ChannelItem, ProgramItem
from .setup import P
from .source_base import SourceBase, URLCacher

logger = P.logger
package_name = P.package_name
ModelSetting = P.ModelSetting


class SourceKBS(SourceBase):
    source_id = "kbs"
    ttl = 60 * 60 * 48  # 48시간

    def __init__(self):
        # session for api
        proxy_url = ModelSetting.get("kbs_proxy_url") if ModelSetting.get_bool("kbs_use_proxy") else None
        self.apisess = self.new_session(proxy_url=proxy_url)
        # session for playlists
        plproxy = proxy_url if ModelSetting.get_bool("kbs_use_proxy_for_playlist") else None
        self.plsess = self.new_session(proxy_url=plproxy, add_headers={"Referer": "https://onair.kbs.co.kr"})
        # cached playlist url
        self.get_url = URLCacher(self.ttl)(self.__get_url)

    def __parse_var(self, text: str, identifiers: tuple[str, str]) -> dict:
        left = text.find(identifiers[0]) + len(identifiers[0])
        right = text.find(identifiers[1], left)
        return json.loads(text[left:right].replace("\\", ""))

    def load_channels(self) -> None:
        ret = []
        include_vod_ch = ModelSetting.get_bool("kbs_include_vod_ch")
        url = "https://onair.kbs.co.kr"
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
                    ret.append(c)
                except Exception:
                    logger.exception("라이브 채널 분석 중 예외: %s", cm)
        self.channels = OrderedDict((c.channel_id, c) for c in ret)

    def get_data(self, channel_id: str) -> dict:
        tmp = f"https://cfpwwwapi.kbs.co.kr/api/v1/landing/live/channel_code/{channel_id}"
        return self.apisess.get(tmp).json()

    def __get_url(self, channel_id: str) -> str:
        url = self.get_data(channel_id)["channel_item"][0]["service_url"]
        if "dokdo" in url:  # 독도
            url = url.replace("playlist.m3u8", "chunklist.m3u8")
        return url

    def make_m3u8(self, channel_id: str, mode: str, quality: str) -> tuple[str, str]:
        stype = ModelSetting.get("kbs_streaming_type")
        url = self.get_url(channel_id)
        if stype == "redirect":
            return stype, url
        return stype, self.repack_m3u8(url, stype)  # direct, proxy
