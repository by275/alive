import re
from collections import OrderedDict
from typing import Tuple

import requests

from .model import ChannelItem
from .setup import P, default_headers
from .source_base import SourceBase

logger = P.logger
package_name = P.package_name
ModelSetting = P.ModelSetting


class SourceNavertv(SourceBase):
    source_id = "navertv"

    def get_channel_list(self) -> None:
        ret = []
        for item in map(str.strip, ModelSetting.get(f"{self.source_id}_list").splitlines()):
            if not item:
                continue
            tmp = item.split("|")
            if len(tmp) == 3:
                cid, cname, url = tmp
                quality = "1080"
            elif len(tmp) == 4:
                cid, cname, url, quality = tmp
            else:
                continue
            c = ChannelItem(self.source_id, cid, cname, None, True)
            c.url = url
            c.quality = quality
            ret.append([c.channel_id, c])
        self.channel_list = OrderedDict(ret)

    def __get_url(self, target_url: str, quality: str) -> str:
        if target_url.startswith("SPORTS_"):
            target_ch = target_url.split("_")[1]
            if not target_ch.startswith("ad") and not target_ch.startswith("ch"):
                target_ch = "ch" + target_ch
            tmp = {"480": "800", "720": "2000", "1080": "5000"}
            qua = tmp.get(quality, "5000")
            tmp = f"https://apis.naver.com/pcLive/livePlatform/sUrl?ch={target_ch}&q={qua}&p=hls&cc=KR&env=pc"
            url = requests.get(tmp, headers=default_headers, timeout=30).json()["secUrl"]

            # https://proxy-gateway.sports.naver.com/livecloud/lives/3278079/playback?countryCode=KR&devt=HTML5_PC&timeMachine=true&p2p=true&includeThumbnail=true&pollingStatus=true
        else:
            # logger.debug(target_url)
            text = requests.get(target_url, headers=default_headers, timeout=30).text
            match = re.search(r"liveId: \'(?P<liveid>\d+)\'", text)
            # logger.debug(match)
            if match:
                liveid = match.group("liveid")
                # https://api.tv.naver.com/api/open/live/v2/player/playback?liveId=3077128&countryCode=KR&timeMachine=true
                json_url = f"https://api.tv.naver.com/api/open/live/v2/player/playback?liveId={liveid}&countryCode=KR&timeMachine=true"
                data = requests.get(json_url, headers=default_headers, timeout=30).json()

                url = data["media"][0]["path"]
        return url

    def get_url(self, channel_id: str, mode: str, quality: str = None) -> Tuple[str, str]:
        # logger.debug('channel_id:%s, quality:%s, mode:%s', channel_id, quality, mode)
        target_url = self.channel_list[channel_id].url
        url = self.__get_url(target_url, self.channel_list[channel_id].quality)
        if mode == "web_play":
            return "return_after_read", url
        return "redirect", url
