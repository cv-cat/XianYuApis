'''
Description: 
Date: 2026-04-04 15:32:48
LastEditTime: 2026-04-06 19:10:56
FilePath: \XianYuApis\XianyuApis.py
'''
import json
import os
import time
from typing import Optional, List

import requests

from message.types import Price, DeliverySettings
from utils.goofish_utils import generate_sign, trans_cookies, generate_device_id


class XianyuApis:
    def __init__(self, cookies, device_id):
        self.login_url = 'https://h5api.m.goofish.com/h5/mtop.taobao.idlemessage.pc.login.token/1.0/'
        self.upload_media_url = 'https://stream-upload.goofish.com/api/upload.api'
        self.refresh_token_url = 'https://h5api.m.goofish.com/h5/mtop.taobao.idlemessage.pc.loginuser.get/1.0/'
        self.item_detail_url = 'https://h5api.m.goofish.com/h5/mtop.taobao.idle.pc.detail/1.0/'
        self.reset_login_info_url = 'https://passport.goofish.com/newlogin/hasLogin.do'
        self.session = requests.Session()
        self.session.cookies.update(cookies)
        self.device_id = device_id
        self.cookies = {}

    def get_token(self):
        headers = {
            "Host": "h5api.m.goofish.com",
            "sec-ch-ua-platform": "\"Windows\"",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
            "accept": "application/json",
            "sec-ch-ua": "\"Chromium\";v=\"146\", \"Not-A.Brand\";v=\"24\", \"Google Chrome\";v=\"146\"",
            "content-type": "application/x-www-form-urlencoded",
            "sec-ch-ua-mobile": "?0",
            "origin": "https://www.goofish.com",
            "sec-fetch-site": "same-site",
            "sec-fetch-mode": "cors",
            "sec-fetch-dest": "empty",
            "referer": "https://www.goofish.com/",
            "accept-language": "en,zh-CN;q=0.9,zh;q=0.8,zh-TW;q=0.7,ja;q=0.6",
            "priority": "u=1, i"
        }
        params = {
            'jsv': '2.7.2',
            'appKey': '34839810',
            't': str(int(time.time()) * 1000),
            'sign': '',
            'v': '1.0',
            'type': 'originaljson',
            'accountSite': 'xianyu',
            'dataType': 'json',
            'timeout': '20000',
            'api': 'mtop.taobao.idlemessage.pc.login.token',
            'sessionOption': 'AutoLoginOnly',
            'spm_cnt': 'a21ybx.im.0.0',
            "spm_pre": "a21ybx.item.want.1.14ad3da6ALVq3n",
            "log_id": "14ad3da6ALVq3n"
        }
        data_val = '{"appKey":"444e9908a51d1cb236a27862abc769c9","deviceId":"' + self.device_id + '"}'
        data = {
            'data': data_val,
        }
        token = self.session.cookies['_m_h5_tk'].split('_')[0]
        sign = generate_sign(params['t'], token, data_val)
        params['sign'] = sign
        response = self.session.post(self.login_url, params=params, headers=headers, data=data)
        for response_cookie_key in response.cookies.get_dict().keys():
            if response_cookie_key in self.session.cookies.get_dict().keys():
                for key in self.session.cookies:
                    if key.name == response_cookie_key and key.domain == '' and key.path == '/':
                        self.session.cookies.clear(domain=key.domain, path=key.path, name=key.name)
                        break
        res_json = response.json()
        if 'ret' in res_json and '令牌过期' in res_json['ret'][0]:
            return self.get_token()
        return res_json


    def refresh_token(self):
        headers = {
            "accept": "application/json",
            "accept-language": "en,zh-CN;q=0.9,zh;q=0.8,zh-TW;q=0.7,ja;q=0.6",
            "cache-control": "no-cache",
            "content-type": "application/x-www-form-urlencoded",
            "origin": "https://www.goofish.com",
            "pragma": "no-cache",
            "priority": "u=1, i",
            "referer": "https://www.goofish.com/",
            "sec-ch-ua": "\"Chromium\";v=\"146\", \"Not-A.Brand\";v=\"24\", \"Google Chrome\";v=\"146\"",
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": "\"Windows\"",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-site",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"
        }
        params = {
            "jsv": "2.7.2",
            "appKey": "34839810",
            "t": str(int(time.time()) * 1000),
            "v": "1.0",
            "type": "originaljson",
            "accountSite": "xianyu",
            "dataType": "json",
            "timeout": "20000",
            "api": "mtop.taobao.idlemessage.pc.loginuser.get",
            "sessionOption": "AutoLoginOnly",
            "spm_cnt": "a21ybx.im.0.0",
            "spm_pre": "a21ybx.item.want.1.12523da6waCtUp",
            "log_id": "12523da6waCtUp"
        }
        data_val = '{}'
        data = {
            'data': data_val,
        }
        token = self.session.cookies['_m_h5_tk'].split('_')[0]
        sign = generate_sign(params['t'], token, data_val)
        params['sign'] = sign
        response = self.session.post(self.refresh_token_url, headers=headers, params=params, data=data)
        for response_cookie_key in response.cookies:
            if response_cookie_key in self.session.cookies:
                for key in self.session.cookies:
                    if key.name == response_cookie_key and key.domain == '' and key.path == '/':
                        del self.session.cookies[key]
                        break
        res_json = response.json()
        return res_json

    def upload_media(self, media_path):
        headers = {
            "accept": "*/*",
            "accept-language": "en,zh-CN;q=0.9,zh;q=0.8,zh-TW;q=0.7,ja;q=0.6",
            "cache-control": "no-cache",
            "origin": "https://www.goofish.com",
            "pragma": "no-cache",
            "priority": "u=1, i",
            "referer": "https://www.goofish.com/",
            "sec-ch-ua": "\"Chromium\";v=\"146\", \"Not-A.Brand\";v=\"24\", \"Google Chrome\";v=\"146\"",
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": "\"Windows\"",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-site",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"
        }
        params = {
            "floderId": "0",
            "appkey": "xy_chat",
            "_input_charset": "utf-8"
        }
        with open(media_path, 'rb') as f:
            media_name = os.path.basename(media_path)
            files = {
                "file": (media_name, f, "image/png")
            }
            response = self.session.post(self.upload_media_url, headers=headers, params=params, files=files)
            res_json = response.json()
            return res_json

    def get_item_info(self, item_id):
        params = {
            'jsv': '2.7.2',
            'appKey': '34839810',
            't': str(int(time.time()) * 1000),
            'sign': '',
            'v': '1.0',
            'type': 'originaljson',
            'accountSite': 'xianyu',
            'dataType': 'json',
            'timeout': '20000',
            'api': 'mtop.taobao.idle.pc.detail',
            'sessionOption': 'AutoLoginOnly',
            'spm_cnt': 'a21ybx.im.0.0',
            "spm_pre": "a21ybx.item.want.1.12523da6waCtUp",
            "log_id": "12523da6waCtUp"
        }
        data_val = '{"itemId":"' + item_id + '"}'
        data = {
            'data': data_val,
        }
        token = self.session.cookies.get('_m_h5_tk', '').split('_')[0]
        sign = generate_sign(params['t'], token, data_val)
        params['sign'] = sign
        response = self.session.post(self.item_detail_url, params=params, data=data)
        res_json = response.json()
        return res_json


    def get_public_channel(self, title, images_info):
        headers = {
            "accept": "application/json",
            "accept-language": "en,zh-CN;q=0.9,zh;q=0.8,zh-TW;q=0.7,ja;q=0.6",
            "cache-control": "no-cache",
            "content-type": "application/x-www-form-urlencoded",
            "origin": "https://www.goofish.com",
            "pragma": "no-cache",
            "priority": "u=1, i",
            "referer": "https://www.goofish.com/",
            "sec-ch-ua": "\"Chromium\";v=\"146\", \"Not-A.Brand\";v=\"24\", \"Google Chrome\";v=\"146\"",
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": "\"Windows\"",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-site",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"
        }
        url = "https://h5api.m.goofish.com/h5/mtop.taobao.idle.kgraph.property.recommend/2.0/"
        params = {
            "jsv": "2.7.2",
            "appKey": "34839810",
            "t": str(int(time.time()) * 1000),
            "sign": "",
            "v": "2.0",
            "type": "originaljson",
            "accountSite": "xianyu",
            "dataType": "json",
            "timeout": "20000",
            "api": "mtop.taobao.idle.kgraph.property.recommend",
            "sessionOption": "AutoLoginOnly",
            "spm_cnt": "a21ybx.publish.0.0",
            "spm_pre": "a21ybx.item.sidebar.1.67321598K9Vgx8",
            "log_id": "67321598K9Vgx8"
        }
        data = {
            "title": title,
            "lockCpv": False,
            "multiSKU": False,
            "publishScene": "mainPublish",
            "scene": "newPublishChoice",
            "description": title,
            "imageInfos": [],
            "uniqueCode": "1775905618164677"
        }
        for image_info in images_info:
            data['imageInfos'].append({
                "extraInfo": {
                    "isH": "false",
                    "isT": "false",
                    "raw": "false"
                },
                "isQrCode": False,
                "url": image_info['url'],
                "heightSize": image_info['height'],
                "widthSize": image_info['width'],
                "major": True,
                "type": 0,
                "status": "done"
            })
        data_val = json.dumps(data, separators=(',', ':'))
        data = {
            "data": data_val
        }
        token = self.session.cookies.get('_m_h5_tk', '').split('_')[0]
        sign = generate_sign(params['t'], token, data_val)
        params['sign'] = sign
        response = self.session.post(url, headers=headers, params=params, data=data)
        res_json = response.json()
        return res_json

    def get_default_location(self):
        headers = {
            "accept": "application/json",
            "accept-language": "en,zh-CN;q=0.9,zh;q=0.8,zh-TW;q=0.7,ja;q=0.6",
            "cache-control": "no-cache",
            "content-type": "application/x-www-form-urlencoded",
            "eagleeye-userdata": "spm-cnt=a21ybx",
            "origin": "https://www.goofish.com",
            "pragma": "no-cache",
            "priority": "u=1, i",
            "referer": "https://www.goofish.com/",
            "sec-ch-ua": "\"Chromium\";v=\"146\", \"Not-A.Brand\";v=\"24\", \"Google Chrome\";v=\"146\"",
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": "\"Windows\"",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-site",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"
        }
        url = "https://h5api.m.goofish.com/h5/mtop.taobao.idle.local.poi.get/1.0/"
        params = {
            "jsv": "2.7.2",
            "appKey": "34839810",
            "t": str(int(time.time()) * 1000),
            "sign": "",
            "v": "1.0",
            "type": "originaljson",
            "accountSite": "xianyu",
            "dataType": "json",
            "timeout": "20000",
            "api": "mtop.taobao.idle.local.poi.get",
            "sessionOption": "AutoLoginOnly",
            "spm_cnt": "a21ybx.publish.0.0",
            "spm_pre": "a21ybx.item.sidebar.1.38262218ame5nr",
            "log_id": "38262218ame5nr"
        }
        data_val = "{\"longitude\":118.78248347393424,\"latitude\":31.91629189813543}"
        data = {
            "data": data_val
        }
        token = self.session.cookies.get('_m_h5_tk', '').split('_')[0]
        sign = generate_sign(params['t'], token, data_val)
        params['sign'] = sign
        response = self.session.post(url, headers=headers, params=params, data=data)
        res_json = response.json()
        return res_json

    def public(self, images_path: List[str], goods_desc: str, price: Optional[Price], ds: DeliverySettings):
        headers = {
            "accept": "application/json",
            "accept-language": "en,zh-CN;q=0.9,zh;q=0.8,zh-TW;q=0.7,ja;q=0.6",
            "cache-control": "no-cache",
            "content-type": "application/x-www-form-urlencoded",
            "origin": "https://www.goofish.com",
            "pragma": "no-cache",
            "priority": "u=1, i",
            "referer": "https://www.goofish.com/",
            "sec-ch-ua": "\"Chromium\";v=\"146\", \"Not-A.Brand\";v=\"24\", \"Google Chrome\";v=\"146\"",
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": "\"Windows\"",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-site",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"
        }
        url = "https://h5api.m.goofish.com/h5/mtop.idle.pc.idleitem.publish/1.0/"
        params = {
            "jsv": "2.7.2",
            "appKey": "34839810",
            "t": str(int(time.time()) * 1000),
            "sign": "",
            "v": "1.0",
            "type": "originaljson",
            "accountSite": "xianyu",
            "dataType": "json",
            "timeout": "20000",
            "api": "mtop.idle.pc.idleitem.publish",
            "sessionOption": "AutoLoginOnly",
            "spm_cnt": "a21ybx.publish.0.0",
            "spm_pre": "a21ybx.home.sidebar.1.46413da6EPl7v5",
            "log_id": "46413da6EPl7v5"
        }
        data = {
            "freebies": False,
            "itemTypeStr": "b",
            "quantity": "1",
            "simpleItem": "true",
            "imageInfoDOList": [],
            "itemTextDTO": {
                "desc": goods_desc,
                "title": goods_desc,
                "titleDescSeparate": False
            },
            "itemLabelExtList": [],
            "itemPriceDTO": {},
            "userRightsProtocols": [
                {
                    "enable": False,
                    "serviceCode": "SKILL_PLAY_NO_MIND"
                }
            ],
            "itemPostFeeDTO": {
                "canFreeShipping": False,
                "supportFreight": False,
                "onlyTakeSelf": False
            },
            "itemAddrDTO": {},
            "defaultPrice": False,
            "itemCatDTO": {},
            "uniqueCode": "1775897582791680",
            "sourceId": "pcMainPublish",
            "bizcode": "pcMainPublish",
            "publishScene": "pcMainPublish"
        }
        images_info = []
        if images_path:
            for image_path in images_path:
                res_json = self.upload_media(image_path)
                image_object = res_json["object"]
                width, height = map(int, image_object["pix"].split('x'))
                image_info = {
                    "url": image_object["url"],
                    "height": height,
                    "width": width
                }
                images_info.append(image_info)
                data['imageInfoDOList'].append({
                    "extraInfo": {
                        "isH": "false",
                        "isT": "false",
                        "raw": "false"
                    },
                    "isQrCode": False,
                    "url": image_info['url'],
                    "heightSize": image_info['height'],
                    "widthSize": image_info['width'],
                    "major": True,
                    "type": 0,
                    "status": "done"
                })
        if ds["choice"] == "包邮":
            data["itemPostFeeDTO"]["canFreeShipping"] = True
            data["itemPostFeeDTO"]["supportFreight"] = True
        elif ds["choice"] == "按距离计费":
            data["itemPostFeeDTO"]["supportFreight"] = True
            data["itemPostFeeDTO"]["templateId"] = "-100"
        elif ds["choice"] == "一口价":
            data["itemPostFeeDTO"]["supportFreight"] = True
            data["itemPostFeeDTO"]["postPriceInCent"] = str(int(ds["post_price"] * 100))
            data["itemPostFeeDTO"]["templateId"] = "0"
        elif ds["choice"] == "无需邮寄":
            data["itemPostFeeDTO"]["templateId"] = "0"
        else:
            raise ValueError("Invalid delivery choice")
        if ds["can_self_pickup"]:
            data["onlyTakeSelf"] = True
        if price:
            if price["current_price"] > 0:
                data["itemPriceDTO"]["priceInCent"] = str(int(price["current_price"] * 100))
            if price["original_price"] > 0:
                data["itemPriceDTO"]["origPriceInCent"] = str(int(price["original_price"] * 100))
        else:
            data["defaultPrice"] = True
        channel_res = self.get_public_channel(goods_desc, images_info)
        for card in channel_res["data"]["cardList"]:
            card_data = card["cardData"]
            for card_value in card_data["valuesList"] if "valuesList" in card_data.keys() else []:
                if "isClicked" in card_value.keys() and card_value["isClicked"]:
                    data["itemLabelExtList"].append({
                        "channelCateName": card_value["catName"],
                        "valueId": None,
                        "channelCateId": card_value["channelCatId"],
                        "valueName": None,
                        "tbCatId": card_value["tbCatId"],
                        "subPropertyId": None,
                        "labelType": "common",
                        "subValueId": None,
                        "labelId": None,
                        "propertyName": card_data["propertyName"],
                        "isUserClick": "1",
                        "isUserCancel": None,
                        "from": "newPublishChoice",
                        "propertyId": card_data["propertyId"],
                        "labelFrom": "newPublish",
                        "text": card_value["catName"],
                        "properties": f'{card_data["propertyId"]}##{card_data["propertyName"]}:{card_value["channelCatId"]}##{card_value["catName"]}'
                    })
                    break

        data["itemCatDTO"] = {
            "catId": str(channel_res["data"]["categoryPredictResult"]["catId"]),
            "catName":  str(channel_res["data"]["categoryPredictResult"]["catName"]),
            "channelCatId": str(channel_res["data"]["categoryPredictResult"]["channelCatId"]),
            "tbCatId": str(channel_res["data"]["categoryPredictResult"]["tbCatId"])
        }

        location_res = self.get_default_location()["data"]["commonAddresses"][0]
        data["itemAddrDTO"] = {
            "area": location_res["area"],
            "city": location_res["city"],
            "divisionId": location_res["divisionId"],
            "gps": f"{location_res['longitude']},{location_res['latitude']}",
            "poiId": location_res["poiId"],
            "poiName": location_res["poi"],
            "prov": location_res["prov"]
        }

        data_val = json.dumps(data, separators=(',', ':'))
        data = {
            "data": data_val
        }
        token = self.session.cookies.get('_m_h5_tk', '').split('_')[0]
        sign = generate_sign(params['t'], token, data_val)
        params['sign'] = sign
        response = self.session.post(url, headers=headers, params=params, data=data)
        res_json = response.json()
        return res_json


if __name__ == '__main__':
    cookies_str = r''
    cookies = trans_cookies(cookies_str)
    xianyu = XianyuApis(cookies, generate_device_id(cookies['unb']))
    # res = xianyu.get_token()
    # print(json.dumps(res, indent=4, ensure_ascii=False))

    # res = xianyu.upload_media(r"D:\Desktop\1.png")
    # print(json.dumps(res, indent=4, ensure_ascii=False))

    # res = xianyu.refresh_token()
    # print(json.dumps(res, indent=4, ensure_ascii=False))

    # res = xianyu.get_item_info('1001160709960')
    # print(json.dumps(res, indent=4, ensure_ascii=False))

    res = xianyu.public(
        images_path=[r"D:\Desktop\logo.jpg"],
        goods_desc="测试发布111222",
        price=None,
        ds={"choice": "一口价", "post_price": 0.01, "can_self_pickup": True}
    )
    print(json.dumps(res, indent=4, ensure_ascii=False))