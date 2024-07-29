import json
from collections import OrderedDict
from typing import Tuple

from .model import ChannelItem
from .setup import P
from .source_base import SourceBase

logger = P.logger
package_name = P.package_name
ModelSetting = P.ModelSetting


class SourceFixURL(SourceBase):
    source_id = "fix_url"

    def load_channels(self) -> None:
        ret = []
        for item in map(str.strip, ModelSetting.get(f"{self.source_id}_list").splitlines()):
            if not item:
                continue
            tmp = item.split("|")
            if len(tmp) < 4:
                continue
            try: cid, cname, url, radio_yn = tmp
            except: cid, cname, url, radio_yn, _ = tmp
            c = ChannelItem(self.source_id, cid, cname, None, radio_yn == "Y", not url.startswith('http'))
            c.url = url
            ret.append([c.channel_id, c])
        self.channels = OrderedDict(ret)

    def get_m3u8(self, channel_id: str) -> str:
        return self.channels[channel_id].url

    def make_m3u8(self, channel_id: str, mode: str, quality: str) -> Tuple[str, str]:
        url = self.get_m3u8(channel_id)
        if mode == "web_play":
            # 매우 좋지 않지만 spotv만 .....
            if url.startswith("{") and "spotvnow" in url:
                info = json.loads(url)
                ret = {
                    "src": info["uri"],
                    "type": "application/x-mpegurl",
                    "keySystems": {
                        "com.widevine.alpha": {
                            "url": "/alive/license",
                            "licenseHeaders": {
                                "Real-Url": info["drm_license_uri"],
                                "Real-Origin": info["drm_key_request_properties"]["origin"],
                                "Real-Referer": info["drm_key_request_properties"]["referer"],
                            },
                            "persistentState": "required",
                        }
                    },
                }
                return None, ret

        return "redirect", url
