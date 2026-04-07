#!/usr/bin/env python3
"""
滑雪行程预算计算器（手动模式）
用法: python scripts/budget_calculator.py '<json>'

⚠️ 推荐使用 resort_recommender.py costs 命令（自动查询雪场数据库估算费用）。
本脚本适用于用户已知所有费用明细、需要手动汇总的场景。
"""

import json
import sys


def calculate_budget(params: dict) -> dict:
    """
    参数示例:
    {
        "people": 2,
        "days": 5,
        "ski_days": 4,
        "flight_per_person": 2500,
        "hotel_per_night": 400,
        "hotel_nights": 4,
        "lift_ticket_per_day": 550,
        "rental_per_day": 200,      # 0 = 自带装备
        "food_per_day": 150,
        "transport_local": 300,
        "insurance_per_person": 50,
        "extras_per_person": 100,
        "currency": "CNY"
    }
    """
    p = params
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
    if len(sys.argv) > 1:
        params = json.loads(sys.argv[1])
    else:
        params = json.load(sys.stdin)

    result = calculate_budget(params)
    print(format_budget(result))
    print("\n<!-- RAW JSON -->")
    print(json.dumps(result, ensure_ascii=False, indent=2))
