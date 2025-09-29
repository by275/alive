from collections import OrderedDict

from .model import ChannelItem
from .setup import P
from .source_base import SourceBase

logger = P.logger
package_name = P.package_name
ModelSetting = P.ModelSetting


class SourceFixURL(SourceBase):
    source_id = "fix_url"

    def load_channels(self) -> None:
        ret = []
        for cid, channels in self.load_channel_source().items():
            try:
                if not channels.get("use", True):
                    continue
                if not (name := channels.get("name") or ""):
                    logger.warning("채널 이름이 유효하지 않음: %s: %s", cid, channels)
                    continue
                if not (url := channels.get("url") or ""):
                    logger.warning("스트리밍 URL이 유효하지 않음: %s: %s", cid, channels)
                    continue
                kwargs = {"source": self.source_id, "channel_id": cid, "name": name, "url": url}
                kwargs["icon"] = channels.get("icon")
                kwargs["is_tv"] = channels.get("is_tv", True)
                ret.append(ChannelItem(**kwargs))
            except Exception:
                logger.exception("채널 분석 중 예외: %s: %s", cid, channels)
        self.channels = OrderedDict((c.channel_id, c) for c in ret)

    def get_url(self, channel_id: str) -> str:
        return self.channels[channel_id].url

    def make_m3u8(self, channel_id: str, mode: str, quality: str) -> tuple[str, str | dict]:
        url = self.get_url(channel_id)
        return "redirect", url
