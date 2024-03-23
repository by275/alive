from collections import OrderedDict
from typing import Tuple

import requests

from .model import ChannelItem
from .setup import P, default_headers
from .source_base import SourceBase

logger = P.logger
package_name = P.package_name
ModelSetting = P.ModelSetting


class SourceKakaotv(SourceBase):
    source_id = "kakaotv"

    def get_channel_list(self) -> OrderedDict[str, ChannelItem]:
        ret = []
        for item in map(str.strip, ModelSetting.get(f"{self.source_id}_list").splitlines()):
            if item.strip() == "":
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

    def __get_url(self, target: str) -> str:
        target = f"https://tv.kakao.com/api/v5/ft/livelinks/impress?player=monet_html5&service=kakao_tv&section=kakao_tv&dteType=PC&profile=BASE&liveLinkId={target}&withRaw=true&contentType=HLS"
        return requests.get(target, headers=default_headers, timeout=30).json()["raw"]["videoLocation"]["url"]

    def get_url(self, channel_id: str, mode: str, quality: str = None) -> Tuple[str, str]:
        # logger.debug('channel_id:%s, quality:%s, mode:%s', channel_id, quality, mode)
        target = self.channel_list[channel_id].url.split("/")[-1]
        url = self.__get_url(target)
        if mode == "web_play":
            return "return_after_read", url
        return "redirect", url
