import re
from collections import OrderedDict
from typing import Tuple

from .model import ChannelItem, ProgramItem
from .setup import P
from .source_base import SourceBase, ttl_cache

logger = P.logger
package_name = P.package_name
ModelSetting = P.ModelSetting

quality_map = {
    "SD": "480p",
    "HD": "720p",
    "FHD": "1080p",
    "UHD": "2160p",
}


class SourceTving(SourceBase):
    source_id = "tving"
    mod = None
    ttl = 60 * 60 * 24  # 1일
    default_quality: str = ModelSetting.get("tving_quality")

    PTN_BANDWIDTH = re.compile(r"BANDWIDTH=(\d+)", re.MULTILINE)

    def __init__(self):
        if self.mod is not None:
            return
        try:
            self.mod = self.load_support_module()
        except (ImportError, ModuleNotFoundError):
            logger.error("support site 플러그인이 필요합니다.")
        except Exception:
            logger.exception("Support Module 로딩 중 예외:")
        if self.mod is None:
            return
        # session for playlists
        self.plsess = self.new_session(
            headers=self.mod._SupportTving__headers,
            proxies=self.mod._SupportTving__proxies,
        )
        # cached playlist url
        self.get_m3u8 = ttl_cache(self.ttl)(self.__get_m3u8)

    def load_support_module(self):
        from support_site import SupportTving as ST

        token = ST._SupportTving__token.strip()  # pylint: disable=protected-access
        if not token:
            logger.error("티빙 토큰이 필요합니다.")
            return None
        return ST

    def load_channels(self) -> None:
        ret = []
        data = self.mod.get_live_list(list_type="live", include_drm=P.ModelSetting.get_bool("tving_include_drm"))
        for item in data:
            try:
                p = ProgramItem(title=item["episode_title"], onair=not item.get("block", False))
                c = ChannelItem(
                    self.source_id,
                    item["id"],
                    item["title"],
                    item["img"],
                    True,
                    is_drm=item["is_drm"],
                    program=p,
                )
                ret.append([c.channel_id, c])
            except Exception:
                logger.exception("라이브 채널 분석 중 예외: %s", item)
        self.channels = OrderedDict(ret)

    def get_data(self, channel_id: str, quality: str) -> dict:
        if quality in [None, "default"]:
            quality = self.default_quality
        quality = quality_map.get(quality, "stream50")
        return self.mod.get_info(channel_id, quality)

    def __get_m3u8(self, channel_id: str, quality: str) -> str:
        data = self.get_data(channel_id, quality)
        if not self.mod.is_drm_channel(channel_id):
            data = self.plsess.get(url := data["url"]).text  # root playlist
            max_bandwidth = max(map(int, self.PTN_BANDWIDTH.findall(data)))
            return url.replace("playlist.m3u8", f"chunklist_b{max_bandwidth}.m3u8")
        else:
            del data["play_info"]["mpd_headers"]
            return data["play_info"]

    def repack_m3u8(self, url: str) -> str:
        data = self.plsess.get(url).text
        data = self.sub_ts(data, url.split("chunklist_")[0], url.split(".m3u8")[1])
        return data

    def make_m3u8(self, channel_id: str, mode: str, quality: str) -> Tuple[str, str]:
        stype = "proxy" if mode == "web_play" else "direct"
        url = self.get_m3u8(channel_id, quality)
        if not self.mod.is_drm_channel(channel_id):
            data = self.repack_m3u8(url)
            if stype == "direct":
                return stype, data
            return stype, self.relay_ts(data, self.source_id)  # proxy, web_play
        else:
            if mode == "web_play":
                ret = {
                    "src": url["uri"],
                    "type": "application/dash+xml",
                    "keySystems": {
                        "com.widevine.alpha": {
                            "url": "/alive/license",
                            "licenseHeaders": {
                                "Real-Url": url["drm_license_uri"],
                                "Real-Origin": url["drm_key_request_properties"]["origin"],
                                "Real-Referer": url["drm_key_request_properties"]["referer"],
                                "Pallycon-Customdata-V2": url["drm_key_request_properties"]["Pallycon-Customdata-V2"],
                            },
                            "persistentState": "required",
                        }
                    },
                }
                return stype, ret
            else:
                return stype, url
