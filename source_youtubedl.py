# local
from .model import ChannelItem, SimpleItem
from .setup import P
from .source_base import SourceBase

logger = P.logger
package_name = P.package_name
ModelSetting = P.ModelSetting


class SourceYoutubedl(SourceBase):
    source_name = "youtubedl"

    @staticmethod
    def is_installed():
        try:
            import yt_dlp

            return True
        except ImportError:
            return False

    @classmethod
    def get_channel_list(cls):
        ret = []
        cls.channel_cache = {}
        for item in map(str.strip, ModelSetting.get(f"{cls.source_name}_list").splitlines()):
            if not item:
                continue
            tmp = item.split("|")
            if len(tmp) != 3:
                continue
            cid, title, url = tmp
            c = ChannelItem(cls.source_name, cid, title, None, True)
            cls.channel_cache[cid] = SimpleItem(cid, title, url)
            ret.append(c)
        return ret

    @classmethod
    def get_url(cls, channel_id, mode, quality=None):
        # logger.debug('channel_id:%s, quality:%s, mode:%s', channel_id, quality, mode)
        # import youtube_dl
        import yt_dlp

        ydl_opts = {}
        if ModelSetting.get_bool("youtubedl_use_proxy"):
            ydl_opts["proxy"] = ModelSetting.get("youtubedl_proxy_url")
        # ydl = youtube_dl.YoutubeDL(ydl_opts)
        ydl = yt_dlp.YoutubeDL(ydl_opts)
        target_url = cls.channel_cache[channel_id].url
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
