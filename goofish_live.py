import base64
import json
import asyncio
import inspect
import os
import re
import threading
import time
from collections import deque

from loguru import logger
import requests
import websockets
from goofish_apis import XianyuApis, qrcode_login

from utils.goofish_utils import generate_mid, generate_uuid, trans_cookies, generate_device_id, decrypt, \
    get_session_cookies_str
from message import Message, make_text, make_image


class XianyuLive:
    def __init__(self, cookies_str, message_handler=None, reply_sent_handler=None):
        self.base_url = 'wss://wss-goofish.dingtalk.com/'
        self.cookies_str = cookies_str
        self.cookies = trans_cookies(cookies_str)
        self.myid = self.cookies['unb']
        self.device_id = generate_device_id(self.myid)
        self.xianyu = XianyuApis(self.cookies, self.device_id)
        self.ws = None
        self.loop = None
        self.message_handler = message_handler
        self.reply_sent_handler = reply_sent_handler
        self.recent_outgoing = deque(maxlen=50)
        self.default_reply = '你好，消息已收到，我稍后回复你。'
        self.keyword_replies = [
            (('在吗', '在不在', '有人吗'), '你好，在的，请说下你的问题或想咨询的商品。'),
            (('价格', '多少钱', '最低', '便宜点', '少点'), '价格以商品页面为准。如果你想确认优惠空间，可以直接告诉我你看中的商品。'),
            (('包邮', '邮费', '运费'), '邮费和发货方式以商品页说明为准，你也可以把商品链接发我，我帮你确认。'),
            (('发货', '多久发', '什么时候发'), '正常会尽快安排处理，具体发货时间我会尽快确认后回复你。'),
            (('图片', '细节图', '实拍'), '可以的，你告诉我想看哪个位置或细节，我稍后给你补充。'),
            (('真假', '正品', '全新'), '商品具体成色和情况以页面说明为准，如果你有特别关心的点可以直接问我。'),
        ]
        self.ai_api_url = os.getenv('AI_API_URL', '').strip()
        self.ai_api_key = os.getenv('AI_API_KEY', '').strip()
        self.ai_model = os.getenv('AI_MODEL', '').strip()
        self.ai_system_prompt = os.getenv(
            'AI_SYSTEM_PROMPT',
            '你是闲鱼卖家的客服助手。回复要简短、礼貌、自然，优先回答买家问题，不要编造库存、发货、优惠信息。'
        ).strip()

    def _match_keyword_reply(self, send_message: str):
        normalized = (send_message or '').strip().lower()
        for keywords, reply in self.keyword_replies:
            if any(keyword in normalized for keyword in keywords):
                return reply
        return None

    def _call_ai_reply(self, send_user_name: str, send_message: str):
        if not (self.ai_api_url and self.ai_api_key and self.ai_model):
            return None

        payload = {
            'model': self.ai_model,
            'messages': [
                {'role': 'system', 'content': self.ai_system_prompt},
                {'role': 'user', 'content': f'买家昵称：{send_user_name}\n买家消息：{send_message}'},
            ],
            'temperature': 0.6,
        }
        headers = {
            'Authorization': f'Bearer {self.ai_api_key}',
            'Content-Type': 'application/json',
        }
        response = requests.post(
            self.ai_api_url,
            headers=headers,
            json=payload,
            timeout=30,
            proxies={'http': None, 'https': None},
        )
        response.raise_for_status()
        data = response.json()
        content = data['choices'][0]['message']['content'].strip()
        return content or None

    async def build_reply(self, send_user_name: str, send_message: str):
        keyword_reply = self._match_keyword_reply(send_message)
        if keyword_reply:
            return {'reply': keyword_reply, 'source': 'rule'}

        try:
            ai_reply = await asyncio.to_thread(self._call_ai_reply, send_user_name, send_message)
            if ai_reply:
                return {'reply': ai_reply, 'source': 'ai'}
        except Exception as e:
            logger.warning(f'ai reply failed: {e}')

        return {'reply': self.default_reply, 'source': 'fallback'}

    async def _call_hook(self, hook, payload):
        result = hook(payload)
        if inspect.isawaitable(result):
            return await result
        return result

    async def resolve_reply(self, context):
        if self.message_handler:
            result = await self._call_hook(self.message_handler, context)
            if isinstance(result, str):
                return {'reply': result, 'source': 'custom'}
            return result or {}
        return await self.build_reply(context['send_user_name'], context['send_message'])

    async def list_all_conversations(self, cid):
        headers = {
            "Cookie": get_session_cookies_str(self.xianyu.session),
            "Host": "wss-goofish.dingtalk.com",
            "Connection": "Upgrade",
            "Pragma": "no-cache",
            "Cache-Control": "no-cache",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
            "Origin": "https://www.goofish.com",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }
        async with websockets.connect(self.base_url, additional_headers=headers, proxy=None) as websocket:
            asyncio.create_task(self.init(websocket))
            send_mid = generate_mid()
            msg = {
                "lwp": "/r/MessageManager/listUserMessages",
                "headers": {
                    "mid": send_mid
                },
                "body": [
                    f"{cid}@goofish",
                    False,
                    9007199254740991,
                    20,
                    False
                ]
            }
            user_message_models = []
            async for message in websocket:
                try:
                    message = json.loads(message)
                    ack = {
                        "code": 200,
                        "headers": {
                            "mid": message["headers"]["mid"] if "mid" in message["headers"] else generate_mid(),
                            "sid": message["headers"]["sid"] if "sid" in message["headers"] else '',
                        }
                    }
                    if 'app-key' in message["headers"]:
                        ack["headers"]["app-key"] = message["headers"]["app-key"]
                    if 'ua' in message["headers"]:
                        ack["headers"]["ua"] = message["headers"]["ua"]
                    if 'dt' in message["headers"]:
                        ack["headers"]["dt"] = message["headers"]["dt"]
                    await websocket.send(json.dumps(ack))
                except Exception as e:
                    pass
                try:
                    if 'lwp' in message and message['lwp'] == "/s/vulcan":
                        await websocket.send(json.dumps(msg))
                    recv_mid = message["headers"]["mid"] if "mid" in message["headers"] else ''
                    if recv_mid == send_mid:
                        logger.info(f"user history message: {message}")
                        has_more = message["body"]["hasMore"] == 1
                        next_cursor = message["body"]["nextCursor"]
                        for user_message in message["body"]["userMessageModels"]:
                            send_user_name = user_message["message"]["extension"]["reminderTitle"]
                            send_user_id = user_message["message"]["extension"]["senderUserId"]
                            send_message_base64 = user_message["message"]["content"]["custom"]["data"]
                            send_message_json = json.loads(base64.b64decode(send_message_base64).decode('utf-8'))
                            user_message_models.insert(0, {
                                "send_user_id": send_user_id,
                                "send_user_name": send_user_name,
                                "message": send_message_json
                            })
                        if has_more:
                            logger.info(f"has more history messages, next cursor: {next_cursor}")
                            send_mid = generate_mid()
                            msg["headers"]["mid"] = send_mid
                            msg["body"][2] = next_cursor
                            await websocket.send(json.dumps(msg))
                        else:
                            return user_message_models
                except Exception as e:
                    return user_message_models

    async def create_chat(self, ws, toid, item_id='891198795482'):
        msg = {
            "lwp": "/r/SingleChatConversation/create",
            "headers": {
                "mid": generate_mid()
            },
            "body": [
                {
                    "pairFirst": f"{toid}@goofish",
                    "pairSecond": f"{self.myid}@goofish",
                    "bizType": "1",
                    "extension": {
                        "itemId": item_id
                    },
                    "ctx": {
                        "appVersion": "1.0",
                        "platform": "web"
                    }
                }
            ]
        }
        await ws.send(json.dumps(msg))

    async def send_msg(self, ws, cid, toid, message: Message):
        msg_type = message["type"]
        msg = {
            "lwp": "/r/MessageSend/sendByReceiverScope",
            "headers": {
                "mid": generate_mid()
            },
            "body": [
                {
                    "uuid": generate_uuid(),
                    "cid": f"{cid}@goofish",
                    "conversationType": 1,
                    "content": {
                        "contentType": 101,
                        "custom": {
                            "type": None,
                            "data": None
                        }
                    },
                    "redPointPolicy": 0,
                    "extension": {
                        "extJson": "{}"
                    },
                    "ctx": {
                        "appVersion": "1.0",
                        "platform": "web"
                    },
                    "mtags": {},
                    "msgReadStatusSetting": 1
                },
                {
                    "actualReceivers": [
                        f"{toid}@goofish",
                        f"{self.myid}@goofish"
                    ]
                }
            ]
        }
        if msg_type == "text":
            payload = {
                "contentType": 1,
                "text": {
                    "text": message["text"]
                }
            }
            text_base64 = str(base64.b64encode(json.dumps(payload).encode('utf-8')), 'utf-8')
            msg["body"][0]["content"]["custom"]["type"] = 1
            msg["body"][0]["content"]["custom"]["data"] = text_base64
        elif msg_type == "image":
            payload = {
                "contentType": 2,
                "image": {
                    "pics": [
                        {
                            "type": 0,
                            "url": message["image_url"],
                            "width": message["width"],
                            "height": message["height"]
                        }
                    ]
                }
            }
            image_base64 = str(base64.b64encode(json.dumps(payload).encode('utf-8')), 'utf-8')
            msg["body"][0]["content"]["custom"]["type"] = 2
            msg["body"][0]["content"]["custom"]["data"] = image_base64
        elif msg_type == "audio":
            # TODO: handle audio message
            logger.error(f"不支持的消息类型: {msg_type}")
            return
        else:
            logger.error(f"不支持的消息类型: {msg_type}")
            return
        await ws.send(json.dumps(msg))
        if msg_type == "text":
            self.recent_outgoing.append({
                'cid': str(cid),
                'text': message["text"],
                'created_at': time.time(),
            })

    async def init(self, ws):
        data = self.xianyu.get_token()
        token = data['data']['accessToken'] if 'data' in data and 'accessToken' in data['data'] else ''
        if not token:
            logger.error('获取token失败')
            exit(0)
        msg = {
            "lwp": "/reg",
            "headers": {
                "cache-header": "app-key token ua wv",
                "app-key": "444e9908a51d1cb236a27862abc769c9",
                "token": token,
                "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36 DingTalk(2.1.5) OS(Windows/10) Browser(Chrome/133.0.0.0) DingWeb/2.1.5 IMPaaS DingWeb/2.1.5",
                "dt": "j",
                "wv": "im:3,au:3,sy:6",
                "sync": "0,0;0;0;",
                "did": self.device_id,
                "mid": generate_mid()
            }
        }
        await ws.send(json.dumps(msg))
        current_time = int(time.time() * 1000)
        msg = {
            "lwp": "/r/SyncStatus/ackDiff",
            "headers": {"mid": generate_mid()},
            "body": [
                {
                    "pipeline": "sync",
                    "tooLong2Tag": "PNM,1",
                    "channel": "sync",
                    "topic": "sync",
                    "highPts": 0,
                    "pts": current_time * 1000,
                    "seq": 0,
                    "timestamp": current_time
                }
            ]
        }
        await ws.send(json.dumps(msg))
        logger.info('init')

    async def heart_beat(self, ws):
        while True:
            msg = {
                "lwp": "/!",
                "headers": {
                    "mid": generate_mid()
                 }
            }
            await ws.send(json.dumps(msg))
            await asyncio.sleep(15)

    def user_alive(self):
        while True:
            time.sleep(600)
            self.xianyu.refresh_token()

    async def main(self):
        headers = {
            "Cookie": get_session_cookies_str(self.xianyu.session),
            "Host": "wss-goofish.dingtalk.com",
            "Connection": "Upgrade",
            "Pragma": "no-cache",
            "Cache-Control": "no-cache",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
            "Origin": "https://www.goofish.com",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }
        threading.Thread(target=self.user_alive).start()
        async with websockets.connect(self.base_url, additional_headers=headers, proxy=None) as websocket:
            self.loop = asyncio.get_running_loop()
            self.ws = websocket
            asyncio.create_task(self.init(websocket))
            asyncio.create_task(self.heart_beat(websocket))
            async for message in websocket:
                # logger.info(f"message: {message}")
                message = json.loads(message)
                ack = {
                    "code": 200,
                    "headers": {
                        "mid": message["headers"]["mid"] if "mid" in message["headers"] else generate_mid(),
                        "sid": message["headers"]["sid"] if "sid" in message["headers"] else '',
                    }
                }
                if 'app-key' in message["headers"]:
                    ack["headers"]["app-key"] = message["headers"]["app-key"]
                if 'ua' in message["headers"]:
                    ack["headers"]["ua"] = message["headers"]["ua"]
                if 'dt' in message["headers"]:
                    ack["headers"]["dt"] = message["headers"]["dt"]
                await websocket.send(json.dumps(ack))

                await self.handle_message(message, websocket)

    async def send_text(self, cid, toid, text):
        if not self.ws:
            raise RuntimeError('WebSocket is not connected')
        await self.send_msg(self.ws, cid, toid, make_text(text))

    def is_recent_self_echo(self, cid, text):
        now = time.time()
        for item in reversed(self.recent_outgoing):
            if now - item['created_at'] > 180:
                continue
            if item['cid'] == str(cid) and item['text'] == text:
                return True
        return False

    def extract_chat_payload(self, message):
        if not isinstance(message, dict):
            return None

        if "1" in message and isinstance(message["1"], dict) and "10" in message["1"]:
            return message

        for value in message.values():
            if isinstance(value, dict):
                nested = self.extract_chat_payload(value)
                if nested:
                    return nested
            elif isinstance(value, list):
                for item in value:
                    nested = self.extract_chat_payload(item)
                    if nested:
                        return nested
        return None

    def extract_item_context(self, message):
        context = {
            'item_id': None,
            'item_title': None,
            'item_url': None,
            'item_cover': None,
            'item_context_source': None,
        }

        def save_item_id(value, source):
            if not value:
                return
            text = str(value)
            match = re.search(r'(\d{8,})', text)
            candidate = match.group(1) if match else text
            if candidate.isdigit() and len(candidate) >= 8 and not context['item_id']:
                context['item_id'] = candidate
                context['item_context_source'] = source

        def walk(node, source='message'):
            if isinstance(node, dict):
                for key, value in node.items():
                    lower = str(key).lower()
                    if lower in {'itemid', 'item_id', 'itemidstr'}:
                        save_item_id(value, source)
                    elif lower in {'targeturl', 'url', 'link'} and isinstance(value, str):
                        if not context['item_url'] and value.startswith(('http', 'fleamarket', 'goofish')):
                            context['item_url'] = value
                        save_item_id(value, source)
                    elif lower in {'title', 'itemtitle'} and isinstance(value, str) and not context['item_title']:
                        context['item_title'] = value
                    elif lower in {'image', 'img', 'cover', 'mainpic'} and isinstance(value, str) and value.startswith('http') and not context['item_cover']:
                        context['item_cover'] = value
                    walk(value, source)
            elif isinstance(node, list):
                for item in node:
                    walk(item, source)
            elif isinstance(node, str):
                save_item_id(node, source)

        walk(message)
        if context['item_id']:
            return context
        return None

    def collect_item_hints(self, message):
        hints = []

        def walk(node, path='root'):
            if isinstance(node, dict):
                for key, value in node.items():
                    next_path = f'{path}.{key}'
                    lower = str(key).lower()
                    if lower in {'itemid', 'item_id', 'itemidstr', 'targeturl', 'url', 'link', 'title', 'itemtitle', 'image', 'img', 'cover', 'mainpic'}:
                        preview = str(value)
                        if len(preview) > 160:
                            preview = preview[:160] + '...'
                        hints.append({'path': next_path, 'value': preview})
                    walk(value, next_path)
            elif isinstance(node, list):
                for idx, item in enumerate(node[:10]):
                    walk(item, f'{path}[{idx}]')
            elif isinstance(node, str):
                if re.search(r'(\d{8,})', node):
                    preview = node[:160] + ('...' if len(node) > 160 else '')
                    hints.append({'path': path, 'value': preview})

        walk(message)
        dedup = []
        seen = set()
        for hint in hints:
            key = (hint['path'], hint['value'])
            if key in seen:
                continue
            seen.add(key)
            dedup.append(hint)
        return dedup[:20]

    async def process_chat_message(self, message, websocket):
        chat_message = self.extract_chat_payload(message)
        if not chat_message:
            return False

        send_user_name = chat_message["1"]["10"].get("reminderTitle", "")
        send_user_id = chat_message["1"]["10"].get("senderUserId", "")
        send_message = chat_message["1"]["10"].get("reminderContent", "")
        cid = chat_message["1"]["2"].split('@')[0]

        logger.info(f"message direction check: sender={send_user_id}, self={self.myid}, cid={cid}")

        if str(send_user_id) == str(self.myid) and self.is_recent_self_echo(cid, send_message):
            logger.info("skip self echo message")
            return True

        logger.info(f"user: {send_user_name}, 发送给我的信息 message: {send_message}")

        item_context = self.extract_item_context(chat_message)
        item_hints = self.collect_item_hints(chat_message)
        logger.info(f"item probe: item_context={item_context}, hints={json.dumps(item_hints, ensure_ascii=False)}")

        context = {
            'send_user_name': send_user_name,
            'send_user_id': send_user_id,
            'send_message': send_message,
            'cid': cid,
            'raw_message': chat_message,
            'item_context': item_context,
            'item_fetcher': self.xianyu.get_item_info,
        }
        decision = await self.resolve_reply(context)
        reply = (decision or {}).get('reply')
        reply_source = (decision or {}).get('source', 'unknown')
        if reply:
            await self.send_msg(websocket, cid, send_user_id, make_text(reply))
            if self.reply_sent_handler:
                await self._call_hook(self.reply_sent_handler, {
                    **context,
                    'reply': reply,
                    'reply_source': reply_source,
                    'incoming_message_id': (decision or {}).get('incoming_message_id'),
                    'matched_rule_id': (decision or {}).get('matched_rule_id'),
                    'matched_doc_id': (decision or {}).get('matched_doc_id'),
                })
        return True

    async def handle_message(self, message, websocket):
        data = None
        if not isinstance(message, dict) or "body" not in message:
            return

        try:
            data = message["body"]["syncPushPackage"]["data"][0]["data"]
            try:
                parsed = json.loads(data)
            except Exception:
                parsed = None

            if isinstance(parsed, dict):
                handled = await self.process_chat_message(parsed, websocket)
                if handled:
                    logger.info("received plain sync payload")
                    return
        except Exception as sync_err:
            logger.debug(f"sync payload parse failed: {sync_err}")
            return

        try:
            decrypted = decrypt(data)
            parsed = json.loads(decrypted)
            handled = await self.process_chat_message(parsed, websocket)
            if not handled:
                logger.debug("decrypted payload is not a chat message")
        except Exception as e:
            logger.debug(f"handle_message decode failed: {e}")


if __name__ == '__main__':
    xianyu = qrcode_login()
    cookies_str = '; '.join(
        f'{c.name}={c.value}'
        for c in xianyu.session.cookies
        if c.domain and '.goofish.com' in c.domain
    )
    xianyuLive = XianyuLive(cookies_str)

    # 1 获取全部聊天记录
    # cid = '47812870000'
    # all_messages = asyncio.run(xianyuLive.list_all_conversations(cid))
    # for message in all_messages:
    #     print(message)

    # 2 常驻进程 用于接收消息和自动回复
    asyncio.run(xianyuLive.main())
