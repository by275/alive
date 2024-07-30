import json
from collections import OrderedDict

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
            cid, cname, url, radio_yn = tmp[:4]
            c = ChannelItem(self.source_id, cid, cname, None, radio_yn == "Y", not url.startswith("http"))
            c.url = url
            ret.append([c.channel_id, c])
        self.channels = OrderedDict(ret)

    def get_m3u8(self, channel_id: str) -> str:
        return self.channels[channel_id].url

    def make_drm(self, data: dict, mode: str) -> tuple[str, dict]:
        if mode == "web_play":
            return "drm+web", {
                "src": data["uri"],
                "type": "application/x-mpegurl",
                "keySystems": {
                    "com.widevine.alpha": {
                        "url": "/alive/license",
                        "licenseHeaders": {
                            "Real-Url": data["drm_license_uri"],
                            "Real-Origin": data["drm_key_request_properties"]["origin"],
                            "Real-Referer": data["drm_key_request_properties"]["referer"],
                        },
                        "persistentState": "required",
                    }
                },
            }
        return "drm", data

    def make_m3u8(self, channel_id: str, mode: str, quality: str) -> tuple[str, str | dict]:
        url = self.get_m3u8(channel_id)
        if self.channels[channel_id].is_drm:
            # 매우 좋지 않지만 spotv만 .....
            return self.make_drm(json.loads(url), mode)
        return "redirect", url
