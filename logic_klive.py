import time
from collections import OrderedDict
from datetime import datetime
from typing import List, Tuple, Type

from plugin import F  # pylint: disable=import-error

from .model import ChannelItem
from .setup import P
from .source_base import SourceBase
from .source_fix_url import SourceFixURL
from .source_kakaotv import SourceKakaotv
from .source_kbs import SourceKBS
from .source_mbc import SourceMBC
from .source_navertv import SourceNavertv
from .source_sbs import SourceSBS
from .source_streamlink import SourceStreamlink
from .source_tving import SourceTving
from .source_wavve import SourceWavve
from .source_youtubedl import SourceYoutubedl

logger = P.logger
package_name = P.package_name
ModelSetting = P.ModelSetting
SystemModelSetting = F.SystemModelSetting


class LogicKlive:
    source_list: OrderedDict[str, Type[SourceBase]] = OrderedDict()
    channel_list: OrderedDict[str, OrderedDict[str, ChannelItem]] = OrderedDict()

    @classmethod
    def __get_channel_list(cls) -> None:
        source_list, channel_list = [], []

        if ModelSetting.get_bool("use_wavve"):
            source = SourceWavve()
            if source.mod is not None:
                source_list.append(["wavve", source])
        if ModelSetting.get_bool("use_tving"):
            source = SourceTving()
            if source.mod is not None:
                source_list.append(["tving", source])
        if ModelSetting.get_bool("use_kbs"):
            source_list.append(["kbs", SourceKBS()])
        if ModelSetting.get_bool("use_mbc"):
            source_list.append(["mbc", SourceMBC()])
        if ModelSetting.get_bool("use_sbs"):
            source_list.append(["sbs", SourceSBS()])
        if ModelSetting.get_bool("use_youtubedl"):
            source = SourceYoutubedl()
            if source.is_installed():
                source_list.append(["youtubedl", source])
        if ModelSetting.get_bool("use_streamlink"):
            source = SourceStreamlink()
            if source.is_installed():
                source_list.append(["streamlink", source])
        if ModelSetting.get_bool("use_navertv"):
            source_list.append(["navertv", SourceNavertv()])
        if ModelSetting.get_bool("use_kakaotv"):
            source_list.append(["kakaotv", SourceKakaotv()])
        if ModelSetting.get_bool("use_fix_url"):
            source_list.append(["fix_url", SourceFixURL()])

        for source_id, source in source_list:
            for _ in range(3):  # 재시도?
                source_channels = source.get_channel_list()
                if len(source_channels) != 0:
                    break
                time.sleep(3)
            logger.debug("%-10s: %s", source_id, len(source_channels))
            channel_list.append([source_id, source_channels])
        cls.source_list = OrderedDict(source_list)
        cls.channel_list = OrderedDict(channel_list)
        ModelSetting.set("channel_list_updated_at", datetime.now().isoformat())

    @classmethod
    def should_reload_channel_list(cls, reload: bool) -> bool:
        if not cls.channel_list or reload:
            return True
        channel_list_max_age = ModelSetting.get_int("channel_list_max_age")
        if channel_list_max_age <= 0:
            return False
        updated_at = datetime.fromisoformat(ModelSetting.get("channel_list_updated_at"))
        if (datetime.now() - updated_at).total_seconds() > channel_list_max_age * 60:
            return True
        return False

    @classmethod
    def get_channel_list(cls, reload: bool = False) -> List[ChannelItem]:
        ret = []
        try:
            if cls.should_reload_channel_list(reload=reload):
                cls.__get_channel_list()
            for ch in cls.channel_list.values():
                ret.extend(ch.values())
        except Exception:
            logger.exception("채널 목록을 얻는 중 예외:")
        return ret

    @classmethod
    def get_url(cls, source: str, channel_id: str, mode: str, quality: str = None) -> Tuple[str, str]:
        try:
            if not cls.source_list:
                cls.get_channel_list()
            if quality is None or quality == "default":
                if source in ["wavve", "tving"]:
                    quality = ModelSetting.get(f"{source}_quality")
            return cls.source_list[source].get_url(channel_id, mode, quality=quality)
        except Exception:
            logger.exception("Playlist URL을 얻는 중 예외:")
            return None, None

    @classmethod
    def repack_playlist(cls, source: str, url: str, mode: str) -> str:
        try:
            return cls.source_list[source].repack_playlist(url, mode=mode)
        except Exception:
            logger.exception("Playlist 수정 중 예외:")
            return None

    @classmethod
    def get_m3uall(cls):
        idx = 1
        m3u = ["#EXTM3U\n"]
        try:
            apikey = None
            if SystemModelSetting.get_bool("use_apikey"):
                apikey = SystemModelSetting.get("apikey")
            ddns = SystemModelSetting.get("ddns")
            for c in cls.get_channel_list():
                url = c.svc_url(apikey=apikey, ddns=ddns)
                m3u.append(c.as_m3u(url=url, tvg_chno=idx, tvh_chnum=idx))
                idx += 1
        except Exception:
            logger.exception("Exception:")
        return "".join(m3u)
