import json
from collections import OrderedDict

from .model import ChannelItem
from .setup import P
from .source_base import SourceBase

logger = P.logger
package_name = P.package_name
ModelSetting = P.ModelSetting


class SourceSpotv(SourceBase):
    source_id = "spotv"

    def load_channels(self) -> None:
        ret = []
        for id, channel in CHANNELS.items():
            c = ChannelItem(self.source_id, id, channel["name"], channel["icon"], True, True)
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
        elif mode == "kodi":
            text = f"""#KODIPROP:inputstream=inputstream.adaptive
#KODIPROP:inputstream.adaptive.license_type=com.widevine.alpha
#KODIPROP:inputstream.adaptive.license_key={channel['drm_license_uri']}
#KODIPROP:inputstream.adaptive.stream_headers=Origin={BASE_HEADERS['Origin']}&User-Agent={BASE_HEADERS['User-Agent']}&Referer={channel['referer']}
{channel['uri']}"""
            return "m3u8", text
        else:
            data = {
                "uri": channel["uri"],
                "drm_scheme": "widevine",
                "drm_license_uri": channel["drm_license_uri"],
                "drm_key_request_properties": {
                    "origin": BASE_HEADERS["Origin"],
                    "user-agent": BASE_HEADERS["User-Agent"],
                    "referer": channel["referer"],
                },
            }
            return "drm", data

    
BASE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3",
    "Origin": "https://www.spotvnow.co.kr",
}

CHANNELS = {
    "spotv": {
        "id": "spotv",
        "name": "SPOTV",
        "uri": "https://spotv-elivecdn.spotvnow.co.kr/spotv/cbcs/pc.m3u8",
        "icon": "https://tv.kt.com//relatedmaterial/ch_logo/live/fec3895330613133542.png",
        "drm_license_uri": "https://www.spotvnow.co.kr/drm/widevine/spotv/19015302",
        "referer": "https://www.spotvnow.co.kr/player?type=channel&id=9",
    },
    "spotv2": {
        "id": "spotv2",
        "name": "SPOTV2",
        "uri": "https://spotv2-elivecdn.spotvnow.co.kr/spotv2/cbcs/pc.m3u8",
        "icon": "https://tv.kt.com/relatedmaterial/ch_logo/live/c9cddade01216153933.png",
        "drm_license_uri": "https://www.spotvnow.co.kr/drm/widevine/spotv2/19015302",
        "referer": "https://www.spotvnow.co.kr/player?type=channel&id=10",
    },
    "spotv_gnh": {
        "id": "spotv_gnh",
        "name": "SPOTV Golf & Health",
        "uri": "https://spotvgnh-elivecdn.spotvnow.co.kr/spotvgnh/cbcs/pc.m3u8",
        "icon": "https://i.imgur.com/LdXbM0p.png",
        "drm_license_uri": "https://www.spotvnow.co.kr/drm/widevine/spotvgnh/19015302",
        "referer": "https://www.spotvnow.co.kr/player?type=channel&id=11",
    },
    "spotv_prime": {
        "id": "spotv_prime",
        "name": "SPOTV Prime",
        "uri": "https://prime-elivecdn.spotvnow.co.kr/prime/cbcs/pc.m3u8",
        "icon": "https://i.imgur.com/zIpfuzC.png",
        "drm_license_uri": "https://www.spotvnow.co.kr/drm/widevine/prime/19015302",
        "referer": "https://www.spotvnow.co.kr/player?type=channel&id=1",
    },
    "spotv_prime2": {
        "name": "SPOTV Prime2",
        "uri": "https://prime2-elivecdn.spotvnow.co.kr/prime2/cbcs/pc.m3u8",
        "icon": "https://i.imgur.com/r7Ol1Kh.png",
        "drm_license_uri": "https://www.spotvnow.co.kr/drm/widevine/prime2/19015302",
        "referer": "https://www.spotvnow.co.kr/player?type=channel&id=2",
    },
    "spotv_primeplus": {
        "name": "SPOTV Prime+",
        "uri": "https://primeplus-elivecdn.spotvnow.co.kr/primeplus/cbcs/pc.m3u8",
        "icon": "https://i.imgur.com/JVVFLLc.png",
        "drm_license_uri": "https://www.spotvnow.co.kr/drm/widevine/primeplus/19015302",
        "referer": "https://www.spotvnow.co.kr/player?type=channel&id=15",
    },
    "nba": {
        "name": "NBA",
        "uri": "https://nba-elivecdn.spotvnow.co.kr/nba/cbcs/pc.m3u8",
        "icon": "https://i.imgur.com/dG0NCUs.png",
        "drm_license_uri": "https://www.spotvnow.co.kr/drm/widevine/nba/19015302",
        "referer": "https://www.spotvnow.co.kr/player?type=channel&id=3",
    },
}