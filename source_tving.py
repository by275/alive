import re
from collections import OrderedDict
from pathlib import Path
from typing import Tuple

from support import SupportSC  # pylint: disable=import-error

from .model import ChannelItem, ProgramItem
from .setup import P
from .source_base import SourceBase, ttl_cache

logger = P.logger
package_name = P.package_name
ModelSetting = P.ModelSetting


class SourceTving(SourceBase):
    source_id = "tving"
    mod = None
    ttl = 60 * 60 * (24 - 1)  # 1일

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
        self.plsess = self.new_session(headers=self.mod.headers, proxies=self.mod.proxies)
        # cached playlist url
        self.get_playlist = ttl_cache(self.ttl)(self.__get_playlist)

    def load_support_module(self):
        from support_site.setup import P as SS

        token = SS.ModelSetting.get("site_tving_token").strip()
        if not token:
            logger.error("티빙 토큰이 필요합니다.")
            return None
        proxy = None
        if SS.ModelSetting.get_bool("site_tving_use_proxy"):
            proxy = SS.ModelSetting.get("site_tving_proxy_url")
        deviceid = SS.ModelSetting.get("site_tving_deviceid")

        if Path(__file__).with_name("tving.py").is_file():
            from .tving import SupportTving

            return SupportTving(token=token, proxy=proxy, deviceid=deviceid)
        return SupportSC.load_module_f(__file__, "tving").SupportTving(token=token, proxy=proxy, deviceid=deviceid)

    def get_channel_list(self) -> None:
        ret = []
        data = self.mod.get_live_list(list_type="live", include_drm=ModelSetting.get_bool("tving_include_drm"))
        for item in data:
            try:
                p = ProgramItem(title=item["episode_title"], onair=not item["block"])
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
        self.channel_list = OrderedDict(ret)

    def get_data(self, channel_id: str, quality: str) -> dict:
        quality = self.mod.get_quality_to_tving(quality)
        return self.mod.get_info(channel_id, quality)

    def __get_playlist(self, channel_id: str, quality: str) -> str:
        data = self.get_data(channel_id, quality)
        data = self.plsess.get(url := data["url"]).text  # root playlist
        max_bandwidth = max(map(int, self.PTN_BANDWIDTH.findall(data)))
        return url.replace("playlist.m3u8", f"chunklist_b{max_bandwidth}.m3u8")

    def get_url(self, channel_id: str, mode: str, quality: str = None) -> Tuple[str, str]:
        if self.mod.is_drm_channel(channel_id):
            # FIXME
            raise ValueError("DRM 채널은 현재 지원되지 않습니다.")
        return "return_after_read", self.get_playlist(channel_id, quality)

    def repack_playlist(self, url: str, mode: str = None) -> str:
        data = self.plsess.get(url).text
        data = self.sub_ts(data, url.split("chunklist_")[0], url.split(".m3u8")[1])
        if mode == "web_play":  # CORS issue
            return self.relay_segments(data)
        return data
