import requests

# local
from .model import ChannelItem, SimpleItem
from .setup import P, default_headers
from .source_base import SourceBase

logger = P.logger
package_name = P.package_name
ModelSetting = P.ModelSetting


class SourceKakaotv(SourceBase):
    source_name = "kakaotv"

    @classmethod
    def get_channel_list(cls):
        ret = []
        cls.channel_cache = {}
        for item in map(str.strip, ModelSetting.get(f"{cls.source_name}_list").splitlines()):
            if item.strip() == "":
                continue
            tmp = item.split("|")
            if len(tmp) != 3:
                continue
            cid, title, url = tmp
            c = ChannelItem(cls.source_name, cid, title, None, True)
            cls.channel_cache[cid] = SimpleItem(cid, title, url)
            ret.append(c)
        return ret

    @classmethod
    def __get_url(cls, target):
        target = f"https://tv.kakao.com/api/v5/ft/livelinks/impress?player=monet_html5&service=kakao_tv&section=kakao_tv&dteType=PC&profile=BASE&liveLinkId={target}&withRaw=true&contentType=HLS"
        return requests.get(target, headers=default_headers, timeout=30).json()["raw"]["videoLocation"]["url"]

    @classmethod
    def get_url(cls, channel_id, mode, quality=None):
        # logger.debug('channel_id:%s, quality:%s, mode:%s', channel_id, quality, mode)
        target = cls.channel_cache[channel_id].url.split("/")[-1]
        url = cls.__get_url(target)
        if mode == "web_play":
            return "return_after_read", url
        return "redirect", url
