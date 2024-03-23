from collections import OrderedDict
from typing import Tuple

from .model import ChannelItem
from .setup import P
from .source_base import SourceBase

logger = P.logger
package_name = P.package_name
ModelSetting = P.ModelSetting


class SourceFixURL(SourceBase):
    source_id = "fix_url"

    def get_channel_list(self) -> OrderedDict[str, ChannelItem]:
        ret = []
        for item in map(str.strip, ModelSetting.get(f"{self.source_id}_list").splitlines()):
            if not item:
                continue
            tmp = item.split("|")
            if len(tmp) != 4:
                continue
            cid, cname, url, radio_yn = tmp
            c = ChannelItem(self.source_id, cid, cname, None, radio_yn == "Y")
            c.url = url
            ret.append([c.channel_id, c])
        self.channel_list = OrderedDict(ret)
        return self.channel_list

    def get_url(self, channel_id: str, mode: str, quality: str = None) -> Tuple[str, str]:
        url = self.channel_list[channel_id].url
        if mode == "web_play":
            return "return_after_read", url
        return "redirect", url
