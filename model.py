from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from urllib.parse import urlencode

from flask import request
from plugin import F  # type: ignore # pylint: disable=import-error

db = F.db
SystemModelSetting = F.SystemModelSetting

# local
from .setup import P, default_headers

logger = P.logger
package_name = P.package_name

M3U_FORMAT = '#EXTINF:-1 tvg-id="%s" tvg-name="%s" tvg-logo="%s" group-title="%s" tvg-chno="%s" tvh-chnum="%s",%s\n%s\n'
M3U_RADIO_FORMAT = '#EXTINF:-1 tvg-id="%s" tvg-name="%s" tvg-logo="%s" group-title="%s" radio="true" tvg-chno="%s" tvh-chnum="%s",%s\n%s\n'

source_id2name = {
    "wavve": "웨이브",
    "tving": "티빙",
    "kbs": "KBS",
    "mbc": "MBC",
    "sbs": "SBS",
    "streamlink": "StreamLink",
    "fix_url": "고정주소",
    "spotv": "SPOTV",
    "bot": "BOT",
}
source_id2char = {
    "wavve": "w",
    "tving": "t",
    "kbs": "k",
    "mbc": "m",
    "sbs": "s",
    "streamlink": "l",
    "fix_url": "f",
    "spotv": "p",
    "bot": "b",
}
circled_alphabet = "ⒶⒷⒸⒹⒺⒻⒼⒽⒾⒿⓀⓁⓂⓃⓄⓅⓆⓇⓈⓉⓊⓋⓌⓍⓎⓏ"


@dataclass
class ProgramItem:
    program_id: str = None
    title: str = ""
    image: str = None
    stime: datetime = None
    etime: datetime = None
    onair: bool = True  # 저작권 등의 이유로 방송 송출이 안되는 프로그램 표시
    targetage: int = 0

    def __setattr__(self, prop, val):
        if prop in ["stime", "etime"] and val is not None:
            if len(val) in [4, 5]:
                val = val.replace(":", "")
                if val[:2] == "24":
                    val = "00" + val[2:]
                dt = datetime.strptime(val, "%H%M")
            elif len(val) == 14:
                dt = datetime.strptime(val, "%Y%m%d%H%M%S")
            else:
                raise NotImplementedError(f"Unknown datetime format: {val}")
            now = datetime.now().astimezone()
            val = now.replace(hour=dt.hour, minute=dt.minute, second=0, microsecond=0)
            if prop == "stime" and val > now + timedelta(minutes=5):
                val += timedelta(days=-1)
            if prop == "etime" and val < now - timedelta(minutes=5):
                val += timedelta(days=1)
        super().__setattr__(prop, val)


@dataclass
class ChannelItem:
    source: str  # source{_id}
    channel_id: str
    name: str  # {channel_}name
    icon: str
    is_tv: bool
    is_drm: bool = False  # DRM 채널 / 현재 tving만

    url: str = None
    quality: str = None
    program: ProgramItem = field(default_factory=ProgramItem)

    @property
    def source_name(self):
        return source_id2name.get(self.source, None)

    @property
    def source_char(self):
        char = source_id2char.get(self.source, "x").lower()
        return circled_alphabet[ord(char) - ord("a")]

    def svc_url(self, apikey=None, ddns=None, mode="url", for_tvh=False):
        if apikey is None and SystemModelSetting.get_bool("use_apikey"):
            apikey = SystemModelSetting.get("apikey")

        url_base = f'{ddns or SystemModelSetting.get("ddns")}/{package_name}'
        params = {"m": mode, "s": self.source, "i": self.channel_id}
        if apikey is not None:
            params["apikey"] = apikey

        path = "url.mpd" if self.is_drm else "url.m3u8"
        url = f"{url_base}/api/{path}?{urlencode(params)}"
        if not F.config["run_celery"]:  # epg에서 m3u 요청시 request 사용으로 인해 문제발생
            try:
                if self.is_drm and (
                    request.headers.get("User-Agent", "").lower().startswith("tivimate")
                    or request.headers.get("User-Agent", "").lower().startswith("kodi")
                    or request.headers.get("User-Agent", "").lower().startswith("iptvplay")
                ):
                    from .logic_klive import LogicKlive

                    source_ins = LogicKlive.get_source(self.source)
                    ret = source_ins.make_m3u8(self.channel_id, "kodi", "")
                    url = ret[1]
            except Exception as e:
                logger.exception("Error while making drm m3u8 for %s: %s", self.channel_id, e)
                return "error", str(e)

        if for_tvh:
            return (
                f'pipe://ffmpeg -user_agent "{default_headers["user-agent"]}" -loglevel quiet -i "{url}" -c copy '
                f'-metadata service_provider=flaskfarm_alive -metadata service_name="{self.name}" '
                f"-c:v copy -c:a aac -b:a 128k -f mpegts -tune zerolatency pipe:1"
            )
        return url

    def as_dict(self):
        return {**asdict(self), "source_name": self.source_name}

    def as_m3u(self, **kwargs):
        tvg_id = kwargs.setdefault("tvg_id", self.name)
        tvg_name = kwargs.setdefault("tvg_name", self.name)
        tvg_logo = kwargs.setdefault("tvg_logo", self.icon)
        group_title = kwargs.setdefault("group_title", self.source_name)
        tvg_chno = kwargs.setdefault("tvg_chno", 0)
        tvh_chnum = kwargs.setdefault("tvh_chnum", 0)
        display_name = kwargs.setdefault("display_name", self.name)
        url = kwargs.setdefault("url", self.svc_url())
        data = (tvg_id, tvg_name, tvg_logo, group_title, tvg_chno, tvh_chnum, display_name, url)
        if self.is_tv:
            return M3U_FORMAT % data
        return M3U_RADIO_FORMAT % data
