'''
Description: 
Date: 2026-04-04 15:32:48
LastEditTime: 2026-04-06 19:10:56
FilePath: \XianYuApis\XianyuApis.py
'''
import json
import os
import time

import requests

from utils.goofish_utils import generate_sign, trans_cookies, generate_device_id


class XianyuApis:
    def __init__(self, cookies, device_id):
        self.login_url = 'https://h5api.m.goofish.com/h5/mtop.taobao.idlemessage.pc.login.token/1.0/'
        self.upload_media_url = 'https://stream-upload.goofish.com/api/upload.api'
        self.session = requests.Session()
        self.session.cookies.update(cookies)
        self.device_id = device_id

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
        response = self.session.post(self.login_url, params=params, headers=headers, data=data, verify=False)
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
            response = self.session.post(self.upload_media_url, headers=headers, params=params, files=files, verify=False)
            res_json = response.json()
            return res_json



if __name__ == '__main__':
    cookies_str = r''
    cookies = trans_cookies(cookies_str)
    xianyu = XianyuApis(cookies, generate_device_id(cookies['unb']))
    res = xianyu.get_token()
    print(json.dumps(res, indent=4, ensure_ascii=False))

    res = xianyu.upload_media(r"D:\Desktop\1.png")
    print(json.dumps(res, indent=4, ensure_ascii=False))
