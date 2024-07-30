from collections import OrderedDict
from html import unescape
from urllib.parse import quote

from .model import ChannelItem, ProgramItem
from .setup import P
from .source_base import SourceBase, ttl_cache

logger = P.logger
package_name = P.package_name
ModelSetting = P.ModelSetting


class SourceWavve(SourceBase):
    source_id = "wavve"
    mod = None
    default_quality: str = ModelSetting.get("wavve_quality")

    def __init__(self):
        if self.mod is not None:
            return
        try:
            self.mod = self.load_support_module()
        except (ImportError, ModuleNotFoundError):
            logger.error("support site 플러그인이 필요합니다.")
        except Exception:
            logger.exception("Support Module 로딩 중 예외:")
        if self.mod is None:
            return
        # session for playlists
        plproxy = self.mod.proxy_url if ModelSetting.get_bool("wavve_use_proxy_for_playlist") else None
        self.plsess = self.new_session(headers=self.mod.session.headers, proxy_url=plproxy)
        # cached playlist url
        if self.mod.credential != "none":
            ttl = 60 * 60 * 24  # 1일
        else:
            ttl = 60 * 2  # 2분
        self.get_m3u8 = ttl_cache(ttl)(self.__get_m3u8)

    def load_support_module(self):
        from support_site import SupportWavve as SW

        return SW

    def load_channels(self) -> None:
        ret = []
        data = self.mod.live_all_channels()
        for item in data["list"]:
            try:
                p = ProgramItem(
                    program_id=item["programid"],
                    title=unescape(item["title"].strip()),
                    image="https://" + quote(item["image"]) if item["image"] != "" else None,
                    stime=item["starttime"],
                    etime=item["endtime"],
                    onair=item["license"] == "y",
                    targetage=int(item["targetage"] or "0"),
                )
                c = ChannelItem(
                    self.source_id,
                    item["channelid"],
                    item["channelname"],
                    "https://" + quote(item["tvimage"]) if item["tvimage"] != "" else "",
                    item["type"] == "video",
                    program=p,
                )
                ret.append([c.channel_id, c])
            except Exception:
                logger.exception("라이브 채널 분석 중 예외: %s", item)
        self.channels = OrderedDict(ret)

    def __get_m3u8(self, channel_id: str, quality: str) -> str:
        """returns playlist url from streaming data

        새로운 playlist는 최신의/연속된 MEDIA SEQUENCE를 보장할 수 없다. (Error: Received stale playlist)
        따라서 한 번 얻은 playlist url을 최대한 유지해야 한다. (cache를 사용하는 이유)
        """
        if quality in [None, "default"]:
            quality = self.default_quality
        data = self.mod.streaming("live", channel_id, quality)
        # 2022-01-10 라디오. 대충 함 by soju6jan
        # if data['quality'] == '100p' or data['qualities']['list'][0]['name'] == '오디오모드':
        #     url = data['playurl'].replace('/100/100', '/100') + f"/live.m3u8{data['debug']['orgurl'].split('.m3u8')[1]}"
        return data["play_info"].get("hls")

    def repack_m3u8(self, url: str) -> str:
        data = self.plsess.get(url).text
        data = self.sub_ts(data, url.split(".m3u8")[0].rsplit("/", 1)[0] + "/")
        return data

    def make_m3u8(self, channel_id: str, mode: str, quality: str) -> tuple[str, str]:
        stype = "proxy" if mode == "web_play" else ModelSetting.get("wavve_streaming_type")
        url = self.get_m3u8(channel_id, quality)
        if stype == "redirect":
            return stype, url
        data = self.repack_m3u8(url)
        if stype == "direct":
            return stype, data
        return stype, self.relay_ts(data, self.source_id, proxy=self.plsess.proxies.get("http"))  # proxy, web_play
