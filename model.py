from dataclasses import dataclass, asdict
from datetime import datetime, timedelta

from plugin import F  # pylint: disable=import-error

db = F.db
SystemModelSetting = F.SystemModelSetting

# local
from .setup import P

logger = P.logger
package_name = P.package_name

M3U_FORMAT = '#EXTINF:-1 tvg-id="%s" tvg-name="%s" tvg-logo="%s" group-title="%s" tvg-chno="%s" tvh-chnum="%s",%s\n%s\n'
M3U_RADIO_FORMAT = '#EXTINF:-1 tvg-id="%s" tvg-name="%s" tvg-logo="%s" group-title="%s" radio="true" tvg-chno="%s" tvh-chnum="%s",%s\n%s\n'

source_id2name = {
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
            if len(val) == 4:
                dt = datetime.strptime(val, "%H%M")
            elif len(val) == 5:
                dt = datetime.strptime(val, "%H:%M")
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

    url: str = None
    quality: str = None
    program: ProgramItem = ProgramItem()

    is_drm: bool = False  # DRM 채널 / 현재 tving만

    @property
    def source_name(self):
        return source_id2name.get(self.source, None)

    def svc_url(self, apikey=None, ddns=None, mode="url"):
        if apikey is None:
            if SystemModelSetting.get_bool("use_apikey"):
                apikey = SystemModelSetting.get("apikey")

        url_base = f'{ddns or SystemModelSetting.get("ddns")}/{package_name}'
        url = url_base + f"/api/url.m3u8?m={mode}&s={self.source}&i={self.channel_id}"
        if apikey is not None:
            url += f"&apikey={apikey}"
        return url

    # json = db.Column(db.JSON)
    # created_time = db.Column(db.DateTime)

    # def __repr__(self):
    #     return repr(self.as_dict())

    def as_dict(self):
        return {**asdict(self), "source_name": self.source_name}

    def as_m3u(self, url=None, idx=0):
        if url is None:
            url = self.svc_url()
        data = (self.name, self.name, self.icon, self.source_name, idx, idx, self.name, url)
        if self.is_tv:
            return M3U_FORMAT % data
        return M3U_RADIO_FORMAT % data

    # def as_dict(self):
    #     ret = {x.name: getattr(self, x.name) for x in self.__table__.columns}
    #     ret["created_time"] = self.created_time.strftime("%m-%d %H:%M:%S") if ret["created_time"] is not None else None
    #     if self.json is not None:
    #         ret["json"] = json.loads(ret["json"])
    #     else:
    #         ret["json"] = {}
    #     return ret
