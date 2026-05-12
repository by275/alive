import json
import re
import time
from base64 import b64decode, urlsafe_b64encode
from collections import OrderedDict
from datetime import timedelta
from functools import lru_cache
from threading import Lock
from typing import Callable
from urllib.parse import parse_qs, urljoin, urlparse

import requests
import yaml
from plugin import F  # type: ignore # pylint: disable=import-error

from .model import ChannelItem, ChannelMap
from .setup import Loader, P, alive_prefs, default_headers

logger = P.logger
package_name = P.package_name
ModelSetting = P.ModelSetting
SystemModelSetting = F.SystemModelSetting

PTN_HLS_ATTR: re.Pattern = re.compile(r'([A-Z0-9-]+)=("([^"]*)"|[^,]*)')
PTN_HLS_URI_ATTR: re.Pattern = re.compile(r'URI="([^"]+)"')
HLS_MEDIA_EXTS = (".ts", ".aac", ".m4s", ".mp4", ".m4a", ".cmfv", ".cmfa")


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
            # jwt token - sbs, tving
            try:
                payload = token.split(".")[1]
                return float(self.b64decode(payload)["exp"])
            except Exception:
                pass
        return None

    def expires_in(self, url: str | dict) -> None:
        if isinstance(url, dict):
            url = url.get("uri", "")  # tving drm
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


def _parse_hls_attrs(line: str) -> dict[str, str]:
    attrs = {}
    payload = line.split(":", 1)[1] if ":" in line else line
    for match in PTN_HLS_ATTR.finditer(payload):
        key = match.group(1)
        raw = match.group(2)
        if raw.startswith('"') and raw.endswith('"'):
            raw = raw[1:-1]
        attrs[key] = raw
    return attrs


def _is_hls_media_uri(uri: str) -> bool:
    return urlparse(uri).path.lower().endswith(HLS_MEDIA_EXTS)


def _complete_hls_media_url(media_url: str, uri: str) -> str:
    url = urljoin(media_url, uri)
    suffix = media_url.partition(".m3u8")[2]
    if suffix and _is_hls_media_uri(url) and not urlparse(url).query:
        return f"{url}{suffix}"
    return url


def _rewrite_hls_uri_attr(line: str, repl) -> str:
    return PTN_HLS_URI_ATTR.sub(lambda m: f'URI="{repl(m.group(1))}"', line, count=1)


def parse_hls_master_playlist(data: str, master_url: str) -> dict:
    lines = str(data or "").splitlines()
    streams = []
    renditions = []
    idx = 0
    stream_order = 0
    rendition_order = 0
    while idx < len(lines):
        raw = lines[idx]
        line = raw.strip()
        if line.startswith("#EXT-X-MEDIA:"):
            attrs = _parse_hls_attrs(line)
            if uri := attrs.get("URI"):
                renditions.append({"uri": uri, "order": rendition_order, "attrs": attrs})
                rendition_order += 1
        if line.startswith("#EXT-X-STREAM-INF:"):
            attrs = _parse_hls_attrs(line)
            uri_line = lines[idx + 1] if idx + 1 < len(lines) else ""
            uri = uri_line.strip()
            if uri and not uri.startswith("#"):
                streams.append(
                    {
                        "uri": uri,
                        "bandwidth": int(attrs.get("BANDWIDTH") or "0"),
                        "height": int((attrs.get("RESOLUTION") or "0x0").lower().rsplit("x", 1)[-1] or 0),
                        "order": stream_order,
                        "attrs": attrs,
                    }
                )
                stream_order += 1
                idx += 2
                continue
        idx += 1

    if not streams:
        raise ValueError(f"HLS master playlist has no EXT-X-STREAM-INF variants: {master_url}")

    # Keep streams ordered by preferred playback quality; streams[0] is the best variant.
    streams.sort(key=lambda item: (-item["height"], -item["bandwidth"], item["order"]))

    # Complete only parsed child playlist URIs while preserving manifest formatting and comments.
    contents = data
    suffix = master_url.partition(".m3u8")[2]
    for item in renditions + streams:
        url = urljoin(master_url, item["uri"])
        if suffix and url.endswith(".m3u8"):
            url = f"{url}{suffix}"
        contents = contents.replace(item["uri"], url, 1)
        item["url"] = url
    return {
        "raw": {"url": master_url, "manifest": data},
        "contents": contents,
        "streams": streams,
        "renditions": renditions,
    }


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
    plsess: requests.Session = None

    @property
    def channels(self) -> ChannelMap:
        if not hasattr(self, "_channels"):
            self._channels = ChannelMap(source_id=self.source_id)
        return self._channels

    @channels.setter
    def channels(self, channels: OrderedDict[str, ChannelItem]) -> None:
        self._channels = ChannelMap(channels, source_id=self.source_id)

    def load_channels(self) -> None:
        raise NotImplementedError

    def load_channel_source(self) -> dict:
        with alive_prefs.open("r", encoding="utf-8") as f:
            return (yaml.load(f, Loader=Loader) or {}).get("channel_source", {}).get(self.source_id, {})

    @property
    def streaming_type(self) -> str:
        """shortcuts to db settings"""
        return ModelSetting.get(f"{self.source_id}_streaming_type")

    @property
    def quality(self) -> str:
        """shortcuts to db settings"""
        return ModelSetting.get(f"{self.source_id}_quality")

    @CachedMethod
    def get_m3u8(self, url: str) -> dict:
        logger.debug("opening url: %s", url)
        data = self.plsess.get(url).text
        return parse_hls_master_playlist(data, url)

    def repack_m3u8(self, url: str, streaming_type: str) -> str:
        """repack m3u8 media playlist"""
        if not hasattr(self, "_repack_cache"):
            self._repack_cache = {}
            self._repack_lock = Lock()

        now = time.time()
        with self._repack_lock:
            if url in self._repack_cache:
                data, ts, ttl = self._repack_cache[url]
                if now - ts < ttl:
                    return data

        raw = self.plsess.get(url, timeout=5).text
        data, ttl = self.parse_hls_media_playlist(raw, url)

        now = time.time()
        with self._repack_lock:
            self._repack_cache[url] = (data, now, ttl)
            for expired in [k for k, (_, ts, _) in self._repack_cache.items() if now - ts > 10.0]:
                del self._repack_cache[expired]

        if streaming_type == "direct":
            return data
        return self.rewrite_hls_media_urls(data, self.source_id)

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
    def b64url(u: str) -> str:
        """returns base64url encoded string"""
        return urlsafe_b64encode(u.encode()).decode()

    @staticmethod
    def rewrite_hls_master_urls(master: dict, path: str) -> str:
        contents = str(master.get("contents") or "")
        for idx, rendition in enumerate(master.get("renditions") or []):
            contents = contents.replace(str(rendition["url"]), f"{path}&r={idx}", 1)
        for idx, stream in enumerate(master.get("streams") or []):
            contents = contents.replace(str(stream["url"]), f"{path}&t={idx}", 1)
        return contents

    @staticmethod
    def parse_hls_media_playlist(m3u8: str, media_url: str) -> tuple[str, float]:
        """Parse and complete media playlist URLs, returning contents and cache TTL."""
        output = []
        target_duration = None
        part_target = None
        for raw in str(m3u8 or "").splitlines():
            line = raw.strip()
            if line.startswith("#EXT-X-TARGETDURATION:"):
                try:
                    target_duration = float(line.split(":", 1)[1])
                except Exception:
                    pass
            elif line.startswith("#EXT-X-PART-INF:"):
                try:
                    part_target = float(_parse_hls_attrs(line)["PART-TARGET"])
                except Exception:
                    pass
            elif line.startswith(("#EXT-X-MAP:", "#EXT-X-KEY:")):
                raw = _rewrite_hls_uri_attr(raw, lambda uri: _complete_hls_media_url(media_url, uri))
            elif line and not line.startswith("#") and _is_hls_media_uri(line):
                raw = _complete_hls_media_url(media_url, line)
            output.append(raw)
        if part_target:
            ttl = max(0.25, min(1.0, part_target))
        elif target_duration:
            ttl = max(0.5, min(2.0, target_duration * 0.5))
        else:
            ttl = 1.0
        return "\n".join(output) + "\n", ttl

    @staticmethod
    def rewrite_hls_media_urls(m3u8: str, source: str) -> str:
        def proxy_url(url: str) -> str:
            return f"/alive/proxy/hls/chunk?s={source}&url={SourceBase.b64url(url)}"

        output = []
        for raw in str(m3u8 or "").splitlines():
            line = raw.strip()
            if line.startswith(("#EXT-X-MAP:", "#EXT-X-KEY:")):
                raw = _rewrite_hls_uri_attr(raw, proxy_url)
            elif line.startswith(("http://", "https://")) and _is_hls_media_uri(line):
                raw = proxy_url(line)
            output.append(raw)
        return "\n".join(output) + "\n"
