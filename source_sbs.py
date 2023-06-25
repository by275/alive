import requests

# local
from .model import ChannelItem
from .setup import P, default_headers
from .source_base import SourceBase

logger = P.logger
package_name = P.package_name
ModelSetting = P.ModelSetting


class SourceSBS(SourceBase):
    source_id = "sbs"

    def get_channel_list(self):
        ret = []
        url_list = ["http://static.apis.sbs.co.kr/play-api/1.0/onair/channels"]
        if ModelSetting.get_bool("sbs_include_vod_ch"):
            url_list += ["http://static.apis.sbs.co.kr/play-api/1.0/onair/virtual/channels"]
        for url in url_list:
            data = requests.get(url, timeout=30).json()
            for item in data["list"]:
                cname = item["channelname"]
                is_tv = item.get("type", "TV") == "TV"
                if item["channelid"] in ["S17", "S18"]:
                    cname += " (보는 라디오)"
                    is_tv = True
                c = ChannelItem(self.source_id, item["channelid"], cname, None, is_tv)
                c.current = item["title"]
                c.is_onair = item.get("onair_yn", "N") == "Y"
                ret.append(c)
        return ret

    def __get_url(self, channel_id):
        if channel_id.startswith("EVENT"):
            prefix = ""
        else:
            prefix = "" if channel_id != "SBS" and int(channel_id[1:]) < 21 else "virtual/"
        # tmp = 'http://apis.sbs.co.kr/play-api/1.0/onair/%schannel/%s?v_type=2&platform=pcweb&protocol=hls&ssl=N&jwt-token=%s&rnd=462' % (prefix, channel_id, '')
        tmp = f"https://apis.sbs.co.kr/play-api/1.0/onair/{prefix}channel/{channel_id}?v_type=2&platform=pcweb&protocol=hls&ssl=N&rscuse=&jwt-token=&sbsmain="
        # logger.debug(tmp)

        proxies = None
        if ModelSetting.get_bool("sbs_use_proxy"):
            proxies = {
                "http": ModelSetting.get("sbs_proxy_url"),
                "https": ModelSetting.get("sbs_proxy_url"),
            }
        data = requests.get(tmp, headers=default_headers, proxies=proxies, timeout=30).json()
        url = data["onair"]["source"]["mediasource"]["mediaurl"]
        return url

    def get_url(self, channel_id, mode, quality=None):
        url = self.__get_url(channel_id)
        url = url.replace("playlist.m3u8", "chunklist.m3u8")
        # 2022-03-30
        return "return_after_read", url
        # logger.debug(url)
        # if mode == "web_play":
        #     return "return_after_read", url
        # return "redirect", url

    def get_return_data(self, url, mode=None):
        data = requests.get(url, headers=default_headers, timeout=30).text
        tmp = url.split("chunklist")
        data = data.replace("media", tmp[0] + "media")
        return data
