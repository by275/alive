import json
from collections import OrderedDict

from support import SupportSC  # type: ignore # pylint: disable=import-error

from .model import ChannelItem
from .setup import P
from .source_base import SourceBase

logger = P.logger
package_name = P.package_name
ModelSetting = P.ModelSetting

BASE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3",
    "Origin": "https://www.spotvnow.co.kr",
}

CHANNELS = json.loads(
    SupportSC.decode(
        "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"
    )
)


class SourceSpotv(SourceBase):
    source_id = "spotv"

    def load_channels(self) -> None:
        ret = []
        for cid, channel in CHANNELS.items():
            c = ChannelItem(self.source_id, cid, channel["name"], channel["icon"], True, True)
            ret.append(c)
        self.channels = OrderedDict((c.channel_id, c) for c in ret)

    def make_m3u8(self, channel_id: str, mode: str, quality: str) -> tuple[str, str | dict]:
        channel = CHANNELS[channel_id]
        if mode == "web_play":
            return "drm+web", {
                "src": channel["uri"],
                "type": "application/x-mpegurl",
                "keySystems": {
                    "com.widevine.alpha": {
                        "url": "/alive/proxy/license",
                        "licenseHeaders": {
                            "Real-Url": channel["drm_license_uri"],
                            "Real-Origin": BASE_HEADERS["Origin"],
                            "Real-Referer": channel["referer"],
                        },
                        "persistentState": "required",
                    }
                },
            }
        if mode == "kodi":
            text = f"""#KODIPROP:inputstream=inputstream.adaptive
#KODIPROP:inputstream.adaptive.license_type=com.widevine.alpha
#KODIPROP:inputstream.adaptive.license_key={channel['drm_license_uri']}
#KODIPROP:inputstream.adaptive.stream_headers=Origin={BASE_HEADERS['Origin']}&User-Agent={BASE_HEADERS['User-Agent']}&Referer={channel['referer']}
{channel['uri']}"""
            return "drm+kodi", text
        return "drm", {
            "uri": channel["uri"],
            "drm_scheme": "widevine",
            "drm_license_uri": channel["drm_license_uri"],
            "drm_key_request_properties": {
                "origin": BASE_HEADERS["Origin"],
                "user-agent": BASE_HEADERS["User-Agent"],
                "referer": channel["referer"],
            },
        }
