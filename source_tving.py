import re
from collections import OrderedDict

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
    ttl = 60 * 60 * 3  # 3시간
    default_quality: str = ModelSetting.get("tving_quality")

    PTN_BANDWIDTH = re.compile(r"BANDWIDTH=(\d+)", re.MULTILINE)
    PTN_HTTP = re.compile(r"^http:\/\/")

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

    def upgrade_http(self, d):
        """in-place replacement of http urls in data"""
        if isinstance(d, (dict, list)):
            for k, v in d.items() if isinstance(d, dict) else enumerate(d):
                if isinstance(v, str) and v.startswith("http://"):
                    d[k] = self.PTN_HTTP.sub("https://", d[k])
                self.upgrade_http(v)

    def __get_m3u8(self, channel_id: str, quality: str) -> str | dict:
        data = self.get_data(channel_id, quality)
        self.upgrade_http(data)
        if self.mod.is_drm_channel(channel_id):
            del data["play_info"]["mpd_headers"]
            return data["play_info"]
        data = self.plsess.get(url := data["url"]).text  # root playlist
        max_bandwidth = max(map(int, self.PTN_BANDWIDTH.findall(data)))
        return url.replace("playlist.m3u8", f"chunklist_b{max_bandwidth}.m3u8")

    def repack_m3u8(self, url: str) -> str:
        data = self.plsess.get(url).text
        data = self.sub_ts(data, url.split("chunklist_")[0], url.split(".m3u8")[1])
        return data

    def make_drm(self, data: dict, mode: str) -> tuple[str, dict]:
        if mode == "web_play":
            return "drm+web", {
                "src": data["uri"],
                "type": "application/dash+xml",
                "keySystems": {
                    "com.widevine.alpha": {
                        "url": "/alive/license",
                        "licenseHeaders": {
                            "Real-Url": data["drm_license_uri"],
                            "Real-Origin": data["drm_key_request_properties"]["origin"],
                            "Real-Referer": data["drm_key_request_properties"]["referer"],
                            "Pallycon-Customdata-V2": data["drm_key_request_properties"]["pallycon-customdata-v2"],
                        },
                        "persistentState": "required",
                    }
                },
            }
        return "drm", data

    def make_m3u8(self, channel_id: str, mode: str, quality: str) -> tuple[str, str | dict]:
        url = self.get_m3u8(channel_id, quality)
        if self.mod.is_drm_channel(channel_id):
            return self.make_drm(url, mode)
        stype = "proxy" if mode == "web_play" else "direct"
        data = self.repack_m3u8(url)
        if stype == "direct":
            return stype, data
        return stype, self.relay_ts(data, self.source_id)  # proxy, web_play
