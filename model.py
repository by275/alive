from dataclasses import dataclass, asdict

from plugin import F  # pylint: disable=import-error

db = F.db

# local
from .setup import P

logger = P.logger
package_name = P.package_name


@dataclass
class ChannelItem:
    source: str
    channel_id: str
    title: str
    icon: str
    is_tv: bool

    current: str = ""
    is_include_custom: bool = False
    is_drm_channel: bool = False

    # json = db.Column(db.JSON)
    # created_time = db.Column(db.DateTime)

    # def __repr__(self):
    #     return repr(self.as_dict())

    def as_dict(self):
        return asdict(self)

    # def as_dict(self):
    #     ret = {x.name: getattr(self, x.name) for x in self.__table__.columns}
    #     ret["created_time"] = self.created_time.strftime("%m-%d %H:%M:%S") if ret["created_time"] is not None else None
    #     if self.json is not None:
    #         ret["json"] = json.loads(ret["json"])
    #     else:
    #         ret["json"] = {}
    #     return ret


@dataclass
class SimpleItem:
    id: str
    title: str
    url: str
    quality: str = None
