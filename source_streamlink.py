# local
from .model import ChannelItem, SimpleItem
from .setup import P
from .source_base import SourceBase

logger = P.logger
package_name = P.package_name
ModelSetting = P.ModelSetting


class SourceStreamlink(SourceBase):
    source_name = "streamlink"

    @staticmethod
    def is_installed():
        try:
            import streamlink

            return True
        except ImportError:
            return False

    @classmethod
    def get_channel_list(cls):
        ret = []
        cls.channel_dict = {}
        for item in map(str.strip, ModelSetting.get(f"{cls.source_name}_list").splitlines()):
            if not item:
                continue
            tmp = item.split("|")
            if len(tmp) != 3:
                continue
            cid, title, url = tmp
            c = ChannelItem(cls.source_name, cid, title, None, True)
            cls.channel_dict[cid] = SimpleItem(cid, title, url)
            ret.append(c)
        return ret

    @classmethod
    def get_url(cls, channel_id, mode, quality=None):
        # logger.debug('channel_id:%s, quality:%s, mode:%s', channel_id, quality, mode)
        from streamlink import Streamlink

        s = Streamlink()
        # logger.debug(StreamlinkItem.ch_list[channel_id].url)
        data = s.streams(cls.channel_dict[channel_id].url)

        try:
            stream = data[ModelSetting.get("streamlink_quality")]
            url = stream.url
        except Exception:
            if "youtube" in cls.channel_dict[channel_id].url.lower():
                for t in data.values():
                    try:
                        url = t.url
                    except Exception:
                        pass
        if mode == "web_play":
            return "return_after_read", url
        return "redirect", url
