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
    source_id = "kbs"

    def get_channel_list(self):
        ret = []
        include_vod_ch = ModelSetting.get_bool("kbs_include_vod_ch")
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
                if not include_vod_ch and channel_master["channel_code"].startswith("nvod"):
                    continue
                if channel_master["channel_type"] == "DMB":
                    continue
                c = ChannelItem(
                    self.source_id,
                    channel_master["channel_code"],
                    channel_master["title"],
                    channel_master["image_path_channel_logo"],
                    channel_master["channel_type"] == "TV",
                )
                ret.append(c)
        return ret

    def __get_url(self, channel_id):
        tmp = f"https://cfpwwwapi.kbs.co.kr/api/v1/landing/live/channel_code/{channel_id}"
        # logger.error(tmp)
        data = requests.get(tmp, headers=default_headers, timeout=30).json()
        return data["channel_item"][0]["service_url"]

    def get_url(self, channel_id, mode, quality=None):
        url = self.__get_url(channel_id)
        # logger.info(url)
        if mode == "web_play":
            return "return_after_read", url
        return "redirect", url
