#!/usr/bin/env python3
"""
滑雪票价比价工具
用法: python scripts/ticket_comparator.py '<json>'
输入多个票源信息，输出排序后的比价表和购买建议
"""

import json
import sys


def compare_tickets(params: dict) -> str:
    """
    参数示例:
    {
        "resort": "万龙",
        "date": "2026-01-15",
        "base_price": 600,
        "base_half_day": 420,
        "currency": "CNY",
        "tickets": [
            {"source": "雪场官网", "type": "全天票", "price": 600, "refundable": true, "trust": "高"},
            {"source": "飞猪", "type": "全天票", "price": 520, "refundable": true, "trust": "高"},
            {"source": "闲鱼转让", "type": "全天票", "price": 380, "refundable": false, "trust": "中"},
            {"source": "小红书", "type": "全天票", "price": 350, "refundable": false, "trust": "低"}
        ]
    }
    """
    resort = params.get("resort", "未知雪场")
    date = params.get("date", "未知日期")
    base = params.get("base_price", 0)
    currency = params.get("currency", "CNY")
    symbol = "¥" if currency == "CNY" else currency + " "
    tickets = params.get("tickets", [])

    # Sort by price ascending
    tickets.sort(key=lambda t: t.get("price", 0))

    lines = []
    lines.append(f"🎿 {resort} 低价票比价结果（{date}）\n")
    lines.append(f"基准价：全天票 {symbol}{base}\n")
    lines.append("| 来源 | 票种 | 价格 | 折扣 | 可退改 | 可信度 |")
    lines.append("|------|------|------|------|--------|--------|")

    best = None
    for t in tickets:
        price = t.get("price", 0)
        discount = f"{(1 - price / base) * 100:.0f}% off" if base > 0 else "-"
        refund = "✅" if t.get("refundable") else "❌"
        trust = t.get("trust", "未知")

        lines.append(
            f"| {t.get('source', '')} | {t.get('type', '')} "
            f"| {symbol}{price} | {discount} | {refund} | {trust} |"
        )

        if best is None and trust in ("高", "中"):
            best = t

    lines.append("")

    # Generate recommendation
    if best:
        saving = base - best["price"]
        lines.append(
            f"💡 推荐：{best['source']}的{best['type']}，"
            f"{symbol}{best['price']}，较门市价节省 {symbol}{saving}。"
        )
        if not best.get("refundable"):
            lines.append("⚠️ 注意：该票源不可退改，请确认行程后再购买。")
    else:
        lines.append("💡 建议通过雪场官网或正规 OTA 平台购票，确保可退改。")

    return "\n".join(lines)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        params = json.loads(sys.argv[1])
    else:
        params = json.load(sys.stdin)

    print(compare_tickets(params))
