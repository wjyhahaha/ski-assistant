#!/usr/bin/env python3
"""
滑雪票价比价工具
用法: python scripts/ticket_comparator.py '<json>'
输入多个票源信息，输出排序后的比价表和购买建议

支持命令:
  compare  '<json>'   比价多张票（默认）
  search   '<json>'   生成搜索关键词列表，用于查找低价票
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
    resort = params.get("resort", "")
    date = params.get("date", "")
    base = params.get("base_price", 0)
    currency = params.get("currency", "CNY")
    symbol = "¥" if currency == "CNY" else currency + " "
    tickets = params.get("tickets", params.get("results", []))

    # 如果顶层没有 resort/date，尝试从票信息中提取
    if not resort and tickets:
        resort = tickets[0].get("resort", "未知雪场")
    if not date and tickets:
        date = tickets[0].get("date", "未知日期")
    if not base and tickets:
        # 尝试从 original_price 推断基准价
        originals = [t.get("original_price", 0) for t in tickets if t.get("original_price")]
        if originals:
            base = max(originals)

    resort = resort or "未知雪场"
    date = date or "未知日期"

    # Sort by price ascending
    tickets.sort(key=lambda t: t.get("price", 0))

    lines = []
    lines.append(f"🎿 {resort} 低价票比价结果（{date}）\n")
    lines.append(f"基准价：全天票 {symbol}{base}\n")
    lines.append("| 来源 | 票种 | 价格 | 折扣 | 可退改 | 可信度 |")
    lines.append("|------|------|------|------|--------|--------|")

    best = None
    best_value = None  # 性价比最高（平衡价格和可信度）
    for t in tickets:
        price = t.get("price", 0)
        source = t.get("source") or t.get("platform", "")
        ttype = t.get("type") or t.get("ticket_type", "")
        discount = f"{(1 - price / base) * 100:.0f}% off" if base > 0 else "-"
        refund = "✅" if t.get("refundable") else "❌"
        trust = t.get("trust", "未知")

        lines.append(
            f"| {source} | {ttype} "
            f"| {symbol}{price} | {discount} | {refund} | {trust} |"
        )

        # 最佳价格（可信度高/中）
        if best is None and trust in ("高", "中"):
            best = {**t, "_source": source, "_type": ttype}

        # 性价比最高（综合考虑价格和可信度）
        if best_value is None or (price < best_value.get("price", 999999) and trust in ("高", "中")):
            best_value = {**t, "_source": source, "_type": ttype, "_trust": trust}

    lines.append("")

    # 票价统计分析
    if tickets:
        prices = [t.get("price", 0) for t in tickets]
        avg_price = sum(prices) / len(prices)
        min_price = prices[0]
        max_price = prices[-1]
        lines.append(f"📊 **票价统计**")
        lines.append(f"  · 最低价：{symbol}{min_price}")
        lines.append(f"  · 最高价：{symbol}{max_price}")
        lines.append(f"  · 平均价：{symbol}{avg_price:.0f}")
        lines.append(f"  · 价差：{symbol}{max_price - min_price}")
        lines.append("")

    # Generate recommendation
    if best:
        saving = base - best["price"]
        if saving > 0:
            lines.append(
                f"💡 **推荐购买**：{best['_source']}的{best['_type']}，"
                f"{symbol}{best['price']}，较门市价节省 {symbol}{saving}。"
            )
        else:
            lines.append(
                f"💡 **推荐购买**：{best['_source']}的{best['_type']}，"
                f"{symbol}{best['price']}。"
            )
        if not best.get("refundable"):
            lines.append("⚠️ 注意：该票源不可退改，请确认行程后再购买。")
    else:
        lines.append("💡 建议通过雪场官网或正规 OTA 平台购票，确保可退改。")

    # 购票建议
    lines.append(f"\n📋 **购票建议**")
    lines.append("  1. 优先选择可退改的票源，避免行程变更损失")
    lines.append("  2. 二手票需谨慎核实真伪，建议选择有担保交易的平台")
    lines.append("  3. 早鸟票/季卡通常比单日票更划算，如计划多次前往")
    if best_value and best_value != best:
        lines.append(f"  4. 性价比之选：{best_value['_source']}（{symbol}{best_value['price']}，可信度{best_value['_trust']}）")

    return "\n".join(lines)


def generate_search_keywords(params: dict) -> str:
    """
    生成查找低价票的搜索关键词列表。
    参数: {"resort": "万龙", "date": "2026-01-15", "ticket_type": "全天票"}
    """
    resort = params.get("resort", "")
    date = params.get("date", "")
    ticket_type = params.get("ticket_type", "雪票")

    if not resort:
        return "⚠️ 请提供雪场名称。"

    # 从日期提取雪季信息
    season = ""
    if date:
        try:
            year = int(date.split("-")[0])
            if "01" <= date.split("-")[1] <= "03":
                season = f"{year-1}-{year}雪季"
            else:
                season = f"{year}-{year+1}雪季"
        except (ValueError, IndexError):
            pass

    keywords = []

    # 核心关键词
    if season:
        keywords.append(f"{resort} {season} 雪票")
    else:
        keywords.append(f"{resort} 雪票")

    # 低价票关键词
    keywords.extend([
        f"{resort} 残票",
        f"{resort} 低价票",
        f"{resort} 转让 雪票",
        f"{resort} 二手票",
    ])

    # 平台特定关键词
    platforms = [
        ("飞猪", f"{resort} 飞猪 雪票"),
        ("美团", f"{resort} 美团 雪票"),
        ("抖音", f"{resort} 抖音 团购"),
        ("闲鱼", f"{resort} 闲鱼 转让"),
        ("小红书", f"{resort} 小红书 攻略"),
    ]

    lines = [f"🔍 {resort} 低价票搜索任务\n"]
    lines.append("请按以下关键词依次搜索：\n")

    lines.append("### 1️⃣ 核心搜索")
    for kw in keywords[:3]:
        lines.append(f"  · 搜索：\"{kw}\"")

    lines.append("\n### 2️⃣ 平台搜索")
    for platform, kw in platforms:
        lines.append(f"  · {platform}：搜索 \"{kw}\"")

    lines.append("\n### 3️⃣ 社区/转让搜索")
    transfer_keywords = [
        f"{resort} 雪票 转让",
        f"{resort} 雪票 出售",
        f"{resort} 雪票 出",
    ]
    for kw in transfer_keywords:
        lines.append(f"  · 搜索：\"{kw}\"")

    lines.append(f"\n共 {len(keywords) + len(platforms) + len(transfer_keywords)} 个关键词")
    lines.append("\n搜索后，请使用 compare 命令传入找到的票价信息进行比价。")

    return "\n".join(lines)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]

    try:
        if cmd == "compare" or cmd == "ticket_comparator":
            params = json.loads(sys.argv[2]) if len(sys.argv) > 2 else json.load(sys.stdin)
            print(compare_tickets(params))
        elif cmd == "search":
            params = json.loads(sys.argv[2]) if len(sys.argv) > 2 else json.load(sys.stdin)
            print(generate_search_keywords(params))
        else:
            # 默认行为：直接传入 JSON 视为 compare
            params = json.loads(cmd)
            print(compare_tickets(params))
    except json.JSONDecodeError as e:
        print(f"❌ JSON 参数格式错误：{e}")
        print(f"💡 请使用有效的 JSON 字符串，例如：")
        print(f'   python scripts/ticket_comparator.py compare \'{{"resort":"万龙"}}\'')
        sys.exit(1)
    except Exception as e:
        print(f"❌ 执行出错：{type(e).__name__}: {e}")
        sys.exit(1)
