import re
import time
from collections import OrderedDict
from functools import lru_cache
from typing import Tuple
from urllib.parse import quote

import requests
from plugin import F  # pylint: disable=import-error

from .model import ChannelItem
from .setup import P, default_headers

logger = P.logger
package_name = P.package_name
ModelSetting = P.ModelSetting
SystemModelSetting = F.SystemModelSetting


def ttl_cache(seconds: int, maxsize: int = 10):
    def wrapper(func):
        @lru_cache(maxsize)
        def inner(__ttl, *args, **kwargs):
            return func(*args, **kwargs)

        return lambda *args, **kwargs: inner(time.time() // seconds, *args, **kwargs)

    return wrapper


class SourceBase:
    source_id: str = None
    channel_list: OrderedDict[str, ChannelItem] = OrderedDict()
    ttl: int = None

    PTN_M3U8_TS: re.Pattern = re.compile(r"^[^#].*\.ts.*$", re.MULTILINE)
    PTN_URL = re.compile(r"^http(.*?)$", re.MULTILINE)

    def __init__(self):
        pass

    def get_channel_list(self) -> None:
        raise NotImplementedError("method 'get_channel_list' must be implemented")

    def get_url(self, channel_id: str, mode: str, quality: str = None) -> Tuple[str, str]:
        raise NotImplementedError("method 'get_url' must be implemented")

    def repack_playlist(self, url: str, mode: str = None) -> str:
        pass

    def relay_segments(self, data: str, proxy: str = None) -> str:
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
    def new_session(
        self,
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

    def sub_ts(self, m3u8: str, prefix: str, suffix: str = None):
        repl = rf"{prefix}\g<0>"
        if suffix is not None:
            repl += suffix
        return self.PTN_M3U8_TS.sub(repl, m3u8)
