from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Literal, Type

from plugin import F  # pylint: disable=import-error

from .model import ChannelItem
from .setup import P
from .source_base import SourceBase
from .source_fix_url import SourceFixURL
from .source_kbs import SourceKBS
from .source_mbc import SourceMBC
from .source_sbs import SourceSBS
from .source_streamlink import SourceStreamlink
from .source_tving import SourceTving
from .source_wavve import SourceWavve

logger = P.logger
package_name = P.package_name
ModelSetting = P.ModelSetting
SystemModelSetting = F.SystemModelSetting


class LogicKlive:
    sources: OrderedDict[str, Type[SourceBase]] = OrderedDict()

    @classmethod
    def __load_sources(cls) -> None:
        srcs = []

        if ModelSetting.get_bool("use_wavve"):
            if (src := SourceWavve()).mod is not None:
                srcs.append(src)
        if ModelSetting.get_bool("use_tving"):
            if (src := SourceTving()).mod is not None:
                srcs.append(src)
        if ModelSetting.get_bool("use_kbs"):
            srcs.append(SourceKBS())
        if ModelSetting.get_bool("use_mbc"):
            srcs.append(SourceMBC())
        if ModelSetting.get_bool("use_sbs"):
            srcs.append(SourceSBS())
        if ModelSetting.get_bool("use_streamlink"):
            if (src := SourceStreamlink()).is_installed:
                srcs.append(src)
        if ModelSetting.get_bool("use_fix_url"):
            srcs.append(SourceFixURL())

        cls.sources = OrderedDict([s.source_id, s] for s in srcs)

    @classmethod
    def __load_channels(cls) -> None:
        with ThreadPoolExecutor(max_workers=5) as exe:
            f2s = {exe.submit(s.load_channels): s for s in cls.sources.values()}
            for f in as_completed(f2s):
                logger.debug("%-10s: %s", f2s[f].source_id, len(f2s[f].channels))

        ModelSetting.set("channel_list_updated_at", datetime.now().isoformat())

    @classmethod
    def should_reload_channels(cls, reload: bool) -> bool:
        if not any(s.channels for s in cls.sources.values()) or reload:
            return True
        channel_list_max_age = ModelSetting.get_int("channel_list_max_age")
        if channel_list_max_age <= 0:
            return False
        updated_at = datetime.fromisoformat(ModelSetting.get("channel_list_updated_at"))
        if (datetime.now() - updated_at).total_seconds() > channel_list_max_age * 60:
            return True
        return False

    @classmethod
    def all_channels(cls, reload: Literal["soft", "hard"] = None) -> list[ChannelItem]:
        ret = []
        try:
            if not cls.sources or reload == "hard":
                cls.__load_sources()
            if cls.should_reload_channels(reload in ["soft", "hard"]):
                cls.__load_channels()
            for s in cls.sources.values():
                ret.extend(s.channels.values())
        except Exception:
            logger.exception("채널 목록을 얻는 중 예외:")
        return ret

    @classmethod
    def make_m3u8(cls, source: str, channel_id: str, mode: str, quality: str = None) -> tuple[str, str | dict]:
        try:
            cls.all_channels()  # api에서 가장 먼저 call하는 entrypoint기 때문에...
            return cls.sources[source].make_m3u8(channel_id, mode, quality)
        except Exception:
            logger.exception("m3u8 응답을 작성 중 예외:")
            return None, None

    @classmethod
    def get_m3uall(cls):
        idx = 1
        m3u = ["#EXTM3U\n"]
        try:
            apikey = None
            if SystemModelSetting.get_bool("use_apikey"):
                apikey = SystemModelSetting.get("apikey")
            ddns = SystemModelSetting.get("ddns")
            for c in cls.all_channels():
                url = c.svc_url(apikey=apikey, ddns=ddns)
                m3u.append(c.as_m3u(url=url, tvg_chno=idx, tvh_chnum=idx))
                idx += 1
        except Exception:
            logger.exception("Exception:")
        return "".join(m3u)
