# 🐟 XianYuApis — “闲鱼”第三方API集成库，AI客服智能体底座 

[![Python](https://img.shields.io/badge/python-3.9%2B-blue)](https://www.python.org/)
[![Node.js](https://img.shields.io/badge/node.js-18%2B-green)](https://nodejs.org/)
[![License](https://img.shields.io/badge/license-MIT-orange)](LICENSE)

> **在 AI 大模型爆发的时代，每一个闲鱼卖家都值得拥有一个 7×24 小时不下线的智能客服。**
> 本项目封装了闲鱼平台完整的消息通信能力，为开发者构建 AI 客服智能体提供可靠、稳定的底层 API 支撑。

**⚠️ 严禁用于发布不良信息、违法内容！如有侵权请联系作者删除。**

---

## 为什么需要这个项目？

```
用户私信 ──► [XianYuApis] ──► 你的 AI Agent（LLM / RAG / 规则引擎）──► 自动回复
                ▲                                                          │
                └──────────────── 发送消息 / 图片 ◄────────────────────────┘
```

闲鱼官方没有开放 IM 消息接口。想要接入 GPT、Claude、本地大模型来做智能客服，首先需要能**稳定收发消息**。XianYuApis 解决的正是这个前置问题：

- 逆向还原了闲鱼 WebSocket 私信协议（sign 签名 + base64 + Protobuf）
- 封装全部 HTTP 接口（sign 参数已解密）
- 提供统一的消息收发抽象层，开发者只需关注业务逻辑

**你负责接 AI 大脑，我们负责打通闲鱼的神经。**

---

## 已实现功能

| 模块 | 功能 | 状态 |
|------|------|------|
| HTTP API | 闲鱼所有 HTTP 接口（sign 签名已解密） | ✅ |
| WebSocket | 私信实时收发（sign + base64 + Protobuf 协议） | ✅ |
| 消息类型 | 文字、图片消息 | ✅ |
| 会话管理 | 获取全部历史聊天记录 | ✅ |
| 主动发送 | 主动向指定用户发消息 | ✅ |
| Token 维持 | 自动刷新登录态，常驻进程不掉线 | ✅ |
| 获取聊天记录 | 获取与指定用户的历史消息记录 | ✅ |
| 商品信息 | 获取商品详情 | ✅ |
| 媒体上传 | 上传图片并发送 | ✅ |

---

## 成品案例 在本项目基础上继续构建的Agent项目

- [XianyuAutoAgent](https://github.com/shaxiu/XianyuAutoAgent) — 基于本项目构建的闲鱼 AI 全自动客服智能体
- [xianyu-auto-reply](https://github.com/zhinianboke/xianyu-auto-reply) -  基于本项目构建的闲鱼自动回复系统
- [xianyu-auto-reply-fix](https://github.com/GuDong2003/xianyu-auto-reply-fix) -  基于本项目构建的闲鱼闲鱼管理系统
- [xianyu-auto-reply](https://github.com/zhinianboke-new/xianyu-auto-reply) -  基于本项目构建的闲鱼 AI 全自动客服智能体
- [xianyu-auto-reply](https://github.com/HJYHJYHJY/xianyu-auto-reply) -  基于本项目构建的闲鱼闲鱼自动回复系统
- [xianyu-super-butler](https://github.com/23Star/xianyu-super-butler) -  基于本项目构建的闲鱼闲鱼超级管家
- [XianyuAutoAgent](https://github.com/qOeOp/XianyuAutoAgent) -  基于本项目构建的闲鱼智能闲鱼客服机器人系统



> 欢迎提交你基于本项目构建的 AI 应用，PR 随时欢迎！

---

## 快速开始

### 环境要求

- Python 3.9+
- Node.js 18+（用于执行签名算法 JS）

### 安装依赖

```bash
pip install -r requirements.txt
```

### 配置 Cookie

登录 [goofish.com](https://www.goofish.com) 后，从浏览器开发者工具中复制完整 Cookie 字符串，填入代码对应位置：

```python
# goofish_live.py 底部
cookies_str = r'your_cookie_string_here'
```

> Cookie 必须是**登录后的状态**，否则无法获取消息。


### 直接运行

```bash
python goofish_live.py
```

---

## 项目结构

```
XianYuApis/
├── goofish_live.py      # 主入口：WebSocket 消息监听 & 回复逻辑（在此接入 AI）
├── goofish_apis.py      # HTTP API 封装（登录、刷新 Token、商品详情、上传媒体）
├── message/
│   ├── types.py         # 消息类型定义（TextContent / ImageContent / AudioContent）
├── utils/
│   └── goofish_utils.py # 工具函数（sign 签名、Cookie 处理、消息解密）
├── static/
│   └── goofish_js_*.js  # 逆向 JS（sign 签名核心算法）
├── requirements.txt
└── Dockerfile
```

---

## 接入 AI 智能体

在 `goofish_live.py` 的 `handle_message` 方法中替换回复逻辑即可：

```python
async def handle_message(self, message, websocket):
    # ... 解析 send_user_id, cid, send_message ...

    # 原始 echo 回复（示例）
    # reply = f'{send_user_name} 说了: {send_message}'

    # 接入 AI 大模型（示例）
    reply = await your_ai_agent(send_message)          # GPT / Claude / Qwen / 本地模型

    await self.send_msg(websocket, cid, send_user_id, make_text(reply))
```

---

## 注意事项

- `goofish_live.py` 是消息收发主入口，所有 AI 回复逻辑在此扩展
- `goofish_apis.py` 包含 HTTP 接口模板，可按需添加其他接口

---

## 额外说明

1. 感谢 Star ⭐ 和 Follow，项目会持续更新
2. 作者联系方式在主页，有问题随时联系
3. 欢迎 PR 和 Issue，也欢迎关注作者其他项目
4. 如果此项目对您有帮助，欢迎请作者喝一杯奶茶 ~~

<div align="center">
  <img src="https://github.com/cv-cat/Spider_XHS/blob/master/author/wx_pay.png" width="380px" alt="微信赞赏码">
  <img src="https://github.com/cv-cat/Spider_XHS/blob/master/author/zfb_pay.jpg" width="380px" alt="支付宝收款码">
</div>

---

## Star 趋势

<a href="https://www.star-history.com/#cv-cat/XianYuApis&Date">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=cv-cat/XianYuApis&type=Date&theme=dark" />
    <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=cv-cat/XianYuApis&type=Date" />
    <img alt="Star History Chart" src="https://api.star-history.com/svg?repos=cv-cat/XianYuApis&type=Date" />
  </picture>
</a>


## 🍔 交流群
如果你对爬虫和ai agent感兴趣，请加作者主页wx通过邀请加入群聊

ps: 请加群8，人满或者过期 issue | wx 提醒

![group7](https://github.com/cv-cat/Spider_XHS/blob/master/author/group8.jpg)


