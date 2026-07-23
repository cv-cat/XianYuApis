import argparse
import json
from pathlib import Path

from goofish_apis import XianyuApis
from utils.goofish_utils import trans_cookies, generate_device_id


def main() -> int:
    parser = argparse.ArgumentParser(description="闲鱼商品发布脚本")
    parser.add_argument("--yes", action="store_true", help="确认执行真实发布")
    args = parser.parse_args()

    script_path = Path(__file__).resolve()
    config_path = script_path.with_name("publish_config.json")

    if not config_path.exists():
        print("未找到 publish_config.json，请先根据模板创建配置文件。")
        return 1

    config = json.loads(config_path.read_text(encoding="utf-8-sig"))
    cookies_str = config.get("cookies", "").strip()
    if not cookies_str:
        print("配置缺少 cookies 字段")
        return 1

    cookies = trans_cookies(cookies_str)
    if "unb" not in cookies:
        print("cookies 缺少 unb 字段，无法生成 device_id")
        return 1

    xianyu = XianyuApis(cookies, generate_device_id(cookies["unb"]))

    publish_cfg = config.get("publish", {})
    images_path = publish_cfg.get("images_path", [])
    goods_desc = publish_cfg.get("goods_desc", "")
    price = publish_cfg.get("price", None)
    delivery = publish_cfg.get("delivery", {})

    if not goods_desc:
        print("publish.goods_desc 不能为空")
        return 1
    if not images_path:
        print("publish.images_path 至少需要 1 张图片")
        return 1
    if not delivery:
        print("publish.delivery 不能为空")
        return 1

    preview = {
        "images_path": images_path,
        "goods_desc": goods_desc,
        "price": price,
        "delivery": delivery,
    }

    if not args.yes:
        print(
            "\n".join(
                [
                    "⚠️ 危险操作检测！",
                    "操作类型：发布商品",
                    "影响范围：会使用 publish_config.json 中的配置发布线上闲鱼商品",
                    "风险评估：发布成功后会产生真实线上商品，需要后续手工下架或删除",
                    "",
                    "发布配置预览：",
                    json.dumps(preview, ensure_ascii=False, indent=2),
                    "",
                    "如确认执行，请重新运行并附加 --yes",
                ]
            )
        )
        return 1

    res = xianyu.public(
        images_path=images_path,
        goods_desc=goods_desc,
        price=price,
        ds=delivery,
    )
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
