import json
import re
from collections import OrderedDict
from datetime import datetime, timedelta
import traceback
from flask import request, jsonify, Response
import requests
from urllib.parse import unquote, quote

from .model import ChannelItem, ProgramItem
from .setup import P
from support import d
from tool import ToolUtil
from plugin import F, db, ModelBase 
from .source_base import SourceBase

logger = P.logger
package_name = P.package_name
ModelSetting = P.ModelSetting


class SourceBot(SourceBase):
    source_id = "bot"

    def load_channels(self) -> None:
        ModelBot.time_check()
        items = ModelBot.get_list(by_dict=True)
        logger.debug(f"SourceBot.load_channels {len(items)} items found")
        ret = []
        if items:
            for item in items:
                p = ProgramItem(
                    title=f"{item['start_time_str']} ~ {item['end_time_str']}"
                )
                c = ChannelItem(
                    self.source_id, 
                    item['code'],
                    item['title'], 
                    item['poster'], 
                    True, 
                    item['is_drm'],
                    program=p
                )
                ret.append(c)
            self.channels = OrderedDict((c.channel_id, c) for c in ret)

    def get_url(self, channel_id: str) -> str:
        return self.channels[channel_id].url

    def make_drm(self, data: dict, mode: str) -> tuple[str, dict]:
        if mode == "web_play":
            return "drm+web", {
                "src": data["uri"],
                "type": "application/x-mpegurl",
                "keySystems": {
                    "com.widevine.alpha": {
                        "url": "/alive/proxy/license",
                        "licenseHeaders": {
                            "Real-Url": data["drm_license_uri"],
                            "Real-Origin": data["drm_key_request_properties"]["origin"],
                            "Real-Referer": data["drm_key_request_properties"]["referer"],
                        },
                        "persistentState": "required",
                    }
                },
            }
        return "drm", data

    def make_m3u8(self, channel_id: str, mode: str, quality: str) -> tuple[str, str | dict]:
        db_item = ModelBot.get_by_code(channel_id)
        if db_item != None:
            
            if db_item.ott == "TVING":
                uri = f"/alive/bot/proxy?url={quote(db_item.stream_url)}"
                url = ToolUtil.make_apikey_url(uri)
                return "redirect", url
            elif db_item.ott == "CPP":
                if db_item.is_drm == False:
                    return "redirect", db_item.stream_url
                else:
                    pass

    def process_discord_data(self, msg):
        ModelBot.process(msg['msg']['data'])


@F.app.route('/alive/bot/proxy')
def tving_proxy():
    try:
        url = request.args.get('url')
        url = unquote(url)
        res = requests.get(url)
        if res.status_code != 200:
            return Response(status=res.status_code)
            
        prefix = url.split('chunklist_')[0]
        postfix = url.split('?')[-1]
        ret = re.sub(
            r'media_.*?\.ts',
            lambda m: f"{prefix}{m.group(0)}?{postfix}",
            res.text
        )
        ret = ret.replace("http://", "https://")
        response = Response(ret, content_type='application/vnd.apple.mpegurl')
        response.headers['Content-Disposition'] = 'attachment; filename="chunklist.m3u8"'
        response.headers['Access-Control-Allow-Origin'] = '*'
        return response
    except Exception as e:
        return Response(status=500, response=f"Error: {str(e)}")


class ModelBot(ModelBase):
    P = P
    __tablename__ = f'{P.package_name}_bot_item'
    __table_args__ = {'mysql_collate': 'utf8_general_ci'}
    __bind_key__ = P.package_name


    id = db.Column(db.Integer, primary_key=True)
    created_time = db.Column(db.DateTime)
    code = db.Column(db.String)
    start_time_str = db.Column(db.String)
    end_time_str = db.Column(db.String)
    start_time = db.Column(db.DateTime)
    end_time = db.Column(db.DateTime)
    poster = db.Column(db.String)
    title = db.Column(db.String)
    is_drm = db.Column(db.Boolean, default=False)
    info = db.Column(db.JSON)
    stream_url = db.Column(db.String)
    ott = db.Column(db.String)

    def __init__(self): 
        self.created_time = datetime.now()

    @classmethod
    def process(cls, data):
        try:
            #logger.debug(d(data))
            db_item = cls.get_by_code(data['id'])
            if data['s'] == 'start':
                if db_item is None:
                    db_item = cls()
                    db_item.code = data['id']
                    db_item.title = data['t']
                    db_item.poster = data['p']
                    db_item.start_time_str = data['t1']
                    db_item.end_time_str = data['t2']

                    db_item.start_time = datetime.strptime(data['t1'], '%Y-%m-%d %H:%M')
                    db_item.end_time = datetime.strptime(data['t2'], '%Y-%m-%d %H:%M')
                    db_item.is_drm = data['i']['is_drm']
                    db_item.info = data['i']
                    db_item.stream_url = data['i']['src']
                    db_item.ott = data['id'].split('_', 1)[0]
                    db_item.save()
                    logger.debug(f"새로운 방송 등록: {data['t']}")
                else:
                    logger.info(f"이미 등록된 방송입니다. {data['t']}")
            elif data['s'] == 'end':
                if db_item is not None:
                    db_item.delete_by_id(db_item.id)

        except Exception as e: 
            logger.error(f'Exception:{str(e)}')
            logger.error(traceback.format_exc())
           

    @classmethod
    def get_by_code(cls, code):
        try:
            with F.app.app_context():
                return F.db.session.query(cls).filter_by(code=code).first()
        except Exception as e:
            logger.error(f'Exception:{str(e)}')
            logger.error(traceback.format_exc())

    @classmethod
    def time_check(cls):
        try:
            with F.app.app_context():
                now = datetime.now() #+ timedelta(days=1)
                items = F.db.session.query(cls).filter(cls.end_time <= now).all()
                logger.debug(f"ModelBot.time_check found {len(items)} items to delete")
                rows_deleted  = F.db.session.query(cls).filter(cls.end_time <= now).delete()
                F.db.session.commit()
        except Exception as e:
            logger.error(f'Exception:{str(e)}')
            logger.error(traceback.format_exc())