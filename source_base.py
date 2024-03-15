import re
from collections import OrderedDict
from urllib.parse import quote

import requests
from plugin import F  # pylint: disable=import-error

SystemModelSetting = F.SystemModelSetting

# local
from .setup import P, default_headers

logger = P.logger
package_name = P.package_name
ModelSetting = P.ModelSetting


class SourceBase:
    source_id: str = None
    channel_list: OrderedDict = OrderedDict()

    PTN_URL = re.compile(r"^http(.*?)$", re.MULTILINE)

    def __init__(self):
        pass

    def get_channel_list(self):
        pass

    def get_url(self, channel_id, mode, quality=None):
        pass

    def get_return_data(self, url, mode=None):
        try:
            data = requests.get(url, headers=default_headers, timeout=30).text
            return self.change_redirect_data(data)
        except Exception:
            logger.exception("Streaming URL을 분석 중 예외:")
            return url

    def change_redirect_data(self, data, proxy=None):
        base_url = f"{SystemModelSetting.get('ddns')}/{package_name}/api/redirect"
        apikey = None
        if SystemModelSetting.get_bool("use_apikey"):
            apikey = SystemModelSetting.get("apikey")
        for m in self.PTN_URL.finditer(data):
            u = m.group(0)
            u2 = f"{base_url}?url={quote(u)}"
            if apikey is not None:
                u2 += f"&apikey={apikey}"
            if proxy is not None:
                u2 += f"&proxy={quote(proxy)}"
            data = data.replace(u, u2)
        return data
