import time
import traceback
from collections import OrderedDict

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

M3U_FORMAT = '#EXTINF:-1 tvg-id="%s" tvg-name="%s" tvg-logo="%s" group-title="%s" tvg-chno="%s" tvh-chnum="%s",%s\n%s\n'
M3U_RADIO_FORMAT = '#EXTINF:-1 tvg-id="%s" tvg-name="%s" tvg-logo="%s" group-title="%s" radio="true" tvg-chno="%s" tvh-chnum="%s",%s\n%s\n'

cate_change = {
    "wavve": "웨이브",
    "tving": "티빙",
    "youtubedl": "YoutubeDL",
    "streamlink": "StreamLink",
    "navertv": "네이버TV",
    "kakaotv": "카카오TV",
    "fix_url": "고정주소",
    "kbs": "KBS",
    "sbs": "SBS",
    "mbc": "MBC",
}


class LogicKlive:
    source_list: OrderedDict = None
    channel_list: list = None

    @staticmethod
    def channel_load_from_site():
        source_list, channel_list = [], []
        try:
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

            for source_name, source in source_list:
                for _ in range(3):
                    tmp = source.get_channel_list()
                    if len(tmp) != 0:
                        break
                    time.sleep(3)
                logger.debug("%-10s: %s", source_name, len(tmp))
                for t in tmp:
                    t.current = t.current.replace("<", "&lt;").replace(">", "&gt;")
                    channel_list.append(t)
        except Exception as e:
            logger.error("Exception:%s", e)
            logger.error(traceback.format_exc())
        else:
            LogicKlive.source_list = OrderedDict(source_list)
            LogicKlive.channel_list = channel_list

    @staticmethod
    def get_channel_list(from_site=False):
        try:
            if LogicKlive.channel_list is None or from_site:
                LogicKlive.channel_load_from_site()
            return LogicKlive.channel_list
        except Exception:
            logger.exception("채널 목록을 얻는 중 예외:")
            return []

    @staticmethod
    def get_url(source, channel_id, mode, quality=None):
        try:
            if LogicKlive.source_list is None:
                LogicKlive.channel_load_from_site()
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
            url_base = f'{SystemModelSetting.get("ddns")}/{package_name}'
            for c in LogicKlive.get_channel_list():
                url = url_base + f"/api/url.m3u8?m=url&s={c.source}&i={c.channel_id}"
                if c.is_drm_channel:
                    url = url.replace("url.m3u8", "url.mpd")
                if apikey is not None:
                    url += f"&apikey={apikey}"
                data = (c.title, c.title, c.icon, cate_change[c.source], idx, idx, c.title, url)
                if c.is_tv:
                    m3u.append(M3U_FORMAT % data)
                else:
                    m3u.append(M3U_RADIO_FORMAT % data)
                idx += 1
        except Exception:
            logger.exception("Exception:")
        return "".join(m3u)
