from collections import OrderedDict

from .model import ChannelItem
from .setup import P
from .source_base import SourceBase, URLCacher

logger = P.logger
package_name = P.package_name
ModelSetting = P.ModelSetting


class SourceStreamlink(SourceBase):
    source_id = "streamlink"
    ttl = 60 * 60 * 1  # 1시간 (youtube는 6시간)

    @classmethod
    def streamlink_ver(cls) -> str | None:
        try:
            import streamlink  # type: ignore # pylint: disable=import-error

            return streamlink.__version__
        except ImportError:
            return None

    def __init__(self):
        try:
            from streamlink import Streamlink  # type: ignore # pylint: disable=import-error
        except ImportError:
            logger.error("streamlink 패키지가 필요합니다.")
            return
        # session for streamlink
        options = None
        if ModelSetting.get_bool("streamlink_use_proxy"):
            options = {"http-proxy": ModelSetting.get("streamlink_proxy_url")}
        self.slsess = Streamlink(options=options)
        # cached streamlink stream
        self.get_stream = URLCacher(self.ttl)(self.__get_stream)

    def load_channels(self) -> None:
        ret = []
        for item in map(str.strip, ModelSetting.get(f"{self.source_id}_list").splitlines()):
            if not item:
                continue
            if len(tmp := item.split("|")) == 3:
                (cid, cname, url), quality = tmp, ""
            elif len(tmp) == 4:
                cid, cname, url, quality = tmp
            else:
                continue
            c = ChannelItem(self.source_id, cid, cname, None, True)
            c.url = url
            c.quality = quality.strip() or None
            ret.append(c)
        self.channels = OrderedDict((c.channel_id, c) for c in ret)

    def __get_stream(self, channel_id: str, quality: str):
        url = (c := self.channels[channel_id]).url
        if quality in [None, "default"]:
            quality = c.quality or "best"
        streams = self.slsess.streams(url)
        s = streams.get(quality)
        logger.info("using %r among %s", quality, list(streams))
        return s

    def open_stream(self, stream) -> str:
        reqargs = stream.session.http.valid_request_args(**stream.args)
        reqargs.setdefault("method", "GET")
        timeout = stream.session.options.get("stream-timeout")
        res = stream.session.http.request(
            timeout=timeout,
            **reqargs,
        )
        return res.text

    def make_m3u8(self, channel_id: str, mode: str, quality: str) -> tuple[str, str]:
        stype = "direct" if mode == "web_play" else ModelSetting.get("streamlink_streaming_type")
        stream = self.get_stream(channel_id, quality)
        if stype == "stream":
            return stype, stream
        if stype == "redirect":
            from streamlink.stream.hls import MuxedHLSStream  # type: ignore # pylint: disable=import-error

            if isinstance(stream, MuxedHLSStream):
                return stype, stream.to_manifest_url()
            return stype, stream.url
        if stype == "direct":
            return stype, self.open_stream(stream)
        raise NotImplementedError(f"잘못된 스트리밍 타입: {stype}")
