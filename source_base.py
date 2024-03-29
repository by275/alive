import json
import re
import time
from base64 import b64decode
from collections import OrderedDict
from datetime import timedelta
from functools import lru_cache
from typing import Tuple
from urllib.parse import parse_qs, quote, urlparse

import requests
from plugin import F  # pylint: disable=import-error

from .model import ChannelItem
from .setup import P, default_headers

logger = P.logger
package_name = P.package_name
ModelSetting = P.ModelSetting
SystemModelSetting = F.SystemModelSetting


def ttl_cache(seconds: int, maxsize: int = 10, margin: int = 10):
    def wrapper(func):
        @lru_cache(maxsize)
        def inner(__ttl, *args, **kwargs):
            return func(*args, **kwargs)

        return lambda *args, **kwargs: inner(time.time() // (seconds - margin), *args, **kwargs)

    return wrapper


class SourceBase:
    source_id: str = None
    channel_list: OrderedDict[str, ChannelItem] = OrderedDict()
    ttl: int = None

    PTN_M3U8_ALL_TS: re.Pattern = re.compile(r"^[^#].*\.ts.*$", re.MULTILINE)
    PTN_M3U8_END_TS: re.Pattern = re.compile(r"^[^#].*\.ts$", re.MULTILINE)
    PTN_URL: re.Pattern = re.compile(r"^http(.*?)$", re.MULTILINE)

    def __init__(self):
        pass

    def get_channel_list(self) -> None:
        raise NotImplementedError("method 'get_channel_list' must be implemented")

    def get_url(self, channel_id: str, mode: str, quality: str = None) -> Tuple[str, str]:
        raise NotImplementedError("method 'get_url' must be implemented")

    def repack_m3u8(self, url: str, mode: str = None) -> str:
        pass

    def relay_ts(self, data: str, proxy: str = None) -> str:
        base_url = f"{SystemModelSetting.get('ddns')}/{package_name}/api/relay"
        apikey = None
        if SystemModelSetting.get_bool("use_apikey"):
            apikey = SystemModelSetting.get("apikey")
        for m in self.PTN_URL.finditer(data):
            u = m.group(0)
            u2 = f"{base_url}?url={quote(u)}"
            if apikey is not None:
                u2 += f"&apikey={apikey}"
            if proxy is not None:
                u2 += f"&proxy={quote(proxy)}"
            data = data.replace(u, u2)
        return data

    #
    # utility
    #
    @staticmethod
    def new_session(
        headers: dict = None,
        proxy_url: str = None,
        add_headers: dict = None,
        proxies: dict = None,
    ) -> requests.Session:
        sess = requests.Session()
        sess.headers.update(headers or default_headers)
        sess.headers.update(add_headers or {})
        if not proxies:
            proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else {}
        sess.proxies.update(proxies)
        return sess

    @staticmethod
    def sub_ts(m3u8: str, prefix: str, suffix: str = None) -> str:
        m3u8 = SourceBase.PTN_M3U8_ALL_TS.sub(rf"{prefix}\g<0>", m3u8)
        if suffix is None:
            return m3u8
        return SourceBase.PTN_M3U8_END_TS.sub(rf"\g<0>{suffix}", m3u8)

    @staticmethod
    def b64decode(txt: str, to_json: bool = True) -> str:
        txt = b64decode(txt.rstrip("_") + "===")  # fix incorrect padding
        if to_json:
            return json.loads(txt)
        return txt

    @staticmethod
    def parse_expiry(url: str) -> int:
        u = urlparse(url)
        q = parse_qs(u.query)
        if policy := q.get("Policy", [None])[0]:
            p = SourceBase.b64decode(policy)
            return p["Statement"][0]["Condition"]["DateLessThan"]["AWS:EpochTime"]
        if token := q.get("token", [None])[0]:
            for t in token.split("."):
                try:
                    return SourceBase.b64decode(t)["exp"]
                except Exception:
                    pass
        return None

    @staticmethod
    def expires_in(url: str) -> None:
        try:
            exp = SourceBase.parse_expiry(url)
        except Exception:
            logger.exception("Exception while parsing expiry in url: %s", url)
            exp = None
        if exp is not None:
            logger.debug("%s", timedelta(seconds=exp - time.time()))
