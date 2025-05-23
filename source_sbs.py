from collections import OrderedDict

from .model import ChannelItem, ProgramItem
from .setup import P
from .source_base import SourceBase, URLCacher

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
        plproxy = proxy_url if ModelSetting.get_bool("sbs_use_proxy_for_playlist") else None
        self.plsess = self.new_session(proxy_url=plproxy)
        # caching master playlist url
        self.get_url = URLCacher(self.ttl)(self.__get_url)

    def load_channels(self) -> None:
        ret = []
        url_list = ["https://static.apis.sbs.co.kr/play-api/1.0/onair/channels"]
        if ModelSetting.get_bool("sbs_include_vod_ch"):
            url_list += ["https://static.apis.sbs.co.kr/play-api/1.0/onair/virtual/channels"]
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
                    ret.append(c)
                except Exception:
                    logger.exception("라이브 채널 분석 중 예외: %s", item)
        self.channels = OrderedDict((c.channel_id, c) for c in ret)

    def get_data(self, channel_id: str) -> dict:
        if channel_id.startswith("EVENT"):
            prefix = ""
        else:
            prefix = "virtual/"
            try:
                if int(channel_id[1:]) < 21:
                    prefix = ""
            except ValueError:
                pass
        url = f"https://apis.sbs.co.kr/play-api/1.0/onair/{prefix}channel/{channel_id}?v_type=2&platform=pcweb&protocol=hls&ssl=N&rscuse=&jwt-token=&sbsmain="
        data = self.apisess.get(url).json()
        return data

    def __get_url(self, channel_id: str) -> str:
        data = self.get_data(channel_id)
        return data["onair"]["source"]["mediasource"]["mediaurl"]  # master playlist url

    def make_m3u8(self, channel_id: str, mode: str, quality: str) -> tuple[str, str | dict]:
        stype = ModelSetting.get("sbs_streaming_type")
        url = self.get_url(channel_id)
        return stype, self.get_m3u8(url)  # direct, proxy
