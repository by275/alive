from pathlib import Path

import yaml
from plugin import F, create_plugin_instance  # type: ignore # pylint: disable=import-error

__menu = {
    "uri": __package__,
    "name": "ALive",
    "list": [
        {"uri": "setting", "name": "설정"},
        {"uri": "list", "name": "전체채널"},
        {"uri": "group", "name": "채널그룹"},
        {"uri": "log", "name": "로그"},
    ],
}

setting = {
    "filepath": __file__,
    "use_db": True,
    "use_default_setting": True,
    "home_module": "setting",
    "menu": __menu,
    "setting_menu": None,
    "default_route": "single",
}

default_headers = {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
    "accept-language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36",
}

alive_prefs = Path(F.path_data) / "db" / "alive.yaml"


class Loader(yaml.SafeLoader):
    def __init__(self, stream):
        self._root = Path(stream.name).parent
        super().__init__(stream)

    def include(self, node):
        filename = self._root / self.construct_scalar(node)
        with open(filename, "r", encoding="utf-8") as f:
            return yaml.load(f, Loader)


Loader.add_constructor("!include", Loader.include)


P = create_plugin_instance(setting)

from .logic import Logic

P.set_module_list([Logic])
