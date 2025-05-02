import json
import re
import time
from base64 import b64decode, urlsafe_b64encode
from collections import OrderedDict
from datetime import timedelta
from functools import lru_cache
from typing import Callable
from urllib.parse import parse_qs, urlencode, urlparse

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

    def b64decode(self, raw: str, to_json: bool = True) -> str | dict:
        raw = b64decode(raw.rstrip("_") + "===")  # fix incorrect padding
        return json.loads(raw) if to_json else raw.decode("utf-8")

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


class CachedMethod:
    def __init__(self, func):
        self.func = func
        self.cache = lru_cache(maxsize=10)(self._call)

    def _call(self, obj, *args, **kwargs):
        return self.func(obj, *args, **kwargs)

    def __get__(self, obj, objtype=None):
        return lambda *args, **kwargs: self.cache(obj, *args, **kwargs)


class SourceBase:
    # class variables
    source_id: str = None
    ttl: int = None

    # instance variables
    channels: OrderedDict[str, ChannelItem] = OrderedDict()
    plsess: requests.Session = None

    PTN_M3U8_ALL: re.Pattern = re.compile(r"^[^#].*\.m3u8.*$", re.MULTILINE)
    PTN_M3U8_END: re.Pattern = re.compile(r"^[^#].*\.m3u8$", re.MULTILINE)
    PTN_M3U8_URL: re.Pattern = re.compile(r'(https?:\/\/(?=.*\.m3u8)[^\s"\']+)')

    PTN_CHUNK_ALL: re.Pattern = re.compile(r"^[^#].*\.(ts|aac).*$", re.MULTILINE)
    PTN_CHUNK_END: re.Pattern = re.compile(r"^[^#].*\.(ts|aac)$", re.MULTILINE)
    PTN_URL: re.Pattern = re.compile(r"^(https?:\/\/[^\/\s]+(?::\d+)?\/[^\s#]*)$", re.MULTILINE)

    def load_channels(self) -> None:
        raise NotImplementedError

    @CachedMethod
    def get_m3u8(self, url: str, streaming_type: str) -> str:
        logger.debug("opening url: %s", url)
        data = self.plsess.get(url).text
        prefix, suffix = self.split_m3u8_url(url)
        data = self.complete_m3u8_urls(data, prefix, suffix)
        return self.rewrite_m3u8_urls(data, streaming_type)

    def repack_m3u8(self, url: str, streaming_type: str) -> str:
        """repack m3u8 media playlist"""
        data = self.plsess.get(url).text
        prefix, suffix = self.split_m3u8_url(url)
        data = self.complete_chunk_urls(data, prefix, suffix)
        if streaming_type == "direct":
            return data
        return self.rewrite_chunk_urls(data)

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
    def split_m3u8_url(url: str) -> tuple[str, str]:
        """Split m3u8 url into prefix and suffix for url completion."""
        base, suffix = url.split(".m3u8", 1)
        return base.rsplit("/", 1)[0] + "/", suffix

    @staticmethod
    def b64url(u: str) -> str:
        """returns base64url encoded string"""
        return urlsafe_b64encode(u.encode()).decode()

    @staticmethod
    def complete_m3u8_urls(m3u8: str, prefix: str, suffix: str = None) -> str:
        """completes incomplete/relative m3u8 media playlist urls in the given m3u8 string"""
        m3u8 = SourceBase.PTN_M3U8_ALL.sub(rf"{prefix}\g<0>", m3u8)
        if suffix is None:
            return m3u8
        return SourceBase.PTN_M3U8_END.sub(rf"\g<0>{suffix}", m3u8)

    def rewrite_m3u8_urls(self, m3u8: str, streaming_type: str) -> str:
        q = urlencode({"s": self.source_id, "t": streaming_type})
        return SourceBase.PTN_M3U8_URL.sub(
            lambda m: f"/alive/proxy/hls/playlist?{q}&url={self.b64url(m.group(1))}",
            m3u8,
        )

    @staticmethod
    def complete_chunk_urls(m3u8: str, prefix: str, suffix: str = None) -> str:
        """completes incomplete/relative chunk urls in the given m3u8 string"""
        m3u8 = SourceBase.PTN_CHUNK_ALL.sub(rf"{prefix}\g<0>", m3u8)
        if suffix is None:
            return m3u8
        return SourceBase.PTN_CHUNK_END.sub(rf"\g<0>{suffix}", m3u8)

    def rewrite_chunk_urls(self, m3u8: str) -> str:
        q = urlencode({"s": self.source_id})
        return SourceBase.PTN_URL.sub(
            lambda m: f"/alive/proxy/hls/chunk?{q}&url={self.b64url(m.group(1))}",
            m3u8,
        )
