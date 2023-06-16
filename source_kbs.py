import json

import requests

# local
from .model import ChannelItem
from .setup import P, default_headers
from .source_base import SourceBase

logger = P.logger
package_name = P.package_name
ModelSetting = P.ModelSetting


class SourceKBS(SourceBase):
    source_name = "kbs"

    @classmethod
    def get_channel_list(cls):
        ret = []
        url = "http://onair.kbs.co.kr"
        data = requests.get(url, timeout=30).text
        idx1 = data.find("var channelList = JSON.parse") + 30
        idx2 = data.find(");", idx1) - 1
        data = data[idx1:idx2].replace("\\", "")
        data = json.loads(data)
        for channel in data["channel"]:
            for channel_master in channel["channel_master"]:
                if "_" in channel_master["channel_code"]:
                    continue
                if channel_master["channel_type"] == "DMB":
                    continue
                c = ChannelItem(
                    cls.source_name,
                    channel_master["channel_code"],
                    channel_master["title"],
                    channel_master["image_path_channel_logo"],
                    channel_master["channel_type"] == "TV",
                )
                ret.append(c)
        return ret

    @classmethod
    def __get_url(cls, channel_id):
        tmp = f"https://cfpwwwapi.kbs.co.kr/api/v1/landing/live/channel_code/{channel_id}"
        # logger.error(tmp)
        data = requests.get(tmp, headers=default_headers, timeout=30).json()
        return data["channel_item"][0]["service_url"]

    @classmethod
    def get_url(cls, channel_id, mode, quality=None):
        url = cls.__get_url(channel_id)
        # logger.info(url)
        if mode == "web_play":
            return "return_after_read", url
        return "redirect", url
