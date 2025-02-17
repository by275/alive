import json
import re
import time
from base64 import b64decode
from collections import OrderedDict
from datetime import timedelta
from functools import lru_cache
from typing import Callable
from urllib.parse import parse_qs, quote, urlparse

import requests
from plugin import F  # type: ignore # pylint: disable=import-error

from .model import ChannelItem
from .setup import P, default_headers

logger = P.logger
package_name = P.package_name
ModelSetting = P.ModelSetting
SystemModelSetting = F.SystemModelSetting


class URLCacher:
    def __init__(self, ttl: int, maxsize: int = 10, factor: float = 0.85):
        self.ttl = ttl
        self.maxsize = maxsize
        self.factor = factor

    @property
    def hash(self):
        return time.time() // (self.ttl * self.factor)

    def __call__(self, func: Callable) -> Callable:
        @lru_cache(self.maxsize)
        def inner(_ttl, *args, **kwargs):
            url = func(*args, **kwargs)
            self.expires_in(url)
            return url

        def wrapper(*args, **kwargs):
            return inner(self.hash, *args, **kwargs)

        return wrapper

    def b64decode(self, txt: str, to_json: bool = True) -> str | dict:
        txt = b64decode(txt.rstrip("_") + "===")  # fix incorrect padding
        if to_json:
            return json.loads(txt)
        return txt

    def parse_expiry(self, url: str) -> int:
        """returns linux epoch"""
        u = urlparse(url)
        q = parse_qs(u.query)
        if policy := q.get("Policy", [None])[0]:
            # AWS cloudfront - wavve, tving, kbs
            p = self.b64decode(policy)
            return p["Statement"][0]["Condition"]["DateLessThan"]["AWS:EpochTime"]
        if token := q.get("token", [None])[0]:
            # sbs
            for t in token.split("."):
                try:
                    return self.b64decode(t)["exp"]
                except Exception:
                    pass
        return None

    def expires_in(self, url: str) -> None:
        if not isinstance(url, str):
            return
        try:
            exp = self.parse_expiry(url)
        except Exception:
            logger.exception("Exception while parsing expiry in url: %s", url)
            exp = None
        logger.debug("new url issued: %s", url)
        if exp is not None:
            exp_in = timedelta(seconds=exp - time.time())
            logger.debug("which will expire in %s", exp_in)
            ttl = int((exp_in.total_seconds() + 30) // 60 * 60)  # to nearest multiple of 60
            if ttl > 0 and self.ttl != ttl:
                logger.debug("detected and changing to the new ttl: %d -> %d", self.ttl, ttl)
                self.ttl = ttl


class SourceBase:
    source_id: str = None
    channels: OrderedDict[str, ChannelItem] = OrderedDict()
    ttl: int = None

    PTN_M3U8_ALL_TS: re.Pattern = re.compile(r"^[^#].*\.(ts|aac).*$", re.MULTILINE)
    PTN_M3U8_END_TS: re.Pattern = re.compile(r"^[^#].*\.(ts|aac)$", re.MULTILINE)
    PTN_URL: re.Pattern = re.compile(r"^http(.*?)$", re.MULTILINE)

    def __init__(self):
        pass

    def load_channels(self) -> None:
        raise NotImplementedError

    def make_m3u8(self, channel_id: str, mode: str, quality: str) -> tuple[str, str | dict]:
        raise NotImplementedError

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
    def relay_ts(m3u8: str, source: str, proxy: str = None) -> str:
        base_url = f"{SystemModelSetting.get('ddns')}/{package_name}/api/relay?source={source}"
        apikey = None
        if SystemModelSetting.get_bool("use_apikey"):
            apikey = SystemModelSetting.get("apikey")
        for m in SourceBase.PTN_URL.finditer(m3u8):
            u = m.group(0)
            u2 = f"{base_url}&url={quote(u)}"
            if apikey is not None:
                u2 += f"&apikey={apikey}"
            if proxy is not None:
                u2 += f"&proxy={quote(proxy)}"
            m3u8 = m3u8.replace(u, u2)
        return m3u8
