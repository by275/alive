from collections import OrderedDict
from html import unescape
from pathlib import Path
from urllib.parse import quote

import requests

from support import SupportSC  # pylint: disable=import-error

# local
from .model import ChannelItem, ProgramItem
from .setup import P
from .source_base import SourceBase

logger = P.logger
package_name = P.package_name
ModelSetting = P.ModelSetting


class SourceWavve(SourceBase):
    source_id = "wavve"
    mod = None

    def __init__(self):
        if self.mod is not None:
            return
        try:
            self.mod = self.load_support_module()
        except (ImportError, ModuleNotFoundError):
            logger.error("support site 플러그인이 필요합니다.")
        except Exception:
            logger.exception("Support Module 로딩 중 예외:")

    def load_support_module(self):
        if Path(__file__).with_name("wavve.py").is_file():
            from .wavve import SupportWavve as mod
        else:
            mod = SupportSC.load_module_f(__file__, "wavve").SupportWavve
        from support_site.setup import P as SS  # pylint: disable=import-error

        mod.initialize(
            SS.ModelSetting.get("site_wavve_credential"),
            SS.ModelSetting.get_bool("site_wavve_use_proxy"),
            SS.ModelSetting.get("site_wavve_proxy_url"),
        )
        return mod

    def get_channel_list(self):
        ret = []
        data = self.mod.live_all_channels()
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
            except Exception:
                logger.exception("라이브 채널 분석 중 예외: %s", item)
            ret.append([c.channel_id, c])
        self.channel_list = OrderedDict(ret)
        return self.channel_list

    def get_url(self, channel_id, mode, quality=None):
        surl = None
        data = self.mod.streaming("live", channel_id, quality)
        if data is not None and "playurl" in data:
            surl = data["playurl"]
            # 2022-01-10 라디오. 대충 함
            # if data['quality'] == '100p' or data['qualities']['list'][0]['name'] == '오디오모드':
            #    surl = data['playurl'].replace('/100/100', '/100') + f"/live.m3u8{data['debug']['orgurl'].split('.m3u8')[1]}"
        if surl is None:
            raise ValueError("URL is None")
        if mode == "web_play":
            return "return_after_read", surl
        if ModelSetting.get("wavve_streaming_type") == "redirect":
            return "redirect", surl
        return "return_after_read", surl

    def get_return_data(self, url, mode=None):
        data = requests.get(url, proxies=self.mod.proxies, headers=self.mod.headers, timeout=10).text
        prefix = url.split("?")[0].rsplit("/", 1)[0]
        new_lines = []
        for line in data.splitlines():
            line = line.strip()
            if line.startswith != "#" and ".ts" in line:
                line = f"{prefix}/{line}"
            new_lines.append(line)
        new_lines = "\n".join(new_lines)
        if ModelSetting.get("wavve_streaming_type") == "direct":
            return new_lines
        return self.change_redirect_data(new_lines, proxy=self.mod.proxy)
