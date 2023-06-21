import re
from pathlib import Path

import requests

from support import SupportSC

# local
from .model import ChannelItem
from .setup import P
from .source_base import SourceBase

logger = P.logger
package_name = P.package_name
ModelSetting = P.ModelSetting


class SourceTving(SourceBase):
    source_id = "tving"
    mod = None

    def __init__(self):
        if self.mod is not None:
            return
        try:
            self.mod = self.load_support_module()
        except (ImportError, ModuleNotFoundError):
            logger.error("support site 플러그인이 필요합니다.")
        except Exception:
            logger.exception("Support Module 로딩 중 예외:")

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

        if Path(__file__).parent.joinpath("tving.py").is_file():
            from .tving import SupportTving

            return SupportTving(token=token, proxy=proxy, deviceid=deviceid)
        return SupportSC.load_module_f(__file__, "tving").SupportTving(token=token, proxy=proxy, deviceid=deviceid)

    def get_channel_list(self):
        ret = []
        data = self.mod.get_live_list(list_type="live", include_drm=ModelSetting.get_bool("tving_include_drm"))
        for item in data:
            c = ChannelItem(self.source_id, item["id"], item["title"], item["img"], True)
            if item["is_drm"]:
                c.is_drm_channel = True
            c.current = item["episode_title"]
            ret.append(c)
        return ret

    def get_url(self, channel_id, mode, quality=None):
        quality = self.mod.get_quality_to_tving(quality)
        data = self.mod.get_info(channel_id, quality)
        if self.mod.is_drm_channel(channel_id):
            return data
        return "return_after_read", data["url"]

    def get_return_data(self, url, mode=None):
        data = requests.get(url, timeout=30).text
        matches = re.finditer(r"BANDWIDTH=(?P<bandwidth>\d+)", data, re.MULTILINE)
        max_bandwidth = 0
        for match in matches:
            bw = int(match.group("bandwidth"))
            if bw > max_bandwidth:
                max_bandwidth = bw

        temp = url.split("playlist.m3u8")
        url1 = f"{temp[0]}chunklist_b{max_bandwidth}.m3u8{temp[1]}"
        data1 = requests.get(url1, timeout=30).text
        data1 = data1.replace("media", f"{temp[0]}media").replace(".ts", f".ts{temp[1]}")
        if mode == "web_play":
            data1 = self.change_redirect_data(data1)
        return data1
