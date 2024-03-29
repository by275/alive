from collections import OrderedDict
from html import unescape
from pathlib import Path
from typing import Tuple
from urllib.parse import quote

from support import SupportSC  # pylint: disable=import-error

from .model import ChannelItem, ProgramItem
from .setup import P
from .source_base import SourceBase, ttl_cache

logger = P.logger
package_name = P.package_name
ModelSetting = P.ModelSetting


class SourceWavve(SourceBase):
    source_id = "wavve"
    mod = None

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
        self.plsess = self.new_session(headers=self.mod.headers, proxies=self.mod.proxies)
        # cached playlist url
        if self.mod.session.headers.get("wavve-credential") != "none":
            ttl = 60 * 60 * 24  # 1일
        else:
            ttl = 60 * 10  # 10분
        self.get_m3u8 = ttl_cache(ttl)(self.__get_m3u8)

    def load_support_module(self):
        if Path(__file__).with_name("wavve.py").is_file():
            from .wavve import SupportWavve as mod
        else:
            mod = SupportSC.load_module_f(__file__, "wavve").SupportWavve
        from support_site.setup import P as SS  # pylint: disable=import-error

        mod.initialize(
            SS.ModelSetting.get("site_wavve_credential"),
            SS.ModelSetting.get_bool("site_wavve_use_proxy"),
            SS.ModelSetting.get("site_wavve_proxy_url"),
        )
        return mod

    def get_channel_list(self) -> None:
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
        self.channel_list = OrderedDict(ret)

    def __get_m3u8(self, channel_id: str, quality: str) -> str:
        """returns playlist url from streaming data

        새로운 playlist는 최신의/연속된 MEDIA SEQUENCE를 보장할 수 없다. (Error: Received stale playlist)
        따라서 한 번 얻은 playlist url을 최대한 유지해야 한다. (cache를 사용하는 이유)
        """
        data = self.mod.streaming("live", channel_id, quality)
        # 2022-01-10 라디오. 대충 함 by soju6jan
        # if data['quality'] == '100p' or data['qualities']['list'][0]['name'] == '오디오모드':
        #     url = data['playurl'].replace('/100/100', '/100') + f"/live.m3u8{data['debug']['orgurl'].split('.m3u8')[1]}"
        assert (url := data.get("playurl")) is not None, "Playlist URL is None!"
        self.expires_in(url)  # debug
        return url

    def get_url(self, channel_id: str, mode: str, quality: str = None) -> Tuple[str, str]:
        url = self.get_m3u8(channel_id, quality)

        if ModelSetting.get("wavve_streaming_type") == "redirect":
            if mode != "web_play":  # CORS issue
                return "redirect", url
        return "return_after_read", url

    def repack_m3u8(self, url: str, mode: str = None) -> str:
        data = self.plsess.get(url).text
        data = self.sub_ts(data, url.split(".m3u8")[0].rsplit("/", 1)[0] + "/")
        if ModelSetting.get("wavve_streaming_type") == "direct":
            if mode != "web_play":  # CORS issue
                return data
        return self.relay_ts(data, proxy=self.mod.proxy)
