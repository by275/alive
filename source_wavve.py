from collections import OrderedDict

from .model import ChannelItem, ProgramItem
from .setup import P
from .source_base import SourceBase, URLCacher

logger = P.logger
package_name = P.package_name
ModelSetting = P.ModelSetting

RADIO_CHANNELS = [
    "C2107",  # YTN 라디오
    "C2701",  # KISS - 최신인기가요
    "C2702",  # KISS - 당신의 발라드
    "C2703",  # KISS - 응답하라 7080
    "C2705",  # KISS - 2010년대 가요
    "C2706",  # KISS - 재즈 라운지
    "C2708",  # KISS - 클래식 산책
    "C2709",  # KISS - 듣기 편한 팝
    "C2710",  # KISS - 키스 인기 트로트
    "C2713",  # KISS - 탑골 K-POP
    "K07",  # KBS1RADIO
    "K08",  # KBSCOOLFM
    "M07",  # MBC 표준 FM
    "M08",  # MBC FM4U
]


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
        include_nonfree = ModelSetting.get_bool("wavve_include_nonfree")
        for item in data["context_list"]:
            try:
                if not include_nonfree and item["tag"]["free"] != "free":
                    continue
                channel_id = item["context_id"]
                live = item["live"]

                thumbnail = live["thumbnail_url"] or None
                if thumbnail and not thumbnail.startswith("http"):
                    thumbnail = "https://" + thumbnail
                main_image = live["main_image"] or None
                if main_image and not main_image.startswith("http"):
                    main_image = "https://" + main_image

                p = ProgramItem(
                    title=live["program_title"],
                    image=thumbnail,
                    targetage=int(item["personal"]["targetage"] or "0"),
                )
                c = ChannelItem(
                    self.source_id,
                    channel_id,
                    live["name"],
                    main_image,
                    channel_id not in RADIO_CHANNELS,
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
        if quality is None or quality == "default":
            quality = self.quality
        if quality == "auto":
            data = self.mod.streaming("live", channel_id, quality, isabr="y")
        else:
            data = self.mod.streaming("live", channel_id, quality, isabr="n")
        return data["play_info"]["hls"]

    def make_m3u8(self, channel_id: str, mode: str, quality: str) -> tuple[str, str | dict]:
        stype = "proxy" if mode == "web_play" else self.streaming_type
        url = self.get_url(channel_id, quality)
        if stype == "redirect":
            return stype, url
        if self.quality != "auto":
            return stype, self.repack_m3u8(url, stype)
        return stype, self.get_m3u8(url)  # direct, proxy(web_play)
