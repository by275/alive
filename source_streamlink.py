from collections import OrderedDict

# local
from .model import ChannelItem
from .setup import P
from .source_base import SourceBase

logger = P.logger
package_name = P.package_name
ModelSetting = P.ModelSetting


class SourceStreamlink(SourceBase):
    source_id = "streamlink"

    @staticmethod
    def is_installed():
        try:
            import streamlink

            return True
        except ImportError:
            return False

    def get_channel_list(self):
        ret = []
        for item in map(str.strip, ModelSetting.get(f"{self.source_id}_list").splitlines()):
            if not item:
                continue
            tmp = item.split("|")
            if len(tmp) != 3:
                continue
            cid, cname, url = tmp
            c = ChannelItem(self.source_id, cid, cname, None, True)
            c.url = url
            ret.append([c.channel_id, c])
        self.channel_list = OrderedDict(ret)
        return self.channel_list

    def get_url(self, channel_id, mode, quality=None):
        # logger.debug('channel_id:%s, quality:%s, mode:%s', channel_id, quality, mode)
        from streamlink import Streamlink

        s = Streamlink()
        # logger.debug(StreamlinkItem.ch_list[channel_id].url)
        data = s.streams(self.channel_list[channel_id].url)

        try:
            stream = data[ModelSetting.get("streamlink_quality")]
            url = stream.url
        except Exception:
            if "youtube" in self.channel_list[channel_id].url.lower():
                for t in data.values():
                    try:
                        url = t.url
                    except Exception:
                        pass
        if mode == "web_play":
            return "return_after_read", url
        return "redirect", url
