import json
from collections import OrderedDict

from .model import ChannelItem
from .setup import P
from .source_base import SourceBase

logger = P.logger
package_name = P.package_name
ModelSetting = P.ModelSetting


class SourceFixURL(SourceBase):
    source_id = "fix_url"

    def load_channels(self) -> None:
        ret = []
        for item in map(str.strip, ModelSetting.get(f"{self.source_id}_list").splitlines()):
            if not item:
                continue
            tmp = item.split("|")
            if len(tmp) < 4:
                continue
            cid, cname, url, radio_yn = tmp[:4]
            c = ChannelItem(self.source_id, cid, cname, None, radio_yn == "Y", not url.startswith("http"))
            c.url = url
            ret.append(c)
        self.channels = OrderedDict((c.channel_id, c) for c in ret)

    def get_url(self, channel_id: str) -> str:
        return self.channels[channel_id].url

    def make_m3u8(self, channel_id: str, mode: str, quality: str) -> tuple[str, str | dict]:
        url = self.get_url(channel_id)
        return "redirect", url
