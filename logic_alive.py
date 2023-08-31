import xml.etree.ElementTree as ET
from copy import deepcopy
from datetime import datetime
from pathlib import Path

import requests
import yaml

try:
    from yaml import CLoader as Loader
except ImportError:
    from yaml import Loader

from plugin import F

SystemModelSetting = F.SystemModelSetting

# local
from .logic_klive import LogicKlive
from .setup import P

logger = P.logger
package_name = P.package_name
ModelSetting = P.ModelSetting


M3U_FORMAT = '#EXTINF:-1 tvg-id="%s" tvg-name="%s" tvg-logo="%s" group-title="%s" tvg-chno="%s" tvh-chnum="%s",%s\n%s\n'
M3U_RADIO_FORMAT = '#EXTINF:-1 tvg-id="%s" tvg-name="%s" tvg-logo="%s" group-title="%s" radio="true" tvg-chno="%s" tvh-chnum="%s",%s\n%s\n'


def is_name_same(a, b) -> bool:
    return a.replace(" ", "").lower() == b.replace(" ", "").lower()


def is_name_in(a, b) -> bool:
    return a.replace(" ", "").lower() in b.replace(" ", "").lower()


def find_channels_from_src(ch_info, src_list):
    ret = []
    for m in src_list:
        if any(is_name_same(m.name, x) for x in [ch_info["name"]] + ch_info.get("alias", [])):
            ret.append(m)
    return ret


def sort_srcs(srcs, priority_list):
    src_known = [s for s in srcs if s.source_name in priority_list]
    src_unknown = [s for s in srcs if s.source_name not in priority_list]
    return sorted(src_known, key=lambda v: priority_list.index(v.source_name)) + src_unknown


def get_source(ch, priority_list):
    srcs = sort_srcs(ch["srcs"], priority_list)
    if "force" in ch:
        for src in srcs:
            if src.source_name.lower() == ch["force"].lower():
                logger.debug("%-10s: 강제로 다음 소스를 선택: %s", ch["name"], src.source_name)
                return deepcopy(src), srcs
    for src in srcs:
        if not src.program.onair:
            logger.debug("%-10s: 현재 방송불가: %s", ch["name"], src.source_name)
            continue
        return deepcopy(src), srcs
    return deepcopy(srcs[0]), srcs


def get_src_item(ch, priority_list, attrib):
    for src in sort_srcs(ch["srcs"], priority_list):
        if hasattr(src, attrib):
            return getattr(src, attrib)
    return ""


def load_yaml(file):
    try:
        return yaml.load(file, Loader=Loader)
    except TypeError:
        with open(file, "r", encoding="utf-8") as fp:
            return yaml.load(fp, Loader=Loader)


def get_circled_name(source):
    source_map = {
        "KBS": "k",
        "SBS": "s",
        "MBC": "m",
        "웨이브": "w",
        "티빙": "t",
        "고정주소": "f",
        "YoutubeDL": "y",
        "StreamLink": "l",
        "네이버TV": "n",
        "카카오TV": "o",
    }
    alphabet = source_map.get(source, "x").lower()
    circled_alphabet = "ⒶⒷⒸⒹⒺⒻⒼⒽⒾⒿⓀⓁⓂⓃⓄⓅⓆⓇⓈⓉⓊⓋⓌⓍⓎⓏ"
    return circled_alphabet[ord(alphabet) - ord("a")]


class LogicAlive:
    epg_names: list = []
    group_list: list = []
    prefs: dict = {}

    @classmethod
    def load_prefs(cls) -> bool:
        file = Path(F.path_data).joinpath("db", "alive.yaml")
        prefs = load_yaml(file)
        if prefs != cls.prefs:
            cls.prefs = prefs
            return True
        return False

    @classmethod
    def __get_epg_names(cls, epg_urls: list) -> list:
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
        known_channel_names = []
        for group in channel_group:
            for channel in group.get("channels", []):
                channel_name = channel["name"]
                if channel_name in known_channel_names:
                    logger.warning("채널 이름에 중복이 있습니다: %s", channel_name)
                known_channel_names += channel_name

        src_tv = [c for c in LogicKlive.get_channel_list() if c.is_tv]
        src_radio = [c for c in LogicKlive.get_channel_list() if not c.is_tv]

        #
        # grouping available sources based on predefined channel_group
        #
        for group in channel_group:
            gtype = group["type"]
            gname = group["name"]
            radio = group.get("radio", False)
            if gtype == "search":
                keyword = group.get("keyword") or gname
                src_found = [c for c in src_tv if is_name_in(keyword, c.name)]
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
        nogroup_names = set()
        for x in src_tv + src_radio:
            nogroup_names.add(x.source_name)
        for group_name in list(nogroup_names):
            channel_group.append(
                {
                    "type": "nogroup",
                    "name": group_name,
                    "channels": [{"name": x.name, "srcs": [x]} for x in src_tv if x.source_name == group_name],
                }
            )
            channel_group.append(
                {
                    "type": "nogroup",
                    "name": f"{group_name} radio",
                    "radio": True,
                    "channels": [{"name": x.name, "srcs": [x]} for x in src_radio if x.source_name == group_name],
                }
            )

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
                if c.get("dname"):
                    src_base.name = c.get("dname")
                else:
                    default_name = get_src_item(c, priority["name"], "name")
                    dnames = list(filter(lambda n: n in cls.epg_names, [default_name, c["name"]] + c.get("alias", [])))
                    src_base.name = dnames[0] if dnames else default_name
                # icon 결정
                src_base.icon = get_src_item(c, priority["icon"], "icon")
                c["src"] = src_base

        cls.group_list = channel_group

    @classmethod
    def get_group_list(cls, reload=False):
        try:
            updated = cls.load_prefs()
            if not cls.group_list or reload or updated:
                cls.__get_group_list()
        except Exception:
            logger.exception("그룹 목록을 얻는 중 예외:")
        return cls.group_list

    @classmethod
    def get_m3u(cls, for_tvh=False):
        idx = 1
        m3u = ["#EXTM3U\n"]
        apikey = None
        if SystemModelSetting.get_bool("use_apikey"):
            apikey = SystemModelSetting.get("apikey")
        ddns = SystemModelSetting.get("ddns")
        for group in cls.get_group_list(reload=True):
            for c in group["channels"]:
                if not c.get("src"):
                    continue
                s = c["src"]
                kwargs = {
                    "url": s.svc_url(apikey=apikey, ddns=ddns, for_tvh=for_tvh),
                    "display_name": s.name
                    if group["type"] == "nogroup"
                    else f"{get_circled_name(s.source_name)} {s.name}",
                    "tvg_chno": idx,
                    "tvh_chnum": idx,
                    "group_title": group["name"],
                }
                m3u.append(s.as_m3u(**kwargs))
                idx += 1
        return "".join(m3u)
