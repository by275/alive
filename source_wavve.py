import time
from collections import OrderedDict
from functools import lru_cache
from html import unescape
from pathlib import Path
from typing import Tuple
from urllib.parse import quote

import requests
from support import SupportSC  # pylint: disable=import-error

# local
from .model import ChannelItem, ProgramItem
from .setup import P
from .source_base import SourceBase

logger = P.logger
package_name = P.package_name
ModelSetting = P.ModelSetting


def ttl_cache(seconds: int, maxsize: int = 128):
    def wrapper(func):
        @lru_cache(maxsize)
        def inner(__ttl, *args, **kwargs):
            return func(*args, **kwargs)

        return lambda *args, **kwargs: inner(time.time() // seconds, *args, **kwargs)

    return wrapper


class SourceWavve(SourceBase):
    source_id = "wavve"
    mod = None

    def __init__(self):
        if self.mod is not None:
            return
        try:
            self.mod = self.load_support_module()
        except (ImportError, ModuleNotFoundError):
            logger.error("support site 플러그인이 필요합니다.")
        except Exception:
            logger.exception("Support Module 로딩 중 예외:")
        # session for requesting playlists
        sess = requests.Session()
        sess.headers.update(self.mod.headers)
        sess.proxies.update(self.mod.proxies or {})
        self.session = sess
        # cached streaming data
        self.streaming = ttl_cache(60 * 60 * 10, maxsize=10)(self.__streaming)

    def load_support_module(self):
        if Path(__file__).with_name("wavve.py").is_file():
            from .wavve import SupportWavve as mod
        else:
            mod = SupportSC.load_module_f(__file__, "wavve").SupportWavve
        from support_site.setup import P as SS  # pylint: disable=import-error

        mod.initialize(
            SS.ModelSetting.get("site_wavve_credential"),
            SS.ModelSetting.get_bool("site_wavve_use_proxy"),
            SS.ModelSetting.get("site_wavve_proxy_url"),
        )
        return mod

    def get_channel_list(self):
        ret = []
        data = self.mod.live_all_channels()
        for item in data["list"]:
            try:
                p = ProgramItem(
                    program_id=item["programid"],
                    title=unescape(item["title"].strip()),
                    image="https://" + quote(item["image"]) if item["image"] != "" else None,
                    stime=item["starttime"],
                    etime=item["endtime"],
                    onair=item["license"] == "y",
                    targetage=int(item["targetage"] or "0"),
                )
                c = ChannelItem(
                    self.source_id,
                    item["channelid"],
                    item["channelname"],
                    "https://" + quote(item["tvimage"]) if item["tvimage"] != "" else "",
                    item["type"] == "video",
                    program=p,
                )
                ret.append([c.channel_id, c])
            except Exception:
                logger.exception("라이브 채널 분석 중 예외: %s", item)
        self.channel_list = OrderedDict(ret)
        return self.channel_list

    def __streaming(self, channel_id: str, quality: str) -> dict:
        return self.mod.streaming("live", channel_id, quality)

    def get_url(self, channel_id: str, mode: str, quality: str = None) -> Tuple[str, str]:
        """returns playlist url from streaming data

        새로운 playlist는 최신의/연속된 MEDIA SEQUENCE를 보장할 수 없다. (Error: Received stale playlist)
        따라서 한 번 얻은 playlist url을 최대한 유지해야 한다. (cache를 사용하는 이유)
        """
        data = self.streaming(channel_id, quality)
        # 2022-01-10 라디오. 대충 함 by soju6jan
        # if data['quality'] == '100p' or data['qualities']['list'][0]['name'] == '오디오모드':
        #    surl = data['playurl'].replace('/100/100', '/100') + f"/live.m3u8{data['debug']['orgurl'].split('.m3u8')[1]}"
        assert (purl := data.get("playurl")) is not None, "Playlist URL is None!"

        if mode == "web_play":
            return "return_after_read", purl
        if ModelSetting.get("wavve_streaming_type") == "redirect":
            return "redirect", purl
        return "return_after_read", purl

    def get_return_data(self, url, mode=None):
        data = self.session.get(url).text
        prefix = url.split("?")[0].rsplit("/", 1)[0]
        new_lines = []
        for line in data.splitlines():
            line = line.strip()
            if line.startswith("#EXT-X-ALLOW-CACHE"):
                continue  # EXT-X-ALLOW-CACHE has been deprecated
            if line.startswith != "#" and ".ts" in line:
                line = f"{prefix}/{line}"
            new_lines.append(line)
        new_lines = "\n".join(new_lines)
        if ModelSetting.get("wavve_streaming_type") == "direct":
            return new_lines
        return self.change_redirect_data(new_lines, proxy=self.mod.proxy)
