import json
import os
import platform
import shutil
import subprocess
from base64 import urlsafe_b64decode
from copy import deepcopy
from datetime import datetime
from itertools import chain
from pathlib import Path

import requests
from flask import Response, abort, jsonify, redirect, render_template, request, stream_with_context
from plugin import F, PluginModuleBase  # type: ignore # pylint: disable=import-error

db = F.db
scheduler = F.scheduler
path_app_root = F.path_app_root
SystemModelSetting = F.SystemModelSetting


# local
from .logic_alive import LogicAlive
from .logic_klive import LogicKlive
from .setup import P, default_headers

logger = P.logger
package_name = P.package_name
ModelSetting = P.ModelSetting
blueprint = P.blueprint


@stream_with_context
def generate(url):
    if platform.system() == "Windows":
        ffmpeg_bin = os.path.join(path_app_root, "bin", platform.system(), "ffmpeg.exe")
    else:
        ffmpeg_bin = "ffmpeg"

    # ffmpeg_cmd = [ffmpeg_bin, "-i", new_url, "-c", "copy", "-f", "mpegts", "-tune", "zerolatency", "pipe:stdout"]
    # ffmpeg_cmd = [ffmpeg_bin, "-i", new_url, "-c:v", "copy", "-c:a", "aac", "-b:a", "128k", "-f", "mpegts", "-tune", "zerolatency", "pipe:stdout"]

    # 2020-12-17 by 잠자
    ffmpeg_cmd = [
        [ffmpeg_bin],
        ["-user_agent", default_headers["user-agent"]],
        ["-loglevel", "quiet"],
        ["-i", url],
        ["-c:v", "copy"],
        ["-c:a", "aac"],
        ["-b:a", "128k"],
        ["-f", "mpegts"],
        ["-tune", "zerolatency"],
        ["pipe:stdout"],
    ]
    ffmpeg_cmd = chain.from_iterable(ffmpeg_cmd)

    # logger.debug('command : %s', ffmpeg_cmd)
    with subprocess.Popen(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=-1) as proc:
        while True:
            chunk = proc.stdout.read(1024)
            if not chunk:
                break
            yield chunk  # 데이터를 받는 즉시 바로바로 내보냄
            proc.poll()
            if isinstance(proc.returncode, int):
                if proc.returncode > 0:
                    logger.error("ffmpeg error: %s", proc.returncode)
                break


@stream_with_context
def _streamlink(stream):
    fd = None
    try:
        fd = stream.open()
        while True:
            if (chunk := fd.read(8192)) == b"":
                break
            yield chunk
    finally:
        if fd:
            fd.close()


class Logic(PluginModuleBase):
    db_default = {
        "channel_list_updated_at": "1970-01-01T00:00:00",
        "channel_list_max_age": "60",  # minutes
        "epg_updated_at": "1970-01-01T00:00:00",
        "web_player_target": "blank",
        # wavve
        "use_wavve": "False",
        "wavve_quality": "HD",
        "wavve_profile": '{"id": "", "password": "", "profile": ""}',
        "wavve_streaming_type": "direct",
        "wavve_use_proxy_for_playlist": "False",
        # tving
        "use_tving": "False",
        "tving_quality": "HD",
        "tving_include_drm": "False",
        "tving_proxy_licenseurl": "/alive/tvinglicense",
        # kbs
        "use_kbs": "False",
        "kbs_include_vod_ch": "False",
        "kbs_streaming_type": "redirect",
        "kbs_use_proxy": "False",
        "kbs_proxy_url": "",
        "kbs_use_proxy_for_playlist": "False",
        # mbc
        "use_mbc": "False",
        "mbc_streaming_type": "direct",
        "mbc_use_proxy": "False",
        "mbc_proxy_url": "",
        "mbc_use_proxy_for_playlist": "False",
        # sbs
        "use_sbs": "False",
        "sbs_include_vod_ch": "False",
        "sbs_streaming_type": "direct",
        "sbs_use_proxy": "False",
        "sbs_proxy_url": "",
        "sbs_use_proxy_for_playlist": "False",
        # streamlink
        "use_streamlink": "False",
        "streamlink_list": "1|LeekBeats Radio: 24/7 chill lofi beats - DMCA safe music|https://www.twitch.tv/leekbeats\n2|2010년 히트곡|https://dailymotion.com/video/x77q22e",
        "streamlink_streaming_type": "redirect",
        "streamlink_use_proxy": "False",
        "streamlink_proxy_url": "",
        # fix_url
        "use_fix_url": "False",
        "fix_url_list": "1|CBS 음악FM|http://aac.cbs.co.kr/cbs939/_definst_/cbs939.stream/playlist.m3u8|N\n2|CBS 표준FM|http://aac.cbs.co.kr/cbs981/_definst_/cbs981.stream/playlist.m3u8|N\n3|국방TV|http://mediaworks.dema.mil.kr:1935/live_edge/cudo.sdp/playlist.m3u8|Y",
        # etc
        "use_plex_proxy": "False",
        "plex_proxy_host": "",
        # spotv
        "use_spotv": "False",
    }

    def __init__(self, PM):
        super().__init__(PM, None)

    def plugin_load(self):
        alive_prefs = Path(F.path_data).joinpath("db", "alive.yaml")
        if not alive_prefs.exists():
            shutil.copyfile(Path(__file__).with_name("alive.example.yaml"), alive_prefs)

    def process_menu(self, sub, req):
        _ = req
        arg = ModelSetting.to_dict()
        ddns = SystemModelSetting.get("ddns")
        use_apikey = SystemModelSetting.get_bool("use_apikey")
        apikey = SystemModelSetting.get("apikey")
        try:
            arg["package_name"] = package_name
            if sub == "setting":
                url_base = f"{ddns}/{package_name}"
                arg["api_m3u"] = url_base + "/api/m3u"
                arg["api_m3utvh"] = url_base + "/api/m3utvh"
                arg["api_m3uall"] = url_base + "/api/m3uall"
                arg["plex_proxy"] = url_base + "/proxy/plex"

                if use_apikey:
                    for tmp in ["api_m3u", "api_m3uall", "api_m3utvh"]:
                        arg[tmp] += f"?apikey={apikey}"

                try:
                    from support_site.setup import P as SS  # type: ignore # pylint: disable=import-error

                    arg["site_wavve_use_proxy"] = SS.ModelSetting.get_bool("site_wavve_use_proxy")
                except ImportError:
                    arg["site_wavve_use_proxy"] = False

                from .source_streamlink import SourceStreamlink

                arg["streamlink_ver"] = SourceStreamlink.streamlink_ver()
            if sub == "group":
                arg["alive_prefs"] = str(Path(F.path_data).joinpath("db", "alive.yaml"))
            return render_template(f"{package_name}_{sub}.html", sub=sub, arg=arg)
        except Exception:
            logger.exception("메뉴 처리 중 예외:")
            return render_template("sample.html", title=f"{package_name} - {sub}")

    def process_ajax(self, sub, req):
        try:
            if sub == "setting_save_and_reload":
                saved, changed = ModelSetting.setting_save(req)
                # NOTE 설정 텍스트 마지막에 whitespace가 있으면 변경사항이 제대로 감지가 안되는 버그가 있다.
                if changed:
                    LogicKlive.load_channels(reload="hard")
                return jsonify(saved)
            if sub == "source_reload":
                LogicKlive.load_channels(reload="hard")
                return jsonify(True)

            form = req.form.to_dict()
            if sub == "channel_list":
                reload = "soft" if form["reload"] == "true" else None
                ret = LogicKlive.all_channels(reload=reload)
                updated_at = ModelSetting.get("channel_list_updated_at")
                updated_at = datetime.fromisoformat(updated_at).strftime("%Y-%m-%d %H:%M:%S")
                return jsonify({"list": [x.as_dict() for x in ret], "updated_at": updated_at})
            if sub == "play_url":
                c = LogicKlive.sources[form["source"]].channels[form["channel_id"]]
                mode = "web_play" if form.get("web_play", "false") == "true" else "url"
                data = {"url": c.svc_url(mode=mode), "title": c.program.title}
                return jsonify({"data": data})
            if sub == "group_list":
                reload = form.get("reload", "false") == "true"
                channel_group = deepcopy(LogicAlive.get_group_list(reload=reload))
                for g in channel_group:
                    for c in g["channels"]:
                        if "src" in c:
                            c["src"] = c["src"].as_dict()
                        c["srcs"] = [s.as_dict() for s in c["srcs"]]
                return jsonify({"list": channel_group})
        except Exception:
            logger.exception("AJAX 요청 처리 중 예외:")

    def process_m3u(self, sub, args):
        if sub == "m3uall":
            m3u = LogicKlive.get_m3uall()
        elif sub == "m3u":
            src_char = args.get("srcChar", "").lower() == "y"
            m3u = LogicAlive.get_m3u(src_char=src_char)
        elif sub == "m3utvh":
            src_char = args.get("srcChar", "").lower() == "y"
            m3u = LogicAlive.get_m3u(src_char=src_char, for_tvh=True)
        else:
            raise NotImplementedError(f"잘못된 sub: {sub}")
        return Response(m3u, content_type="audio/mpegurl")

    def _process_m3u8(self, args) -> Response:
        src = LogicKlive.get_source(source_id := args["s"])
        stype, sdata = src.make_m3u8(channel_id := args["i"], args["m"], args.get("q"))
        if sdata is None:
            return Response(status=204)
        if stype == "redirect":
            r = redirect(sdata, code=302)
        elif stype == "stream":
            r = Response(_streamlink(sdata), mimetype="video/MP2T", direct_passthrough=True)
        else:
            if isinstance(sdata, dict):
                if stream_id := args.get("t"):  # media playlist
                    url = sdata["streams"][int(stream_id)]["url"]
                    sdata = src.repack_m3u8(url, stype)
                else:
                    sdata = src.rewrite_m3u8_urls(sdata["contents"], request.full_path)
            r = Response(sdata, content_type="application/vnd.apple.mpegurl")
        logger.debug("%s", " -> ".join([f"{source_id} {channel_id}", f"({stype})", request.remote_addr]))
        return r

    def process_api(self, sub, req):
        args = req.args.to_dict()
        # logger.debug("args: %s", args)
        try:
            if sub in ["m3uall", "m3u", "m3utvh"]:
                return self.process_m3u(sub, args)
            if (mode := args["m"]) == "plex":
                return Response(generate(req.url.replace("m=plex", "m=url")), mimetype="video/MP2T")
            if sub == "url.m3u8":
                return self._process_m3u8(args)
            if sub == "url.mpd":
                stype, sdata = LogicKlive.get_source(source := args["s"]).make_m3u8(
                    channel_id := args["i"], mode, args.get("q")
                )
                if isinstance(sdata, str):
                    sdata = json.loads(sdata)
                logger.debug("%s", " -> ".join([f"{source} {channel_id}", f"({stype})", req.remote_addr]))
                return jsonify(sdata)
            logger.error("잘못된 sub: %s", sub)
            abort(400)
        except Exception:
            logger.exception("API 요청 처리 중 예외:")


#########################################################
# Plex Proxy
#########################################################
@blueprint.route("/proxy/plex", defaults={"sub": None}, methods=["GET", "POST"])
@blueprint.route("/proxy/plex/<sub>", methods=["GET", "POST"])
def plex_proxy(sub):
    logger.debug("/alive/proxy/plex %s", sub)
    if not ModelSetting.get_bool("use_plex_proxy"):
        abort(403)
    allowed_hosts = map(str.strip, ModelSetting.get("plex_proxy_host").splitlines())
    allowed_hosts = [x for x in allowed_hosts if x and not x.startswith("#")]
    if allowed_hosts and request.host not in allowed_hosts:
        logger.debug("request host %s NOT allowed: %s", request.host, allowed_hosts)
        abort(403)
    try:
        sub_root = f"{request.url_root}alive/proxy/plex"
        if sub is None:
            return redirect(f"{sub_root}/discover.json")
        if sub == "discover.json":
            data = {
                "FriendlyName": "HDHomeRun CONNECT",
                "ModelNumber": "HDHR4-2US",
                "FirmwareName": "hdhomerun4_atsc",
                "FirmwareVersion": "20190621",
                "DeviceID": "104E8010",
                "DeviceAuth": "UF4CFfWQh05c3jROcArmAZaf",
                "BaseURL": sub_root,
                "LineupURL": f"{sub_root}/lineup.json",
                "TunerCount": 20,
            }
            return jsonify(data)
        if sub == "lineup_status.json":
            data = {"ScanInProgress": 0, "ScanPossible": 1, "Source": "Cable", "SourceList": ["Antenna", "Cable"]}
            return jsonify(data)
        if sub == "lineup.json":
            return jsonify(LogicAlive.get_lineup())
    except Exception:
        logger.exception("Exception proxing for plex:")
    abort(403)


#########################################################
# drm license proxy
#########################################################
@blueprint.route("/proxy/license", methods=["OPTIONS", "POST"])
def license_proxy():
    headers = {k: v for k, v in request.headers if k.lower() != "host"}
    headers["Origin"] = headers.pop("Real-Origin")
    headers["Referer"] = headers.pop("Real-Referer")
    url = headers.pop("Real-Url")
    res = requests.request(  # ref. https://stackoverflow.com/a/36601467/248616
        method=request.method,
        url=url,
        headers=headers,
        data=request.get_data(),
        cookies=request.cookies,
        allow_redirects=False,
        timeout=10,
    )
    # region exlcude some keys in :res response
    excluded_headers = [
        "content-encoding",
        "content-length",
        "transfer-encoding",
        "connection",
    ]  # NOTE we here exclude all "hop-by-hop headers" defined by RFC 2616 section 13.5.1 ref. https://www.rfc-editor.org/rfc/rfc2616#section-13.5.1
    headers = [(k, v) for k, v in res.raw.headers.items() if k.lower() not in excluded_headers]
    # endregion exlcude some keys in :res response
    response = Response(res.content, res.status_code, headers)
    return response


#########################################################
# hls proxy
#########################################################
@blueprint.route("/proxy/hls/chunk", methods=["GET"])
def proxy_chunk():
    try:
        src = LogicKlive.get_source(request.args["s"])
        url = urlsafe_b64decode(request.args["url"]).decode()
    except Exception:
        abort(404)
    try:
        r = src.plsess.get(url, stream=True, timeout=30)
        return Response(
            r.iter_content(chunk_size=1048576),
            status=r.status_code,
            content_type=r.headers["Content-Type"],
            direct_passthrough=True,
        )
    except Exception:
        # 어떤 예외든 404로 위장
        logger.debug("Exception proxing for chunks", exc_info=True)
        abort(404)
