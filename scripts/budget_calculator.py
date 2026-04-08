#!/usr/bin/env python3
"""
滑雪行程预算计算器（手动模式）
用法: python scripts/budget_calculator.py '<json>'

⚠️ 推荐使用 resort_recommender.py costs 命令（自动查询雪场数据库估算费用）。
本脚本适用于用户已知所有费用明细、需要手动汇总的场景。
"""

import json
import os
import sys

# ─── 导入共享工具 ───
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SCRIPT_DIR)
from utils import load_resorts_db


def _auto_fill_from_db(params: dict) -> dict:
    """如果传了 resort 名称但缺少费用明细，自动从数据库填充默认值。"""
    resort_name = params.get("resort", "")
    if not resort_name:
        return params

    db = load_resorts_db()
    resort = db.get(resort_name)
    if not resort or not isinstance(resort, dict) or "lat" not in resort:
        return params

    days = params.get("days", 1)
    ski_days = params.get("ski_days", days)
    people = params.get("people", 1)

    # 雪票：取区间中值
    ticket_range = resort.get("ticket_range_cny", [0, 0])
    if "lift_ticket_per_day" not in params and ticket_range:
        params["lift_ticket_per_day"] = sum(ticket_range) / len(ticket_range)

    # 住宿：取区间低值
    hotel_range = resort.get("hotel_range_cny", [0, 0])
    if "hotel_per_night" not in params and hotel_range:
        params["hotel_per_night"] = hotel_range[0]

    # 交通：从 transport_ref 取均值
    transport = resort.get("transport_ref", {})
    if "flight_per_person" not in params and transport:
        cost_range = transport.get("cost_cny", [0, 0])
        if cost_range:
            params["flight_per_person"] = sum(cost_range) / len(cost_range)

    # 保险默认值
    if "insurance_per_person" not in params:
        params["insurance_per_person"] = 25

    return params


def calculate_budget(params: dict) -> dict:
    """
    支持两种输入模式：
    模式1（推荐 - 明细项）:
    {
        "people": 2, "days": 5, "ski_days": 4,
        "items": [
            {"name": "雪票", "unit_price": 500, "quantity": 3},
            {"name": "住宿", "unit_price": 400, "quantity": 4, "split": true},
            {"name": "高铁", "unit_price": 550, "quantity": 1},
            {"name": "装备租赁", "unit_price": 200, "quantity": 3}
        ]
    }
    模式2（flat 参数，自动填充）:
    {
        "people": 2, "days": 5, "ski_days": 4,
        "flight_per_person": 2500, "hotel_per_night": 400,
        "lift_ticket_per_day": 550, "rental_per_day": 200,
        "food_per_day": 150, "insurance_per_person": 50
    }
    """
    people = params.get("people", 1)
    days = params.get("days", 1)
    ski_days = params.get("ski_days", days)
    currency = params.get("currency", "CNY")
    symbol = "¥" if currency == "CNY" else currency + " "

    # 兼容嵌套 dict 格式的 items（如 {"transport": {...}, "hotel": {...}, "ticket": {...}}）
    # 支持两种输入位置：params["items"] 或直接在 params 顶层
    user_items = params.get("items")
    if user_items is None:
        # 检查 params 顶层是否有已知 key
        known_keys = {"transport", "hotel", "ticket", "ski_pass", "food", "meals", "rental", "insurance", "other"}
        if any(k in known_keys for k in params.keys()):
            user_items = {k: v for k, v in params.items() if k in known_keys}
    # 兼容嵌套 dict 格式的 items（如 {"transport": {...}, "hotel": {...}, "ticket": {...}}）
    if user_items and isinstance(user_items, dict):
        # 检测是否是嵌套的配置对象（transport/hotel/ticket 等）
        known_keys = {"transport", "hotel", "ticket", "ski_pass", "food", "meals", "rental", "insurance", "other"}
        if any(k in known_keys for k in user_items.keys()):
            # 转换为标准 items 列表格式
            converted_items = []
            for key, val in user_items.items():
                if not isinstance(val, dict):
                    continue
                name_map = {
                    "transport": "交通", "hotel": "住宿", "ticket": "雪票", "ski_pass": "雪票",
                    "food": "餐饮", "meals": "餐饮", "rental": "装备租赁", "insurance": "保险", "other": "其他"
                }
                item_name = name_map.get(key, key)
                # 支持多种字段
                cost = (val.get("cost_per_person", 0) or val.get("per_person", 0)
                        or val.get("price", 0) or val.get("total", 0)
                        or val.get("per_night", 0) or val.get("per_day", 0)
                        or val.get("per_day_per_person", 0) or val.get("cost", 0))
                if cost > 0:
                    converted_items.append({"name": item_name, "price": cost})
            if converted_items:
                user_items = converted_items
        elif all(isinstance(v, dict) for v in user_items.values()):
            # 旧的兼容逻辑：纯 dict 值列表
            user_items = list(user_items.values())
        else:
            user_items = None
    if user_items and isinstance(user_items, list) and len(user_items) > 0:
        # 模式1：用户提供了明细项，直接计算
        # 支持多种字段名：unit_price/price, quantity/days/nights/people（自动组合）
        output_items = []
        grand_total = 0
        for item in user_items:
            name = item.get("name", "未命名")
            unit_price = item.get("unit_price", 0) or item.get("price", 0)
            # 灵活计算数量：优先用 quantity，否则组合 days/nights × people
            quantity = item.get("quantity", 0)
            if not quantity:
                days_or_nights = item.get("days", 0) or item.get("nights", 0)
                item_people = item.get("people", 0)
                if days_or_nights and item_people:
                    quantity = days_or_nights * item_people
                elif days_or_nights:
                    quantity = days_or_nights
                elif item_people:
                    quantity = item_people
                else:
                    quantity = 1
            # 也支持直接给 total
            total = item.get("total", 0) or (unit_price * quantity)
            pp = total / people if people > 0 else total
            grand_total += total
            output_items.append({"name": name, "total": total, "per_person": pp})

        return {
            "summary": {
                "people": people, "days": days, "ski_days": ski_days,
                "grand_total": grand_total,
                "per_person": grand_total / people if people > 0 else 0,
                "currency": currency, "symbol": symbol,
            },
            "items": output_items,
        }

    # 模式2：flat 参数，支持数据库自动填充
    p = _auto_fill_from_db(dict(params))
    people = p.get("people", 1)
    days = p.get("days", 1)
    ski_days = p.get("ski_days", days)

    flight_total = p.get("flight_per_person", 0) * people
    hotel_total = p.get("hotel_per_night", 0) * p.get("hotel_nights", days - 1)
    ticket_total = p.get("lift_ticket_per_day", 0) * ski_days * people
    rental_total = p.get("rental_per_day", 0) * ski_days * people
    food_total = p.get("food_per_day", 150) * days * people
    transport_total = p.get("transport_local", 0) * people
    insurance_total = p.get("insurance_per_person", 0) * people
    extras_total = p.get("extras_per_person", 0) * people

    grand_total = (flight_total + hotel_total + ticket_total + rental_total
                   + food_total + transport_total + insurance_total + extras_total)
    per_person = grand_total / people if people > 0 else 0

    currency = p.get("currency", "CNY")
    symbol = "¥" if currency == "CNY" else currency + " "

    items = [
        ("交通（往返）", flight_total, flight_total / people),
        ("住宿", hotel_total, hotel_total / people),
        ("雪票", ticket_total, ticket_total / people),
        ("装备租赁", rental_total, rental_total / people),
        ("餐饮", food_total, food_total / people),
        ("当地交通", transport_total, transport_total / people),
        ("保险", insurance_total, insurance_total / people),
        ("其他", extras_total, extras_total / people),
    ]

    return {
        "summary": {
            "people": people,
            "days": days,
            "ski_days": ski_days,
            "grand_total": grand_total,
            "per_person": per_person,
            "currency": currency,
            "symbol": symbol,
        },
        "items": [
            {"name": name, "total": total, "per_person": pp}
            for name, total, pp in items
        ],
    }


def format_budget(result: dict) -> str:
    s = result["summary"]
    lines = []
    lines.append(f"## 预算规划（{s['people']}人 {s['days']}天，滑雪{s['ski_days']}天）\n")
    lines.append(f"| 项目 | 总费用 | 人均 | 备注 |")
    lines.append(f"|------|--------|------|------|")

    for item in result["items"]:
        if item["total"] > 0:
            lines.append(
                f"| {item['name']} | {s['symbol']}{item['total']:.0f} "
                f"| {s['symbol']}{item['per_person']:.0f} | |"
            )

    lines.append(
        f"| **合计** | **{s['symbol']}{s['grand_total']:.0f}** "
        f"| **{s['symbol']}{s['per_person']:.0f}** | |"
    )
    return "\n".join(lines)


if __name__ == "__main__":
    try:
        if len(sys.argv) > 1:
            params = json.loads(sys.argv[1])
        else:
            params = json.load(sys.stdin)

        result = calculate_budget(params)
        print(format_budget(result))
        print("\n<!-- RAW JSON -->")
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except json.JSONDecodeError as e:
        print(f"❌ JSON 参数格式错误：{e}")
        print(f"💡 请使用有效的 JSON 字符串，例如：")
        print(f'   echo \'{{"people":2,"days":4}}\' | python scripts/budget_calculator.py')
        sys.exit(1)
    except Exception as e:
        print(f"❌ 执行出错：{type(e).__name__}: {e}")
        sys.exit(1)
