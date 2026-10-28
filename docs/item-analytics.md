# 闲鱼小铺商品数据

对应专业工作台「数据 → 商品数据」页面 `/seller-data/commodity`。
仅查询登录账号有权查看的店铺数据，需要有效登录态和工作台访问权限。

## 复用现有登录 Session

```python
# xianyu 是已有的 XianyuApis 登录实例。
analytics = xianyu.get_item_analytics()
result = analytics.collect(date_type="recent7d")
if not result["complete"]:
    raise RuntimeError(f"结果不完整: {result['stop_reason']}")

for item in result["items"]:
    print(item["itmId"], item["itmName"], item["showPv"], item["ipv"])
```

也可以独立使用 `ItemAnalytics(session=xianyu.session)`。传入 Session 时保留其
Cookie、代理及其他配置；登录态刷新仍由调用者管理。

## 命令行

依赖项目已有的 `requests`，无需 Node.js 签名运行时。
Cookie 使用本机私有文件或 `XIANYU_COOKIE` 环境变量提供，不要提交到仓库。

```bash
python item_analytics.py --cookie-file /path/to/private-cookie.txt \
  --date-type recent7d --output /path/to/items.json

python item_analytics.py --cookie-file /path/to/private-cookie.txt \
  --date-type customDate --date-range '20260101|20260107' \
  --keyword 示例 --order-by showPv --order desc --output /path/to/items.json
```

`--item-id` 可按商品 ID 筛选。`--page-size` 默认 200，`--max-pages` 默认 100。
结果不完整时仍保存结果，但退出码为 2；请求或鉴权失败时退出码为 1。

## 接口与字段

列表：`mtop.alibaba.idle.seller.pc.datacompass.item.list`，版本 `1.0`。
动态列定义：`mtop.alibaba.idle.seller.pc.datacompass.item.indicators`，
通过 `analytics.indicators()` 获取。

请求使用 `https://h5api.m.goofish.com/h5/{api}/1.0/`，POST 表单 `data`。
签名沿用项目算法：

```text
MD5(_m_h5_tk 下划线前的 token + "&" + 毫秒时间戳 + "&34839810&" + data)
```

签名与发送使用同一份紧凑 JSON 字符串。工作台业务标识为 `COMMONPRO`；
成员身份可通过 `member_id` 设置，查询时可选 `seller_id` 指定工作台授权的卖家身份。

请求字段包括 `dateType`、`dateRange`、`itmName`、`itmId`、`page`、`pageSize`、
`orderBy` 和 `order`。排序方向为 `asc` / `desc`，字段以动态列定义为准。
本封装不覆盖严选工作台及月度统计分支。

| 字段 | 含义 |
| --- | --- |
| `itmId`, `itmName`, `itmPrice` | 商品 ID、名称、价格 |
| `showPv`, `showUv` | 商品曝光次数、曝光人数 |
| `ipv`, `ipvUv` | 商品浏览次数、浏览人数 |
| `chatUv` | 聊天人数 |
| `payOrdCnt`, `payByrCnt`, `payAmt` | 支付订单数、买家数、金额 |

原始列表位于 `response.data.data.list`，总数位于 `response.data.data.total`，
实际日期位于 `response.data.extendInfo.realDateRange`。
封装同时检查 MTOP `ret` 和业务 `data.code`，保留金额字符串、零值及 `"-"`。

`recent1d` 在实测中为昨日数据，勿当作今日实时数据。
`recent7d`、`recent30d`、`customDate` 的实际范围均以服务端返回为准。
自定义日期格式为 `YYYYMMDD|YYYYMMDD`。
不要累加各日 UV 作为区间去重人数。

## 分页限制与验证

实测小分页可能出现跨页重复，疑似同分商品排序不稳定。默认每页 200 条，
顺序查询间隔 0.6 秒，并按 `itmId` 去重。返回 `count`、`total`、`complete`、
`stop_reason` 及各页 `extendInfo`；检测到空页或整页重复会提前结束。
`complete=true` 表示去重后的数量等于最后一次返回的总数，不能保证原子快照。
跨页变化、总数变化或接口行为改变时，调用者需检查元数据。

已实测近 1/7/30 天、自定义日期、名称/ID 筛选、曝光降序，以及单页 200 条完整采集。
测试和示例使用虚构数据，不包含真实店铺数据或登录信息。
失效登录或验证提示不会被自动绕过，也不会盲目重试。

接口定位依据为工作台公开前端
[idle-seller-data 0.0.11](https://g.alicdn.com/idle-pc/idle-seller-data/0.0.11/js/main.js)
中的列表调用和商品页面请求参数。非公开 API 可能随平台更新而变化。

离线测试：

```bash
python -m unittest discover -s tests -v
```
