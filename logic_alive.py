import xml.etree.ElementTree as ET
from copy import deepcopy
from datetime import datetime
from pathlib import Path

import requests
import yaml
import re
from plugin import F  # type: ignore # pylint: disable=import-error

SystemModelSetting = F.SystemModelSetting

# local
from .logic_klive import LogicKlive
from .setup import P

logger = P.logger
package_name = P.package_name
ModelSetting = P.ModelSetting


M3U_FORMAT = '#EXTINF:-1 tvg-id="%s" tvg-name="%s" tvg-logo="%s" group-title="%s" tvg-chno="%s" tvh-chnum="%s",%s\n%s\n'
M3U_RADIO_FORMAT = '#EXTINF:-1 tvg-id="%s" tvg-name="%s" tvg-logo="%s" group-title="%s" radio="true" tvg-chno="%s" tvh-chnum="%s",%s\n%s\n'


def is_name_same(a: str, b: str) -> bool:
    return a.replace(" ", "").lower() == b.replace(" ", "").lower()


def is_name_in(a: str, b: str) -> bool:
    return a.replace(" ", "").lower() in b.replace(" ", "").lower()


def find_channels_from_src(ch_info: dict, src_list: list) -> list:
    names = [ch_info["name"]] + ch_info.get("alias", [])
    return [m for m in src_list if any(is_name_same(m.name, x) for x in names)]


def sort_srcs(srcs: list, priority_list: list) -> list:
    src_known = [s for s in srcs if s.source_name in priority_list]
    src_unknown = [s for s in srcs if s.source_name not in priority_list]
    src_known.sort(key=lambda v: priority_list.index(v.source_name))
    return src_known + src_unknown


def get_source(ch: dict, priority_list: list):
    srcs = sort_srcs(ch["srcs"], priority_list)
    force = ch.get("force", "").lower()
    for src in srcs:
        if force and src.source_name.lower() == force:
            logger.debug("%-10s: 강제로 다음 소스를 선택: %s", ch["name"], src.source_name)
            return deepcopy(src), srcs
    for src in srcs:
        if not src.program.onair:
            logger.debug("%-10s: 현재 방송불가: %s", src.source, ch["name"])
            continue
        return deepcopy(src), srcs
    return deepcopy(srcs[0]), srcs


def get_src_item(ch: dict, priority_list: list, attrib: str):
    for src in sort_srcs(ch["srcs"], priority_list):
        if hasattr(src, attrib):
            return getattr(src, attrib)
    return ""


class LogicAlive:
    epg_names: list[str] = []
    group_list: list = []
    prefs: dict = {}

    @classmethod
    def load_prefs(cls) -> bool:
        file = Path(F.path_data).joinpath("db", "alive.yaml")
        with file.open("r", encoding="utf-8") as strm:
            prefs = yaml.full_load(strm.read())
        if prefs != cls.prefs:
            cls.prefs = prefs
            return True
        return False

    @classmethod
    def __get_epg_names(cls, epg_urls: list[str]) -> list[str]:
        epg_names = []
        for epg_url in epg_urls:
            try:
                root = ET.fromstring(requests.get(epg_url, timeout=30).text)
                epg_names += [c.find("display-name").text for c in root.findall("channel")]
            except Exception:
                logger.exception("epg로부터 채널 이름을 가져오는 중 예외: %s", epg_url)
        return epg_names

    @classmethod
    def get_epg_names(cls):
        prefs = cls.prefs.get("epg", {})
        epg_urls = prefs.setdefault("urls", [])
        if not epg_urls:
            return
        updated_at = datetime.fromisoformat(ModelSetting.get("epg_updated_at"))
        max_age = prefs.get("max_age", 60)
        if cls.epg_names and (datetime.now() - updated_at).total_seconds() < max_age * 60:
            return
        cls.epg_names = cls.__get_epg_names(epg_urls)
        ModelSetting.set("epg_updated_at", datetime.now().isoformat())

    @classmethod
    def __get_group_list(cls):
        channel_group = deepcopy(cls.prefs["channel_group"])
        cls.get_epg_names()

        #
        # check duplicates
        #
        known_channel_names = set()
        for group in channel_group:
            for channel in group.get("channels", []):
                channel_name = channel["name"]
                if channel_name in known_channel_names:
                    logger.warning("채널 이름에 중복이 있습니다: %s", channel_name)
                known_channel_names.add(channel_name)

        all_channels = LogicKlive.all_channels()
        src_tv = [c for c in all_channels if c.is_tv]
        src_radio = [c for c in all_channels if not c.is_tv]

        #
        # grouping available sources based on predefined channel_group
        #
        for group in channel_group:
            gtype = group["type"]
            gname = group["name"]
            radio = group.setdefault("radio", False)
            group.setdefault("no_m3u", False)
            if gtype == "search":
                keyword = group.get("keyword") or gname
                src_found = [c for c in src_tv if is_name_in(keyword, c.name)]
                src_tv = [c for c in src_tv if c not in src_found]
                group["channels"] = [{"name": c.name, "srcs": [c]} for c in src_found]
            elif gtype == "pattern":
                pattern = group.get("pattern") or gname
                src_found = [c for c in src_tv if re.search(pattern, c.name)]
                src_tv = [c for c in src_tv if c not in src_found]
                group["channels"] = [{"name": c.name, "srcs": [c]} for c in src_found]
            elif gtype == "regular" and not radio:
                for ch in group["channels"]:
                    src_found = find_channels_from_src(ch, src_tv)
                    src_tv = [x for x in src_tv if x not in src_found]
                    ch["srcs"] = src_found
            elif gtype == "regular" and radio:
                for ch in group["channels"]:
                    src_found = find_channels_from_src(ch, src_radio)
                    src_radio = [x for x in src_radio if x not in src_found]
                    ch["srcs"] = src_found
            else:
                raise NotImplementedError(f"잘못된 그룹 타입: {gtype}")

        # handling nogroup sources
        no_m3u_if_no_group = cls.prefs.get("no_m3u", {}).get("if_no_group", False)
        nogroup_names = {x.source_name for x in src_tv + src_radio}
        for group_name in nogroup_names:
            channel_group.append(
                {
                    "type": "nogroup",
                    "name": group_name,
                    "radio": False,
                    "no_m3u": no_m3u_if_no_group,
                    "channels": [{"name": x.name, "srcs": [x]} for x in src_tv if x.source_name == group_name],
                }
            )
            channel_group.append(
                {
                    "type": "nogroup",
                    "name": f"{group_name} 라디오",
                    "radio": True,
                    "no_m3u": no_m3u_if_no_group,
                    "channels": [{"name": x.name, "srcs": [x]} for x in src_radio if x.source_name == group_name],
                }
            )

        #
        # override no_m3u by global prefs
        #
        no_m3u_if_radio_group = cls.prefs.get("no_m3u", {}).get("if_radio_group", False)
        for group in channel_group:
            if no_m3u_if_radio_group and group["radio"]:
                group["no_m3u"] = True

        #
        # make decision based on user priority
        #
        priority = cls.prefs["priority"]
        for group in channel_group:
            for c in group["channels"]:
                if not c.get("srcs"):
                    continue
                # source 결정
                src_base, c["srcs"] = get_source(c, priority["source"])
                if src_base is None:
                    continue
                # name 결정
                src_base.name = c.get("dname") or get_src_item(c, priority["name"], "name")
                dnames = [n for n in [src_base.name, c["name"]] + c.get("alias", []) if n in cls.epg_names]
                if dnames:
                    src_base.name = dnames[0]
                # icon 결정
                src_base.icon = get_src_item(c, priority["icon"], "icon")
                c["src"] = src_base

        cls.group_list = channel_group

    @classmethod
    def get_group_list(cls, reload: bool = False):
        try:
            updated = cls.load_prefs()
            if not cls.group_list or reload or updated:
                cls.__get_group_list()
        except Exception:
            logger.exception("그룹 목록을 얻는 중 예외:")
        return cls.group_list

    @classmethod
    def get_m3u(cls, src_char: bool = False, for_tvh: bool = False) -> str:
        idx = 1
        m3u = ["#EXTM3U\n"]
        apikey = None
        if SystemModelSetting.get_bool("use_apikey"):
            apikey = SystemModelSetting.get("apikey")
        ddns = SystemModelSetting.get("ddns")
        for group in cls.get_group_list(reload=True):
            # 제외 설정
            if group["no_m3u"]:
                continue
            for c in group["channels"]:
                if not (s := c.get("src")):
                    continue
                dname = s.name if group["type"] == "nogroup" or not src_char else f"{s.source_char} {s.name}"
                kwargs = {
                    "url": s.svc_url(apikey=apikey, ddns=ddns, for_tvh=for_tvh),
                    "display_name": dname,
                    "tvg_chno": idx,
                    "tvh_chnum": idx,
                    "group_title": group["name"],
                }
                m3u.append(s.as_m3u(**kwargs))
                idx += 1
        return "".join(m3u)

    @classmethod
    def get_lineup(cls) -> list[dict]:
        lineup = []
        guide_num = 1
        apikey = None
        if SystemModelSetting.get_bool("use_apikey"):
            apikey = SystemModelSetting.get("apikey")
        ddns = SystemModelSetting.get("ddns")
        for group in cls.get_group_list(reload=True):
            if group["no_m3u"]:
                continue
            for c in group["channels"]:
                if not (s := c.get("src")):
                    continue
                url = s.svc_url(apikey=apikey, ddns=ddns, mode="plex")
                url = url.replace("&apikey", "&q=default&apikey")
                _lineup = {
                    "GuideNumber": str(guide_num),
                    "GuideName": s.name,
                    "URL": url,
                    # 표준은 아니지만 정렬이나 다른 앱에서 참조할 때 필요
                    "tvg-id": f"{s.channel_id}.{s.source}",
                    "tvg-chno": str(guide_num),
                    "tvg-chnum": str(guide_num),
                }
                lineup.append(_lineup)
                guide_num += 1
        return lineup
