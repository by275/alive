import os
import platform
import subprocess
import threading
import time
from urllib.parse import unquote

import requests
from flask import Response, jsonify, redirect, render_template, request, send_file, stream_with_context

from plugin import F, PluginModuleBase  # pylint: disable=import-error

db = F.db
scheduler = F.scheduler
path_app_root = F.path_app_root
SystemModelSetting = F.SystemModelSetting


# local
# from .logic_alive import make_channel_group
from .logic_klive import LogicKlive
from .setup import P, default_headers

plugin = P
logger = plugin.logger
package_name = plugin.package_name
ModelSetting = plugin.ModelSetting


@stream_with_context
def generate(url):
    startTime = time.time()
    buffer = []
    sentBurst = False

    if platform.system() == "Windows":
        path_ffmpeg = os.path.join(path_app_root, "bin", platform.system(), "ffmpeg.exe")
    else:
        path_ffmpeg = "ffmpeg"

    # ffmpeg_command = [path_ffmpeg, "-i", new_url, "-c", "copy", "-f", "mpegts", "-tune", "zerolatency", "pipe:stdout"]
    # ffmpeg_command = [path_ffmpeg, "-i", new_url, "-c:v", "copy", "-c:a", "aac", "-b:a", "128k", "-f", "mpegts", "-tune", "zerolatency", "pipe:stdout"]

    # 2020-12-17 by 잠자
    ffmpeg_command = [
        path_ffmpeg,
        "-loglevel",
        "quiet",
        "-i",
        url,
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-f",
        "mpegts",
        "-tune",
        "zerolatency",
        "pipe:stdout",
    ]

    # logger.debug('command : %s', ffmpeg_command)
    with subprocess.Popen(ffmpeg_command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=-1) as proc:
        # global process_list
        # process_list.append(proc)
        while True:
            line = proc.stdout.read(1024)
            buffer.append(line)
            if not sentBurst and time.time() > startTime + 1 and len(buffer) > 0:
                sentBurst = True
                for _ in range(0, len(buffer) - 2):
                    yield buffer.pop(0)
            elif time.time() > startTime + 1 and len(buffer) > 0:
                yield buffer.pop(0)
            proc.poll()
            if isinstance(proc.returncode, int):
                if proc.returncode > 0:
                    logger.error("ffmpeg error: %s", proc.returncode)
                break


class Logic(PluginModuleBase):
    db_default = {
        # wavve
        "use_wavve": "False",
        "wavve_quality": "HD",
        "wavve_streaming_type": "direct",
        # tving
        "use_tving": "False",
        "tving_quality": "HD",
        "tving_include_drm": "False",
        # kbs mbc sbs
        "use_kbs": "False",
        "use_mbc": "False",
        "use_sbs": "False",
        "sbs_use_proxy": "False",
        "sbs_proxy_url": "",
        # youtube-dl
        "use_youtubedl": "False",
        "youtubedl_list": "1|YTN|https://www.youtube.com/watch?v=GoXPbGQl-uQ\n2|KBS NEWS D|https://www.youtube.com/watch?v=CISTtnHPntQ\n3|연합뉴스|https://www.youtube.com/watch?v=qfMAsVoh9mg",
        "youtubedl_use_proxy": "False",
        "youtubedl_proxy_url": "",
        # streamlink
        "use_streamlink": "False",
        "streamlink_list": "1|LeekBeats Radio: 24/7 chill lofi beats - DMCA safe music|https://www.twitch.tv/leekbeats\n2|2010년 히트곡|https://dailymotion.com/video/x77q22e",
        "streamlink_quality": "best",
        # navertv
        "use_navertv": "False",
        "navertv_list": "1|스포츠 야구1|SPORTS_ad1|1080\n2|스포츠 야구2|SPORTS_ad2|1080\n3|스포츠 야구3|SPORTS_ad3|1080\n4|스포츠 야구4|SPORTS_ad4|1080\n5|스포츠 야구5|SPORTS_ad5|1080\n6|스포츠 Spocado|SPORTS_ch7|1080\n7|스포츠 sbsgolf|SPORTS_ch15|1080\n11|연합뉴스TV|https://tv.naver.com/l/44267\n12|TBS|https://tv.naver.com/l/43164|720\n",
        # kakaotv
        "use_kakaotv": "False",
        "kakaotv_list": "1|KBS24|https://tv.kakao.com/channel/3193314/livelink/11817131\n2|연합뉴스|https://tv.kakao.com/channel/2663786/livelink/11834144\n3|케이블TV VOD 라이브 - 최신 영화·드라마·예능|https://tv.kakao.com/channel/2876224/livelink/11682940",
        # fix_url
        "use_fix_url": "False",
        "fix_url_list": "1|CBS 음악FM|http://aac.cbs.co.kr/cbs939/_definst_/cbs939.stream/playlist.m3u8|N\n2|CBS 표준FM|http://aac.cbs.co.kr/cbs981/_definst_/cbs981.stream/playlist.m3u8|N\n3|국방TV|http://mediaworks.dema.mil.kr:1935/live_edge/cudo.sdp/playlist.m3u8|Y",
        # etc
        "use_plex_proxy": "False",
    }
    process_list: list = None  # TODO

    def __init__(self, PM):
        super().__init__(PM, None)
        self.process_list = []  # TODO

    def plugin_load(self):
        try:

            def func():
                LogicKlive.channel_load_from_site()

            t = threading.Thread(target=func, args=(), daemon=True)
            t.start()
        except Exception:
            logger.exception("플러그인 로딩 중 예외:")

    def plugin_unload(self):
        try:
            import psutil

            for p in self.process_list:
                if p is not None and p.poll() is None:
                    process = psutil.Process(p.pid)
                    for proc in process.children(recursive=True):
                        proc.kill()
                    process.kill()
        except Exception:
            logger.exception("플러그인 종료 중 예외:")

    def process_menu(self, sub, req):
        arg = ModelSetting.to_dict()
        ddns = SystemModelSetting.get("ddns")
        use_apikey = SystemModelSetting.get_bool("use_apikey")
        apikey = SystemModelSetting.get("apikey")
        try:
            arg["package_name"] = package_name
            arg["ddns"] = ddns
            arg["use_apikey"] = str(use_apikey)
            arg["apikey"] = apikey
            if sub == "setting":
                url_base = f"{ddns}/{package_name}"
                arg["api_m3u"] = url_base + "/api/m3u"
                arg["api_m3utvh"] = url_base + "/api/m3utvh"
                arg["api_m3uall"] = url_base + "/api/m3uall"
                arg["xmltv"] = f"{ddns}/epg/api/klive"  # TODO
                arg["plex_proxy"] = url_base + "/proxy"

                if use_apikey:
                    for tmp in ["api_m3u", "api_m3uall", "api_m3utvh", "xmltv"]:
                        arg[tmp] += f"?apikey={apikey}"

                from .source_streamlink import SourceStreamlink

                arg["tmp_is_streamlink_installed"] = "Installed" if SourceStreamlink.is_installed() else "Not Installed"
                from .source_youtubedl import SourceYoutubedl

                arg["tmp_is_youtubedl_installed"] = "Installed" if SourceYoutubedl.is_installed() else "Not Installed"
            if sub == "proxy":
                return redirect(f"/{package_name}/proxy/discover.json")
            if sub == "group":
                return render_template(f"{package_name}_{sub}.html", channel_group=make_channel_group())
            return render_template(f"{package_name}_{sub}.html", sub=sub, arg=arg)
        except Exception:
            logger.exception("메뉴 처리 중 예외:")
            return render_template("sample.html", title=f"{package_name} - {sub}")

    def process_ajax(self, sub, req):
        # logger.debug('AJAX %s %s', package_name, sub)
        try:
            if sub == "setting_save":
                # old = '%s%s%s%s%s%s' % (ModelSetting.get('use_wavve'), ModelSetting.get('use_tving'), ModelSetting.get('use_videoportal'), ModelSetting.get('use_everyon'), ModelSetting.get('use_streamlink'), ModelSetting.get('streamlink_list'))
                ret = ModelSetting.setting_save(request)
                # new = '%s%s%s%s%s%s' % (ModelSetting.get('use_wavve'), ModelSetting.get('use_tving'), ModelSetting.get('use_videoportal'), ModelSetting.get('use_everyon'), ModelSetting.get('use_streamlink'), ModelSetting.get('streamlink_list'))
                # if new != old:
                LogicKlive.get_channel_list(from_site=True)
                return jsonify(ret)
            if sub == "channel_list":
                from_site = req.form.get("from_site", "") == "true"
                ret = LogicKlive.get_channel_list(from_site=from_site)
                # logger.debug("channel_list: %s", len(ret))
                return jsonify([x.as_dict() for x in ret])
            # 커스텀 생성
            # elif sub == "custom":
            #     ret = {}
            #     ret["list"] = LogicKlive.custom()
            #     ret["setting"] = ModelSetting.to_dict()
            #     return jsonify(ret)
            # elif sub == "custom_save":
            #     ret = LogicKlive.custom_save(request)
            #     return jsonify(ret)
            # elif sub == "get_saved_custom":
            #     ret = LogicKlive.get_saved_custom()
            #     return jsonify(ret)
            # elif sub == "custom_edit_save":
            #     ret = LogicKlive.custom_edit_save(request)
            #     return jsonify(ret)
            # elif sub == "custom_delete":
            #     ret = LogicKlive.custom_delete(request)
            #     return jsonify(ret)
        except Exception:
            logger.exception("AJAX 요청 처리 중 예외:")

    def process_api(self, sub, req):
        if sub == "url.m3u8":
            mode = request.args.get("m")
            source = request.args.get("s")
            channel_id = request.args.get("i")
            quality = request.args.get("q")
            # logger.debug("m=%s, s=%s, i=%s, q=%s", mode, source, channel_id, quality)

            if mode == "plex":
                new_url = f'{SystemModelSetting.get("ddns")}/{package_name}'
                new_url += f"/api/url.m3u8?m=url&s={source}&i={channel_id}&q={quality}"
                if SystemModelSetting.get_bool("use_apikey"):
                    new_url += f'&apikey={SystemModelSetting.get("apikey")}'

                return Response(generate(new_url), mimetype="video/MP2T")

            action, ret = LogicKlive.get_url(source, channel_id, mode, quality=quality)
            # logger.debug('action:%s, url:%s', action, ret)

            if ret is None:
                return ret

            if action == "redirect":
                return redirect(ret, code=302)
            if action == "return_after_read":
                # logger.warning('return_after_read')
                data = LogicKlive.get_return_data(source, ret, mode=mode)
                # logger.debug('Data len : %s', len(data))
                # logger.debug(data)
                return data, 200, {"Content-Type": "application/vnd.apple.mpegurl"}
            if action == "return":
                return ret

            if mode == "url.m3u8":
                return redirect(ret, code=302)
            if mode == "lc":
                return ret
        elif sub == "m3uall":
            return LogicKlive.get_m3uall()
        # elif sub == "m3u":
        #     data = LogicKlive.get_m3u(
        #         m3u_format=request.args.get("format"), group=request.args.get("group"), call=request.args.get("call")
        #     )
        #     if request.args.get("file") == "true":
        #         import framework.common.util as CommonUtil

        #         basename = "klive_custom.m3u"
        #         filename = os.path.join(path_data, "tmp", basename)
        #         CommonUtil.write_file(data, filename)
        #         return send_file(filename, as_attachment=True, attachment_filename=basename)
        #     return data
        # elif sub == "m3utvh":
        #     return LogicKlive.get_m3u(
        #         for_tvh=True, m3u_format=request.args.get("format"), group=request.args.get("group")
        #     )
        elif sub == "redirect":
            # SJVA 사용
            url = request.args.get("url")
            proxy = request.args.get("proxy")
            proxies = None
            if proxy is not None:
                proxy = unquote(proxy)
                proxies = {"https": proxy, "http": proxy}
            url = unquote(url)
            # logger.debug('REDIRECT:%s', url)
            # logger.warning(f"redirect : {url}")
            # 2021-06-03
            headers = {"Connection": "keep-alive"}
            headers.update(default_headers)
            r = requests.get(url, headers=headers, stream=True, proxies=proxies, verify=False, timeout=30)
            rv = Response(
                r.iter_content(chunk_size=1048576),
                r.status_code,
                content_type=r.headers["Content-Type"],
                direct_passthrough=True,
            )
            return rv
        # elif sub == "url.mpd":
        #     try:
        #         mode = request.args.get("m")
        #         source = request.args.get("s")
        #         source_id = request.args.get("i")
        #         quality = request.args.get("q")
        #         return_format = "json"
        #         data = LogicKlive.get_play_info(source, source_id, quality, mode=mode, return_format=return_format)
        #         return jsonify(data)
        #     except Exception as e:
        #         logger.error("Exception:%s", e)
        #         logger.error(traceback.format_exc())
        # elif sub == "url.strm":
        #     try:
        #         mode = request.args.get("m")
        #         source = request.args.get("s")
        #         source_id = request.args.get("i")
        #         quality = request.args.get("q")
        #         return_format = "strm"
        #         data = LogicKlive.get_play_info(source, source_id, quality, mode=mode, return_format=return_format)
        #         # return data

        #         import framework.common.util as CommonUtil

        #         from .model import ModelCustom

        #         db_item = ModelCustom.get(source, source_id)
        #         if db_item is not None:
        #             basename = "%s.strm" % db_item.title
        #         else:
        #             basename = "%s.strm" % source_id
        #         filename = os.path.join(path_data, "tmp", basename)
        #         CommonUtil.write_file(data, filename)
        #         return send_file(filename, as_attachment=True, attachment_filename=basename)

        #         # return data
        #     except Exception as e:
        #         logger.error("Exception:%s", e)
        #         logger.error(traceback.format_exc())
        # elif sub == "sinaplayer":
        #     data = LogicKlive.get_m3u_for_sinaplayer()
        #     return data


# @blueprint.route('/normal/<sub>', methods=['GET', 'POST'])
# def normal(sub):
#     try:
#         pass

#     except Exception as exception:
#         P.logger.error('Exception:%s', exception)
#         P.logger.error(traceback.format_exc())


# #########################################################
# # Proxy
# #########################################################
# @blueprint.route('/proxy/<sub>', methods=['GET', 'POST'])
# def proxy(sub):
#     logger.debug('proxy %s %s', package_name, sub)
#     try:
#         if ModelSetting.get_bool('use_plex_proxy') == False:
#             abort(403)
#             return
#         if sub == 'discover.json':
#             ddns = SystemModelSetting.get('ddns')
#             data = {"FriendlyName":"HDHomeRun CONNECT","ModelNumber":"HDHR4-2US","FirmwareName":"hdhomerun4_atsc","FirmwareVersion":"20190621","DeviceID":"104E8010","DeviceAuth":"UF4CFfWQh05c3jROcArmAZaf","BaseURL":"%s/klive/proxy" % ddns,"LineupURL":"%s/klive/proxy/lineup.json" % ddns,"TunerCount":20}
#             return jsonify(data)
#         elif sub == 'lineup_status.json':
#             data = {"ScanInProgress":0,"ScanPossible":1,"Source":"Cable","SourceList":["Antenna","Cable"]}
#             return jsonify(data)
#         elif sub == 'lineup.json':
#             lineup = []
#             custom_list = LogicKlive.get_saved_custom_instance()
#             ddns = SystemModelSetting.get('ddns')
#             apikey = None
#             if SystemModelSetting.get_bool('auth_use_apikey'):
#                 apikey = SystemModelSetting.get('auth_apikey')
#             for c in custom_list:
#                 tmp = c.get_m3u8(ddns, 'plex', apikey)
#                 lineup.append({'GuideNumber': str(c.number), 'GuideName': c.title, 'URL': tmp})
#             return jsonify(lineup)
#     except Exception as e:
#         logger.error('Exception:%s', e)
#         logger.error(traceback.format_exc())
