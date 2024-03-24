from collections import OrderedDict
from typing import Tuple

from .model import ChannelItem, ProgramItem
from .setup import P
from .source_base import SourceBase, ttl_cache

logger = P.logger
package_name = P.package_name
ModelSetting = P.ModelSetting


class SourceSBS(SourceBase):
    source_id = "sbs"
    ttl = 180  # 3분

    def __init__(self):
        # session for api
        proxy_url = ModelSetting.get("sbs_proxy_url") if ModelSetting.get_bool("sbs_use_proxy") else None
        self.apisess = self.new_session(proxy_url=proxy_url, add_headers={"Referer": "https://www.sbs.co.kr/"})
        # session for playlists
        self.plsess = self.new_session()
        # cached playlist url
        self.get_playlist = ttl_cache(self.ttl)(self.__get_playlist)

    def get_channel_list(self) -> None:
        ret = []
        url_list = ["http://static.apis.sbs.co.kr/play-api/1.0/onair/channels"]
        if ModelSetting.get_bool("sbs_include_vod_ch"):
            url_list += ["http://static.apis.sbs.co.kr/play-api/1.0/onair/virtual/channels"]
        for url in url_list:
            data = self.apisess.get(url).json()
            for item in data["list"]:
                try:
                    cname = item["channelname"]
                    is_tv = item.get("type", "TV") == "TV"
                    if item["channelid"] in ["S17", "S18"]:
                        cname += " (보는 라디오)"
                        is_tv = True
                    p = ProgramItem(
                        title=item["title"],
                        onair=item.get("onair_yn", "N") == "Y",
                        stime=item["starttime"],
                        etime=item["endtime"],
                        image=item["thumbimg"],
                    )
                    c = ChannelItem(self.source_id, item["channelid"], cname, None, is_tv, program=p)
                    ret.append([c.channel_id, c])
                except Exception:
                    logger.exception("라이브 채널 분석 중 예외: %s", item)
        self.channel_list = OrderedDict(ret)

    def get_data(self, channel_id: str) -> dict:
        if channel_id.startswith("EVENT"):
            prefix = ""
        else:
            prefix = "" if channel_id != "SBS" and int(channel_id[1:]) < 21 else "virtual/"
        url = f"https://apis.sbs.co.kr/play-api/1.0/onair/{prefix}channel/{channel_id}?jwt-token=&platform=pcweb&service=&absolute_show=&ssl=Y&rscuse=&v_type=2&protocol=hls&extra="
        data = self.apisess.get(url).json()
        return data

    def __get_playlist(self, channel_id: str) -> str:
        data = self.get_data(channel_id)
        url = data["onair"]["source"]["mediasource"]["mediaurl"]  # root playlist url
        self.expires_in(url)  # debug
        data = self.plsess.get(url).text  # root playlist
        for line in data.splitlines():
            if line.startswith("chunklist.m3u8"):
                return url.split("playlist.m3u8")[0] + line
        return None

    def get_url(self, channel_id: str, mode: str, quality: str = None) -> Tuple[str, str]:
        return "return_after_read", self.get_playlist(channel_id)

    def repack_playlist(self, url: str, mode: str = None) -> str:
        data = self.plsess.get(url).text
        return self.sub_ts(data, url.split("chunklist.m3u8")[0])
