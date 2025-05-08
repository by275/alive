from collections import OrderedDict
from html import unescape
from urllib.parse import quote

from .model import ChannelItem, ProgramItem
from .setup import P
from .source_base import SourceBase, URLCacher

logger = P.logger
package_name = P.package_name
ModelSetting = P.ModelSetting


class SourceWavve(SourceBase):
    source_id = "wavve"
    mod = None
    ttl = 60 * 2  # 2분

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
        # dynamic ttl
        if self.mod.credential != "none":
            self.ttl = 60 * 60 * 24  # 1일
        # caching master playlist url
        self.get_url = URLCacher(self.ttl)(self.__get_url)

    def load_support_module(self):
        from support_site import SupportWavve as SW  # type: ignore

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
                ret.append(c)
            except Exception:
                logger.exception("라이브 채널 분석 중 예외: %s", item)
        self.channels = OrderedDict((c.channel_id, c) for c in ret)

    def __get_url(self, channel_id: str, quality: str) -> str:
        """returns m3u8 master playlist url from streaming data

        새로운 playlist는 최신의/연속된 MEDIA SEQUENCE를 보장할 수 없다. (Error: Received stale playlist)
        따라서 한 번 얻은 playlist url을 최대한 유지해야 한다. (cache를 사용하는 이유)
        """
        if quality in [None, "default"]:
            quality = ModelSetting.get("wavve_quality")
        data = self.mod.streaming("live", channel_id, quality, isabr="y")
        return data["play_info"].get("hls")

    def make_m3u8(self, channel_id: str, mode: str, quality: str) -> tuple[str, str | dict]:
        stype = "proxy" if mode == "web_play" else ModelSetting.get("wavve_streaming_type")
        url = self.get_url(channel_id, quality)
        if stype == "redirect":
            return stype, url
        return stype, self.get_m3u8(url)  # direct, proxy(web_play)
