import re
from collections import OrderedDict
from urllib.parse import urlencode
from flask import Response, request
import requests

from tool import ToolUtil 
from .model import ChannelItem, ProgramItem
from .setup import P
from .source_base import SourceBase, URLCacher

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

    PTN_HTTP = re.compile(r"^http:\/\/")
    license_info = {}
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
        # caching master playlist url
        self.get_url = URLCacher(self.ttl)(self.__get_url)

    def load_support_module(self):
        from support_site import SupportTving as ST  # type: ignore

        token = ST._SupportTving__token.strip()  # pylint: disable=protected-access
        if not token:
            logger.error("티빙 토큰이 필요합니다.")
            return None
        return ST

    def load_channels(self) -> None:
        ret = []
        name_counter = {}

        data = self.mod.get_live_list(list_type="live", include_drm=P.ModelSetting.get_bool("tving_include_drm"))
        for item in data:
            try:
                name = item["title"]
                if "KBO" in name:  # KBO 프로야구 중복 채널명 문제
                    count = name_counter.setdefault(name, 0) + 1
                    name_counter[name] = count
                    name = f"{name} {count}"

                p = ProgramItem(title=item["episode_title"], onair=not item.get("block", False))
                c = ChannelItem(
                    self.source_id,
                    item["id"],
                    name,
                    item["img"],
                    True,
                    is_drm=item["is_drm"],
                    program=p,
                )
                ret.append(c)
            except Exception:
                logger.exception("라이브 채널 분석 중 예외: %s", item)
        self.channels = OrderedDict((c.channel_id, c) for c in ret)

    def get_data(self, channel_id: str, quality: str) -> dict:
        if quality in [None, "default"]:
            quality = ModelSetting.get("tving_quality")
        quality = quality_map.get(quality, "1080p")
        return self.mod.get_info(channel_id, quality)

    def upgrade_http(self, d):
        """in-place replacement of http urls in data"""
        if isinstance(d, (dict, list)):
            for k, v in d.items() if isinstance(d, dict) else enumerate(d):
                if isinstance(v, str) and v.startswith("http://"):
                    d[k] = self.PTN_HTTP.sub("https://", d[k])
                self.upgrade_http(v)

    def __get_url(self, channel_id: str, quality: str) -> str | dict:
        data = self.get_data(channel_id, quality)
        self.upgrade_http(data)
        if self.channels[channel_id].is_drm:
            del data["play_info"]["mpd_headers"]
            return data["play_info"]
        cookies = "; ".join("CloudFront-" + c for c in data["url"].split("?")[1].split("&"))
        self.plsess.headers.update({"Cookie": cookies})  # tvn 같은 몇몇 채널은 쿠키 인증이 필요
        return data["url"]

    def make_drm(self, data: dict, mode: str) -> tuple[str, dict]:
        if mode == "web_play":
            return "drm+web", {
                "src": data["uri"],
                "type": "application/dash+xml",
                "keySystems": {
                    "com.widevine.alpha": {
                        "url": "/alive/proxy/license",
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
        elif mode == "kodi":
            self.license_info[data['id']] = data
            license_url =ToolUtil.make_apikey_url(f"/alive/tvinglicense/{data['id']}")
            text = f"""#KODIPROP:inputstream=inputstream.adaptive
#KODIPROP:inputstream.adaptive.license_type=com.widevine.alpha
#KODIPROP:inputstream.adaptive.license_key={license_url}
{data['uri']}"""
            return "m3u8", text
        return "drm", data

    def make_m3u8(self, channel_id: str, mode: str, quality: str) -> tuple[str, str | dict]:
        url = self.get_url(channel_id, quality)
        if self.channels[channel_id].is_drm:
            url['id'] = channel_id
            return self.make_drm(url, mode)
        stype = "proxy" if mode == "web_play" else "direct"
        return stype, self.get_m3u8(url)  # direct, proxy(web_play)


@P.blueprint.route("/tvinglicense/<channel_id>", methods=["OPTIONS", "POST"])
def proxy_license(channel_id):
    try:
        from .logic_klive import LogicKlive
        data = LogicKlive.sources['tving'].license_info[channel_id]
        headers = {
            "origin": data["drm_key_request_properties"]["origin"],
            "referer": data["drm_key_request_properties"]["referer"],
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3",
            "Pallycon-Customdata-V2": data["drm_key_request_properties"]["pallycon-customdata-v2"],
        }
        
        res = requests.request(
            method=request.method,
            url=data["drm_license_uri"],
            headers=headers,
            data=request.get_data(),
            cookies=request.cookies,
            allow_redirects=False,
            timeout=10,
        )
        excluded_headers = [
            "content-encoding",
            "content-length",
            "transfer-encoding",
            "connection",
        ]
        headers = [(k, v) for k, v in res.raw.headers.items() if k.lower() not in excluded_headers]        
        response = Response(res.content, res.status_code, headers)
        return response
    except Exception as e:
        return Response(str(e), status=500, mimetype="text/plain")