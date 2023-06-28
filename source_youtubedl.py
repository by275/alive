from collections import OrderedDict

# local
from .model import ChannelItem
from .setup import P
from .source_base import SourceBase

logger = P.logger
package_name = P.package_name
ModelSetting = P.ModelSetting


class SourceYoutubedl(SourceBase):
    source_id = "youtubedl"

    @staticmethod
    def is_installed():
        try:
            import yt_dlp

            return True
        except ImportError:
            return False

    def get_channel_list(self):
        ret = []
        for item in map(str.strip, ModelSetting.get(f"{self.source_id}_list").splitlines()):
            if not item:
                continue
            tmp = item.split("|")
            if len(tmp) != 3:
                continue
            cid, cname, url = tmp
            c = ChannelItem(self.source_id, cid, cname, None, True)
            c.url = url
            ret.append([c.channel_id, c])
        self.channel_list = OrderedDict(ret)
        return self.channel_list

    def get_url(self, channel_id, mode, quality=None):
        # logger.debug('channel_id:%s, quality:%s, mode:%s', channel_id, quality, mode)
        import yt_dlp

        ydl_opts = {}
        if ModelSetting.get_bool("youtubedl_use_proxy"):
            ydl_opts["proxy"] = ModelSetting.get("youtubedl_proxy_url")
        # ydl = youtube_dl.YoutubeDL(ydl_opts)
        ydl = yt_dlp.YoutubeDL(ydl_opts)
        target_url = self.channel_list[channel_id].url
        result = ydl.extract_info(target_url, download=False)
        # logger.warning('Formats len : %s', len(result['formats']))
        # logger.warning(d(result))
        if "formats" in result:
            # formats = result['formats']
            url = result["formats"][-1]["url"]
            # logger.error(url)
        # logger.info(url)
        if mode == "web_play":
            return "return_after_read", url
        return "redirect", url
