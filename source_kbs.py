import json
from collections import OrderedDict

import requests

# local
from .model import ChannelItem
from .setup import P, default_headers
from .source_base import SourceBase

logger = P.logger
package_name = P.package_name
ModelSetting = P.ModelSetting


class SourceKBS(SourceBase):
    source_id = "kbs"

    def __parse_var(self, text: str, identifiers):
        left = text.find(identifiers[0]) + len(identifiers[0])
        right = text.find(identifiers[1], left)
        return json.loads(text[left:right].replace("\\", ""))

    def get_channel_list(self):
        ret = []
        include_vod_ch = ModelSetting.get_bool("kbs_include_vod_ch")
        url = "http://onair.kbs.co.kr"
        data = requests.get(url, timeout=30).text
        data = self.__parse_var(data, ("var channelList = JSON.parse('", "');"))
        for channel in data["channel"]:
            for cm in channel["channel_master"]:
                if "_" in cm["channel_code"]:
                    continue  # 지역민방 제외 목적
                if not include_vod_ch and cm["channel_code"].startswith("nvod"):
                    continue
                if cm["channel_type"] == "DMB":
                    continue
                c = ChannelItem(
                    self.source_id,
                    cm["channel_code"],
                    cm["title"],
                    cm["image_path_channel_logo"],
                    cm["channel_type"] == "TV",
                )
                ret.append([c.channel_id, c])
        self.channel_list = OrderedDict(ret)
        return self.channel_list

    def __get_url(self, channel_id):
        tmp = f"https://cfpwwwapi.kbs.co.kr/api/v1/landing/live/channel_code/{channel_id}"
        # logger.error(tmp)
        data = requests.get(tmp, headers=default_headers, timeout=30).json()
        return data["channel_item"][0]["service_url"]

    def get_url(self, channel_id, mode, quality=None):
        url = self.__get_url(channel_id)
        # logger.info(url)
        # Expires가 1일로 길어서 괜찮을 듯
        return "redirect", url
