# local
from .model import ChannelItem, SimpleItem
from .setup import P
from .source_base import SourceBase

logger = P.logger
package_name = P.package_name
ModelSetting = P.ModelSetting


class SourceFixURL(SourceBase):
    source_id = "fix_url"

    def get_channel_list(self):
        ret = []
        self.channel_cache = {}
        for item in map(str.strip, ModelSetting.get(f"{self.source_id}_list").splitlines()):
            if not item:
                continue
            tmp = item.split("|")
            if len(tmp) != 4:
                continue
            cid, title, url, is_radio = tmp
            c = ChannelItem(self.source_id, cid, title, None, is_radio == "Y")
            self.channel_cache[cid] = SimpleItem(cid, title, url)
            ret.append(c)
        return ret

    def get_url(self, channel_id, mode, quality=None):
        url = self.channel_cache[channel_id].url
        if mode == "web_play":
            return "return_after_read", url
        return "redirect", url
