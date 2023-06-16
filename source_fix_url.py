# local
from .model import ChannelItem, SimpleItem
from .setup import P
from .source_base import SourceBase

logger = P.logger
package_name = P.package_name
ModelSetting = P.ModelSetting


class SourceFixURL(SourceBase):
    source_name = "fix_url"

    @classmethod
    def get_channel_list(cls):
        ret = []
        cls.channel_cache = {}
        for item in map(str.strip, ModelSetting.get(f"{cls.source_name}_list").splitlines()):
            if not item:
                continue
            tmp = item.split("|")
            if len(tmp) != 4:
                continue
            cid, title, url, is_radio = tmp
            c = ChannelItem(cls.source_name, cid, title, None, is_radio == "Y")
            cls.channel_cache[cid] = SimpleItem(cid, title, url)
            ret.append(c)
        return ret

    @classmethod
    def get_url(cls, channel_id, mode, quality=None):
        url = cls.channel_cache[channel_id].url
        if mode == "web_play":
            return "return_after_read", url
        return "redirect", url
