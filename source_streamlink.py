from collections import OrderedDict
from functools import lru_cache
from typing import Tuple

from .model import ChannelItem
from .setup import P
from .source_base import SourceBase

logger = P.logger
package_name = P.package_name
ModelSetting = P.ModelSetting


class SourceStreamlink(SourceBase):
    source_id = "streamlink"
    is_installed: bool = True

    def __init__(self):
        try:
            from streamlink import Streamlink

            # session for streamlink
            self.slsess = Streamlink()
            # cached streamlink stream
            self.get_stream = lru_cache(maxsize=10)(self.__get_stream)
        except ImportError:
            logger.error("streamlink<6.6 패키지가 필요합니다.")
            self.is_installed = False

    def load_channels(self) -> None:
        ret = []
        for item in map(str.strip, ModelSetting.get(f"{self.source_id}_list").splitlines()):
            if not item:
                continue
            if len(tmp := item.split("|")) == 3:
                (cid, cname, url), quality = tmp, ""
            elif len(tmp) == 4:
                cid, cname, url, quality = tmp
            else:
                continue
            c = ChannelItem(self.source_id, cid, cname, None, True)
            c.url = url
            c.quality = quality.strip() or None
            ret.append([c.channel_id, c])
        self.channels = OrderedDict(ret)

    def __get_stream(self, channel_id: str, quality: str):
        url = (c := self.channels[channel_id]).url
        if quality in [None, "default"]:
            quality = c.quality or "best"
        streams = self.slsess.streams(url)
        s = streams.get(quality)
        logger.info("using %r among %s", quality, list(streams))
        logger.debug("new url issued: %s", s.url)
        return s

    def get_m3u8(self, channel_id: str, quality: str) -> str:
        return self.get_stream(channel_id, quality).url

    def make_m3u8(self, channel_id: str, mode: str, quality: str) -> Tuple[str, str]:
        url = self.get_m3u8(channel_id, quality)
        return "redirect", url
