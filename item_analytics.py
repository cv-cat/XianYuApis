"""闲鱼小铺商品数据接口。仅查询当前登录账号有权查看的数据。"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from http.cookies import SimpleCookie
from pathlib import Path

import requests

API = "mtop.alibaba.idle.seller.pc.datacompass.item.list"
INDICATORS_API = "mtop.alibaba.idle.seller.pc.datacompass.item.indicators"


class AnalyticsError(RuntimeError):
    pass


class ItemAnalytics:
    def __init__(self, cookie: str = "", *, session=None, member_id: str = ""):
        # 可直接传 XianYuApis 实例中的 session，复用其登录态。
        self.session = session if session is not None else requests.Session()
        self.member_id = member_id
        if cookie:
            jar = SimpleCookie()
            jar.load(cookie)
            if not jar:
                raise AnalyticsError("Cookie 格式无效")
            for name, morsel in jar.items():
                self.session.cookies.set(name, morsel.value, domain=".goofish.com", path="/")

    def _request(self, api, payload):
        # 必须对实际发送的同一份 JSON 字符串签名。
        data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        req = requests.Request("POST", f"https://h5api.m.goofish.com/h5/{api}/1.0/")
        prepared = self.session.prepare_request(req)
        jar = SimpleCookie()
        jar.load(prepared.headers.get("Cookie", ""))
        token = jar.get("_m_h5_tk")
        if token is None or not token.value:
            raise AnalyticsError("缺少有效 _m_h5_tk，请先在官方工作台完成登录")
        t = str(int(time.time() * 1000))
        sign = hashlib.md5(f"{token.value.split('_')[0]}&{t}&34839810&{data}".encode()).hexdigest()
        params = {
            "jsv": "2.7.2", "appKey": "34839810", "t": t, "sign": sign,
            "v": "1.0", "type": "originaljson", "dataType": "json",
            "accountSite": "xianyu", "api": api, "sessionOption": "AutoLoginOnly",
        }
        headers = {
            "Accept": "application/json", "Referer": "https://seller.goofish.com/?site=COMMONPRO",
            "idle_site_biz_code": "COMMONPRO", "idle_user_group_member_id": self.member_id,
        }
        try:
            response = self.session.post(req.url, params=params, data={"data": data},
                                         headers=headers, timeout=25, allow_redirects=False)
            if response.is_redirect:
                raise AnalyticsError("接口发生跳转，请在官方工作台检查登录态")
            response.raise_for_status()
            result = response.json()
        except (requests.RequestException, ValueError):
            # 异常中的完整 URL 带签名，不直接输出。
            raise AnalyticsError("请求失败或响应非 JSON，请检查网络和官方工作台登录态") from None
        if not isinstance(result, dict):
            raise AnalyticsError("接口响应结构异常")
        ret = result.get("ret", [])
        if not isinstance(ret, list) or not any(str(x).split("::")[0] == "SUCCESS" for x in ret):
            codes = [str(x).split("::")[0] for x in ret] if isinstance(ret, list) else []
            safe = [x for x in codes if x.replace("_", "").isalnum()]
            raise AnalyticsError("接口未成功：" + ", ".join(safe) + "；请在官方工作台检查登录或验证提示")
        body = result.get("data", {})
        if not isinstance(body, dict) or body.get("code") != "success":
            raise AnalyticsError("接口业务状态未成功，请在官方工作台检查权限")
        return body

    def indicators(self):
        """动态列定义；字段可用性以账号返回为准。"""
        return self._request(INDICATORS_API, {})

    def item_page(self, *, date_type="recent1d", date_range="", keyword="", item_id="",
                  page=1, page_size=200, order_by="", order="", seller_id=None):
        if date_type not in {"recent1d", "recent7d", "recent30d", "customDate"}:
            raise ValueError("不支持的 date_type")
        if date_type == "customDate":
            try:
                start, end = date_range.split("|")
                if len(start) != 8 or len(end) != 8:
                    raise ValueError()
                if datetime.strptime(start, "%Y%m%d") > datetime.strptime(end, "%Y%m%d"):
                    raise ValueError()
            except ValueError:
                raise ValueError("date_range 应为 YYYYMMDD|YYYYMMDD，开始日期不能晚于结束日期") from None
        if page < 1 or not 1 <= page_size <= 200:
            raise ValueError("page 从 1 开始；page_size 取 1～200（20、200 已实测）")
        if order not in {"", "asc", "desc"} or bool(order_by) != bool(order):
            raise ValueError("order_by 和 order 应同时设置，order 为 asc/desc")
        payload = {
            "tabType": "all", "dateRange": date_range if date_type == "customDate" else "",
            "ms": "", "dateType": date_type, "categoryInfoStr": "[]",
            "itmName": keyword, "itmId": str(item_id), "isDpStk": "", "mktActId": "",
            "page": page, "pageSize": page_size,
        }
        if seller_id is not None:
            payload["selectedSellerId"] = str(seller_id)
        if order_by:
            payload.update(orderBy=order_by, order=order)
        body = self._request(API, payload)
        rows = body.get("data", {}).get("list")
        total = body.get("data", {}).get("total")
        if not isinstance(rows, list) or total is None:
            raise AnalyticsError("缺少 list/total，接口结构可能已变化")
        return body

    def collect(self, *, max_pages=100, interval=0.6, **filters):
        """顺序分页，保留原始字段及服务端实际日期。不是原子快照。"""
        if max_pages < 1 or interval < 0:
            raise ValueError("max_pages 必须为正数，interval 不能为负")
        rows, seen, pages = [], set(), []
        total, stop_reason = None, "max_pages"
        for page in range(1, max_pages + 1):
            body = self.item_page(page=page, **filters)
            current = body["data"]["list"]
            total = int(body["data"]["total"])
            pages.append({"page": page, "total": total, "extendInfo": body.get("extendInfo", {})})
            added = 0
            for row in current:
                key = str(row.get("itmId", ""))
                if not key:
                    raise AnalyticsError("商品缺少 itmId")
                if key not in seen:
                    rows.append(row)
                    seen.add(key)
                    added += 1
            if len(rows) >= total:
                stop_reason = "total_reached"
                break
            if not current or added == 0:
                stop_reason = "empty_or_repeated_page"
                break
            if page < max_pages:
                time.sleep(interval)
        return {
            "api": API, "generated_at": datetime.now(timezone.utc).isoformat(),
            "filters": filters, "total": total, "count": len(rows),
            "complete": len(rows) == total, "stop_reason": stop_reason,
            "pages": pages, "items": rows,
        }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cookie-file", type=Path, help="本机私有 Cookie 文件；也可使用 XIANYU_COOKIE 环境变量")
    p.add_argument("--date-type", default="recent1d", choices=["recent1d", "recent7d", "recent30d", "customDate"])
    p.add_argument("--date-range", default="")
    p.add_argument("--keyword", default="")
    p.add_argument("--item-id", default="")
    p.add_argument("--order-by", default="")
    p.add_argument("--order", default="", choices=["", "asc", "desc"])
    p.add_argument("--max-pages", type=int, default=100)
    p.add_argument("--page-size", type=int, default=200)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    cookie = args.cookie_file.read_text().strip() if args.cookie_file else os.environ.get("XIANYU_COOKIE", "")
    if not cookie:
        p.error("请通过 --cookie-file 或 XIANYU_COOKIE 提供本机登录态，不要粘贴到聊天中")
    try:
        data = ItemAnalytics(cookie).collect(date_type=args.date_type, date_range=args.date_range,
                    keyword=args.keyword, item_id=args.item_id, order_by=args.order_by,
                    order=args.order, max_pages=args.max_pages, page_size=args.page_size)
    except (AnalyticsError, ValueError) as error:
        p.exit(1, f"{error}\n")
    args.output.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已保存 {data['count']}/{data['total']} 条；complete={data['complete']}")
    if not data["complete"]:
        p.exit(2, "分页结果不完整，请检查 stop_reason 和 pages 元数据\n")


if __name__ == "__main__":
    main()
