import time
from collections import OrderedDict
from datetime import datetime

from plugin import F  # pylint: disable=import-error

SystemModelSetting = F.SystemModelSetting

# local
from .setup import P
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


class LogicKlive:
    source_list: OrderedDict = None
    channel_list: list = None

    @staticmethod
    def __get_channel_list():
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
            for _ in range(3):
                tmp = source.get_channel_list()
                if len(tmp) != 0:
                    break
                time.sleep(3)
            logger.debug("%-10s: %s", source_id, len(tmp))
            for t in tmp:
                t.current = t.current.replace("<", "&lt;").replace(">", "&gt;")
                channel_list.append(t)
        LogicKlive.source_list = OrderedDict(source_list)
        LogicKlive.channel_list = channel_list
        ModelSetting.set("channel_list_updated_at", datetime.now().isoformat())

    @staticmethod
    def should_reload_channel_list(reload) -> bool:
        if LogicKlive.channel_list is None or reload:
            return True
        updated_at = datetime.fromisoformat(ModelSetting.get("channel_list_updated_at"))
        if (datetime.now() - updated_at).total_seconds() > ModelSetting.get_int("channel_list_max_age") * 60:
            return True
        return False

    @staticmethod
    def get_channel_list(reload=False):
        try:
            if LogicKlive.should_reload_channel_list(reload=reload):
                LogicKlive.__get_channel_list()
        except Exception:
            logger.exception("채널 목록을 얻는 중 예외:")
        return LogicKlive.channel_list

    @staticmethod
    def get_channel(source, channel_id):
        c = [x for x in LogicKlive.get_channel_list() if x.source == source and x.channel_id == channel_id]
        if len(c) == 1:
            return c[0]
        logger.warning("찾는 채널이 없거나 유니크 하지 않습니다: len(c)=%d", len(c))
        return None

    @staticmethod
    def get_url(source, channel_id, mode, quality=None):
        try:
            if LogicKlive.source_list is None:
                LogicKlive.get_channel_list()
            if quality is None or quality == "default":
                if source in ["wavve", "tving"]:
                    quality = ModelSetting.get(f"{source}_quality")
            return LogicKlive.source_list[source].get_url(channel_id, mode, quality=quality)
        except Exception:
            logger.exception("Streaming URL을 얻는 중 예외:")

    @staticmethod
    def get_return_data(source, url, mode):
        try:
            return LogicKlive.source_list[source].get_return_data(url, mode=mode)
        except Exception:
            logger.exception("Streaming URL을 분석 중 예외:")

    @staticmethod
    def get_m3uall():
        idx = 1
        m3u = ["#EXTM3U\n"]
        try:
            apikey = None
            if SystemModelSetting.get_bool("use_apikey"):
                apikey = SystemModelSetting.get("apikey")
            ddns = SystemModelSetting.get("ddns")
            for c in LogicKlive.get_channel_list():
                url = c.url(apikey=apikey, ddns=ddns)
                if c.is_drm_channel:
                    url = url.replace("url.m3u8", "url.mpd")
                m3u.append(c.as_m3u(url, idx))
                idx += 1
        except Exception:
            logger.exception("Exception:")
        return "".join(m3u)
