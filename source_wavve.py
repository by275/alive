from collections import OrderedDict
from html import unescape
from urllib.parse import quote

from .model import ChannelItem, ProgramItem
from .setup import P
from .source_base import SourceBase, URLCacher

logger = P.logger
package_name = P.package_name
ModelSetting = P.ModelSetting


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

    def _map_channel(self, old: dict, new: dict) -> None:
        """map new api channel to old one"""
        live = new.get("live", {})
        old.update(
            {
                "channelname": live.get("name") or "",
                "title": live.get("program_title") or "",
                "image": live.get("thumbnail_url") or "",
                "tvimage": live.get("main_image") or "",
                "targetage": new.get("personal", {}).get("targetage") or "",
            }
        )

    def _upgrade_channels(self, data: dict) -> None:
        if not (ctx_list := data["context_list"]):
            logger.warning("v2 API로부터 빈 채널 목록")
            return
        new_dict = {cid: c for c in ctx_list if (cid := c.get("context_id"))}
        old_list = []
        for old in data["list"]:
            try:
                if not (new := new_dict.pop(old["channelid"], None)):
                    continue  # 2025.11.20 현재 2개 채널 타요TV 뽀로로TV
                self._map_channel(old, new)
            except Exception:
                logger.exception("채널 업데이트 중 예외: old=%s", old)
            old_list.append(old)
        for newid, new in new_dict.items():
            old = {
                "channelid": newid,
                "programid": "",
                "type": "video",  # 다행히 새 채널들은 모두 video
                "starttime": "00:00",
                "endtime": "00:00",
                "license": "y",
            }
            self._map_channel(old, new)
            old_list.append(old)
        data["list"] = old_list

    def load_channels(self) -> None:
        ret = []
        data = self.mod.live_all_channels()
        try:
            self._upgrade_channels(data)
        except Exception:
            logger.exception("v2 API 로직 실패. 기존 데이터로 채널을 파싱합니다.")
        for item in data["list"]:
            try:
                p = ProgramItem(
                    program_id=item["programid"],
                    title=unescape(item["title"].strip()),
                    image="https://" + quote(item["image"]) if item["image"] != "" else None,
                    stime=item["starttime"],
                    etime=item["endtime"],
                    onair=item["license"] == "y",
                    targetage=int(item["targetage"] or "0"),
                )
                c = ChannelItem(
                    self.source_id,
                    item["channelid"],
                    item["channelname"],
                    "https://" + quote(item["tvimage"]) if item["tvimage"] != "" else "",
                    item["type"] == "video",
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
        if quality in [None, "default"]:
            quality = ModelSetting.get("wavve_quality")
        data = self.mod.streaming("live", channel_id, quality, isabr="y")
        return data["play_info"].get("hls")

    def make_m3u8(self, channel_id: str, mode: str, quality: str) -> tuple[str, str | dict]:
        stype = "proxy" if mode == "web_play" else ModelSetting.get("wavve_streaming_type")
        url = self.get_url(channel_id, quality)
        if stype == "redirect":
            return stype, url
        return stype, self.get_m3u8(url)  # direct, proxy(web_play)


old1 = {
    "isnextpagegroup": "n",
    "pagecount": "110",
    "count": "110",
    "list": [
        {
            "channelid": "M01",
            "channelname": "MBC",
            "programid": "",
            "title": "",
            "image": "image.cdn.wavve.com/live/thumbnail/M01.jpg",
            "tvimage": "",
            "type": "video",
            "price": "0",
            "starttime": "00:00",
            "endtime": "00:00",
            "playratio": "0.0",
            "license": "y",
            "livemarks": [],
            "targetage": "",
        }
    ],
}
new1 = {
    "description": "라이브 채널 밴드",
    "version": "1.0",
    "type": "live",
    "top_context": {"title": "LIVE 전체", "count": "121", "pagecount": "121"},
    "context_list": {
        "index": "0",
        "context_type": "live",
        "context_id": "C2101",
        "live": {
            "thumbnail_url": "image.cdn.wavve.com/live/thumbnail/C2101.jpg?timestamp=1763275776571",
            "main_image": "http://img.pooq.co.kr/BMS/Channelimage30/image/C2101.jpg",
            "logo_image": "https://image.wavve.com/channel_mgmt/image/C2101_logo_20250731141328.png",
            "square_image": "https://image.wavve.com/channel_mgmt/image/C2101_square_20250731141328.png",
            "bg_color": "#1A4880",
            "name": "YTN",
            "program_title": "YTN24",
            "ratings": "11.7",
            "button_text": "",
        },
        "tag": {"free": "free", "live": ""},
        "personal": {"targetage": "", "viewratio": "0.99"},
        "additional_information": {"info_url": "channelid=C2101", "play_url": "contentid=C2101", "rank": "1"},
    },
}
