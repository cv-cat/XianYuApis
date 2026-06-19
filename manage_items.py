import argparse
import json
from pathlib import Path

from goofish_apis import XianyuApis
from utils.goofish_utils import trans_cookies, generate_device_id


def load_client() -> XianyuApis:
    script_path = Path(__file__).resolve()
    config_path = script_path.with_name("publish_config.json")
    if not config_path.exists():
        raise SystemExit("未找到 publish_config.json，请先补全配置。")

    config = json.loads(config_path.read_text(encoding="utf-8-sig"))
    cookies_str = config.get("cookies", "").strip()
    if not cookies_str:
        raise SystemExit("配置缺少 cookies 字段。")

    cookies = trans_cookies(cookies_str)
    if "unb" not in cookies:
        raise SystemExit("cookies 缺少 unb 字段，无法生成 device_id。")

    return XianyuApis(cookies, generate_device_id(cookies["unb"]))


def find_first_item_list(payload):
    if isinstance(payload, dict):
        for key, value in payload.items():
            if isinstance(value, list) and value and all(isinstance(item, dict) for item in value):
                lowered = key.lower()
                if "item" in lowered or "list" in lowered:
                    return value
            nested = find_first_item_list(value)
            if nested:
                return nested
    elif isinstance(payload, list):
        for value in payload:
            nested = find_first_item_list(value)
            if nested:
                return nested
    return []


def extract_summary(payload):
    summary = {}
    if not isinstance(payload, dict):
        return summary

    data = payload.get("data", payload)
    for key in ("totalCount", "totalNum", "count", "itemCount"):
        if isinstance(data, dict) and key in data and data[key]:
            summary["total"] = data[key]
            break

    if isinstance(data, dict):
        for key in ("groupInfos", "groupInfoList", "itemGroupList", "tabList"):
            group_list = data.get(key)
            if isinstance(group_list, list):
                summary["groups"] = group_list
                break

    if "total" not in summary and summary.get("groups"):
        for group in summary["groups"]:
            if group.get("groupName") == "综合":
                summary["total"] = group.get("itemNumber")
                break

    return summary


def print_item_preview(payload):
    items = find_first_item_list(payload.get("data", payload))
    if not items:
        return

    print("商品预览:")
    for item in items[:10]:
        item_data = item.get("cardData", item)
        detail_params = item_data.get("detailParams", {})
        price_info = item_data.get("priceInfo", {})
        item_id = (
            item_data.get("itemId")
            or item_data.get("id")
            or item_data.get("item_id")
            or detail_params.get("itemId")
        )
        title = (
            item_data.get("title")
            or item_data.get("itemTitle")
            or item_data.get("name")
            or item_data.get("itemName")
            or item_data.get("idleTitle")
            or detail_params.get("title")
        )
        price = (
            item_data.get("price")
            or item_data.get("itemPrice")
            or price_info.get("price")
            or detail_params.get("soldPrice")
        )
        print(f"- itemId={item_id} title={title} price={price}")


def confirm_action(action: str, item_id: str, confirmed: bool):
    if confirmed:
        return
    raise SystemExit(
        "\n".join(
            [
                "⚠️ 危险操作检测！",
                f"操作类型：{action}",
                f"影响范围：itemId={item_id}",
                "风险评估：会对线上闲鱼商品执行真实变更",
                "",
                "如确认执行，请重新运行并附加 --yes",
            ]
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="闲鱼商品管理脚本")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="获取我发布的商品列表")
    list_parser.add_argument("--page-number", type=int, default=1)
    list_parser.add_argument("--page-size", type=int, default=20)
    list_parser.add_argument("--no-group-info", action="store_true")

    summary_parser = subparsers.add_parser("summary", help="获取当前商品数量摘要")
    summary_parser.add_argument("--page-size", type=int, default=20)

    down_shelf_parser = subparsers.add_parser("down-shelf", help="下架指定商品")
    down_shelf_parser.add_argument("--item-id", required=True)
    down_shelf_parser.add_argument("--yes", action="store_true")

    delete_parser = subparsers.add_parser("delete", help="删除指定商品")
    delete_parser.add_argument("--item-id", required=True)
    delete_parser.add_argument("--yes", action="store_true")

    args = parser.parse_args()
    client = load_client()

    if args.command == "list":
        result = client.list_my_items(
            page_number=args.page_number,
            page_size=args.page_size,
            need_group_info=not args.no_group_info,
        )
        print_item_preview(result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.command == "summary":
        result = client.list_my_items(page_number=1, page_size=args.page_size, need_group_info=True)
        summary = extract_summary(result)
        groups = []
        for group in summary.get("groups", []):
            groups.append(
                {
                    "groupName": group.get("groupName"),
                    "itemNumber": group.get("itemNumber"),
                    "groupId": group.get("groupId"),
                }
            )
        print(json.dumps({"total": summary.get("total", 0), "groups": groups}, ensure_ascii=False, indent=2))
        return 0

    if args.command == "down-shelf":
        confirm_action("下架商品", args.item_id, args.yes)
        result = client.down_shelf_item(args.item_id)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.command == "delete":
        confirm_action("删除商品", args.item_id, args.yes)
        result = client.delete_item(args.item_id)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    raise SystemExit(f"不支持的命令: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())