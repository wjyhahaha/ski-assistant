#!/usr/bin/env python3
"""
早鸟票/住滑套餐预售监听工具
用法: python scripts/presale_monitor.py <command> [args]

命令:
  watch         '<json>'    添加/更新监听项
  list                      列出所有监听项
  check                     检查所有监听项的预售状态变化，输出通知内容
  check-all                 生成搜索关键词列表，供 Agent 批量搜索（无需外部定时任务）
  remove        '<json>'    移除监听项
  status                    输出当前监听状态摘要
  record-price  '<json>'    🆕 记录价格数据（用于历史对比）
  price-trend   '<json>'    🆕 查询价格趋势和历史对比
  buying-advice '<json>'    🆕 购买时机建议

监听数据存储：通过 utils.py 统一管理，默认 ~/.ski-assistant/watchlist.json
价格历史存储：~/.ski-assistant/price_history.json

工作流程（手动模式，无需外部定时任务）：
1. 运行 check-all 获取所有待检查雪场的搜索关键词
2. Agent 用 WebSearch 批量搜索
3. 将搜索结果传入 check 命令，自动更新状态并生成通知
"""

import json
import os
import sys
from datetime import datetime, timedelta
from typing import List, Dict, Optional

# ─── 导入共享工具 ───
from utils import WATCHLIST_PATH, DATA_DIR, CST, ensure_dir, load_json, save_json, track_usage

# 价格历史存储路径
_PRICE_HISTORY_PATH = os.path.join(DATA_DIR, "price_history.json")


def _load_watchlist() -> dict:
    data = load_json(WATCHLIST_PATH, {"resorts": [], "last_check": None})
    # 结构校验：确保必须字段存在（防止空文件或字段缺失）
    if "resorts" not in data or not isinstance(data["resorts"], list):
        data["resorts"] = []
    if "last_check" not in data:
        data["last_check"] = None
    return data


def _save_watchlist(data: dict):
    save_json(WATCHLIST_PATH, data)


def watch(params: dict) -> str:
    """
    添加或更新监听项。
    支持两种格式:
    1. 批量: {"resorts": [{"name": "万龙滑雪场", "keywords": [...], ...}]}
    2. 单个: {"resort": "万龙滑雪场", "product": "早鸟季卡", "keywords": [...]}
    """
    # 兼容扁平格式：自动转为 resorts 数组
    if "resort" in params and "resorts" not in params:
        name = params["resort"].strip()
        if not name:
            return "⚠️ 请提供雪场名称。示例：watch '{\"resort\": \"万龙滑雪场\", \"product\": \"早鸟季卡\"}'"
        product = params.get("product", "")
        flat_entry = {
            "name": f"{name}" if not product else f"{name}",
            "keywords": params.get("keywords", [f"{name} {product}" if product else f"{name} 早鸟票", f"{name} 预售"]),
            "sources": params.get("sources", ["雪场官网", "微信公众号", "飞猪"]),
        }
        if "notify_channels" in params:
            flat_entry["notify_channels"] = params["notify_channels"]
        params = {"resorts": [flat_entry]}

    wl = _load_watchlist()
    existing_names = {r["name"] for r in wl["resorts"]}

    added = []
    updated = []
    for resort in params.get("resorts", []):
        name = resort.get("name", "")
        if not name:
            continue

        entry = {
            "name": name,
            "keywords": resort.get("keywords", [f"{name} 早鸟票", f"{name} 预售"]),
            "sources": resort.get("sources", ["雪场官网", "微信公众号", "飞猪"]),
            "notify_channels": resort.get("notify_channels", ["im", "console"]),
            "added_at": datetime.now(CST).isoformat(),
            "last_status": "未开始",
            "last_found": None,
            "history": [],
        }

        if name in existing_names:
            wl["resorts"] = [
                {**r, **{k: v for k, v in entry.items() if k not in ("added_at", "last_status", "last_found", "history")}}
                if r["name"] == name else r
                for r in wl["resorts"]
            ]
            updated.append(name)
        else:
            wl["resorts"].append(entry)
            added.append(name)

    _save_watchlist(wl)

    lines = ["📡 预售监听已更新\n"]
    if added:
        lines.append(f"新增监听：{', '.join(added)}")
    if updated:
        lines.append(f"已更新：{', '.join(updated)}")
    lines.append(f"\n当前共监听 {len(wl['resorts'])} 个雪场")
    return "\n".join(lines)


def list_watchlist() -> str:
    wl = _load_watchlist()
    if not wl["resorts"]:
        return "📡 当前没有监听任何雪场。使用 watch 命令添加。"

    lines = [f"📡 预售监听列表（共 {len(wl['resorts'])} 个）\n"]
    lines.append("| 雪场 | 监听关键词 | 当前状态 | 上次检查发现 | 通知渠道 |")
    lines.append("|------|----------|---------|------------|---------|")

    for r in wl["resorts"]:
        keywords = "、".join(r.get("keywords", [])[:2])
        if len(r.get("keywords", [])) > 2:
            keywords += " 等"
        status = r.get("last_status", "未开始")
        last_found = r.get("last_found", "无")
        channels = "、".join(r.get("notify_channels", []))
        lines.append(f"| {r['name']} | {keywords} | {status} | {last_found or '无'} | {channels} |")

    if wl.get("last_check"):
        lines.append(f"\n上次全量检查：{wl['last_check']}")

    return "\n".join(lines)


def check(search_results: dict) -> str:
    """
    处理搜索结果，对比状态变化，输出需要通知的内容。

    参数示例（由 AI agent 调用 WebSearch 后组装）:
    {
        "results": [
            {
                "resort": "万龙滑雪场",
                "found_presale": true,
                "presale_type": "早鸟票",
                "details": "2026-27雪季早鸟票已开售，全季卡 ¥4,999（原价 ¥6,800）",
                "source": "微信公众号",
                "url": "https://mp.weixin.qq.com/...",
                "price_info": "全季卡 ¥4,999 | 次卡10次 ¥3,500",
                "deadline": "2026-06-30"
            },
            {
                "resort": "北大湖滑雪场",
                "found_presale": false,
                "details": "暂未发现预售信息"
            }
        ]
    }
    """
    wl = _load_watchlist()
    now = datetime.now(CST).isoformat()
    wl["last_check"] = now

    # 输入格式校验
    if "results" not in search_results or not isinstance(search_results.get("results"), list):
        return (
            "⚠️ 输入格式错误，缺少 `results` 数组。\n"
            "正确格式示例：\n"
            '  check \'{"results":[{"resort":"万龙滑雪场","found_presale":true,"details":"..."}]}\''
        )

    notifications = []
    resort_map = {r["name"]: r for r in wl["resorts"]}

    for result in search_results.get("results", []):
        name = result.get("resort", "")
        if name not in resort_map:
            continue

        resort = resort_map[name]
        old_status = resort.get("last_status", "未开始")
        found = result.get("found_presale", False)

        if found:
            new_status = "已开售"
            if old_status != "已开售":
                # Status changed - need notification
                notif = {
                    "resort": name,
                    "type": "presale_started",
                    "presale_type": result.get("presale_type", "早鸟票/套餐"),
                    "details": result.get("details", ""),
                    "source": result.get("source", ""),
                    "url": result.get("url", ""),
                    "price_info": result.get("price_info", ""),
                    "deadline": result.get("deadline", ""),
                    "channels": resort.get("notify_channels", ["im", "console"]),
                }
                notifications.append(notif)

                resort["history"].append({
                    "time": now,
                    "event": f"预售开始: {result.get('presale_type', '')}",
                    "details": result.get("details", ""),
                })

            resort["last_status"] = new_status
            resort["last_found"] = now
        else:
            if old_status == "已开售":
                resort["last_status"] = "已开售"
            # else keep as-is

    _save_watchlist(wl)

    if not notifications:
        return f"✅ 检查完成（{now}）：所有监听项无变化。"

    lines = ["🔔 预售监听通知\n"]
    for n in notifications:
        lines.append(f"### 🎿 {n['resort']} - {n['presale_type']}已开售！\n")
        if n["details"]:
            lines.append(f"**详情**：{n['details']}")
        if n["price_info"]:
            lines.append(f"**价格**：{n['price_info']}")
        if n["deadline"]:
            lines.append(f"**截止日期**：{n['deadline']}")
        if n["source"]:
            lines.append(f"**来源**：{n['source']}")
        if n["url"]:
            lines.append(f"**链接**：{n['url']}")
        lines.append(f"**通知渠道**：{', '.join(n['channels'])}")
        lines.append("")

    # JSON output for programmatic use
    lines.append("<!-- NOTIFICATIONS_JSON -->")
    lines.append(json.dumps(notifications, ensure_ascii=False, indent=2))

    return "\n".join(lines)


def remove(params: dict) -> str:
    """
    移除监听项。
    支持两种格式:
    1. 批量: {"resorts": ["万龙滑雪场"]}
    2. 单个: {"resort": "万龙滑雪场"} 或 {"resort": "万龙滑雪场", "product": "早鸟季卡"}
    """
    # 兼容扁平格式
    if "resort" in params and "resorts" not in params:
        params = {"resorts": [params["resort"]]}

    wl = _load_watchlist()
    to_remove = set(params.get("resorts", []))
    before = len(wl["resorts"])
    wl["resorts"] = [r for r in wl["resorts"] if r["name"] not in to_remove]
    after = len(wl["resorts"])
    _save_watchlist(wl)

    removed = before - after
    if removed > 0:
        return f"✅ 已移除 {removed} 个监听项，当前剩余 {after} 个。"
    return "⚠️ 未找到匹配的监听项。"


def status() -> str:
    wl = _load_watchlist()
    if not wl["resorts"]:
        return "📡 当前没有监听任何雪场。"

    total = len(wl["resorts"])
    active = sum(1 for r in wl["resorts"] if r.get("last_status") == "已开售")
    pending = total - active

    lines = [f"📡 监听状态摘要\n"]
    lines.append(f"总监听数：{total} | 已开售：{active} | 等待中：{pending}")
    if wl.get("last_check"):
        lines.append(f"上次检查：{wl['last_check']}")

    if active > 0:
        lines.append("\n已开售的雪场：")
        for r in wl["resorts"]:
            if r.get("last_status") == "已开售":
                lines.append(f"  - {r['name']}（发现于 {r.get('last_found', '未知')}）")

    return "\n".join(lines)


def _load_price_history() -> dict:
    """加载价格历史数据"""
    return load_json(_PRICE_HISTORY_PATH, {"records": [], "meta": {"version": "1.0"}})


def _save_price_history(data: dict):
    """保存价格历史数据"""
    save_json(_PRICE_HISTORY_PATH, data)


def record_price(params: dict) -> str:
    """
    记录价格数据，用于历史对比。
    
    参数:
    {
        "resort": "万龙滑雪场",
        "product": "早鸟季卡",
        "price": 4999,
        "original_price": 6800,  // 原价（可选）
        "source": "微信公众号",
        "date": "2026-04-01"     // 可选，默认今天
    }
    """
    resort = params.get("resort", "").strip()
    product = params.get("product", "").strip()
    price = params.get("price", 0)
    
    if not resort or not product or price <= 0:
        return "⚠️ 请提供有效的雪场名称、产品名称和价格。"
    
    history = _load_price_history()
    
    record = {
        "id": f"{resort}_{product}_{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "resort": resort,
        "product": product,
        "price": price,
        "original_price": params.get("original_price", 0),
        "source": params.get("source", "未知"),
        "date": params.get("date", datetime.now().strftime("%Y-%m-%d")),
        "recorded_at": datetime.now(CST).isoformat(),
    }
    
    history["records"].append(record)
    
    # 只保留最近 500 条记录
    if len(history["records"]) > 500:
        history["records"] = history["records"][-500:]
    
    _save_price_history(history)
    
    return f"✅ 已记录价格：{resort} {product} = ¥{price}（{record['date']}）"


def price_trend(params: dict) -> str:
    """
    查询某雪场/产品的价格趋势和历史对比。
    
    参数:
    {
        "resort": "万龙滑雪场",
        "product": "早鸟季卡"  // 可选，不传则显示该雪场所有产品
    }
    """
    resort = params.get("resort", "").strip()
    product = params.get("product", "").strip()
    
    if not resort:
        return "⚠️ 请提供雪场名称。"
    
    history = _load_price_history()
    records = history.get("records", [])
    
    # 筛选记录
    filtered = [r for r in records if r["resort"] == resort]
    if product:
        filtered = [r for r in filtered if r["product"] == product]
    
    if not filtered:
        return f"📊 {resort} 暂无价格历史记录。使用 record-price 添加记录。"
    
    # 按产品分组
    products = {}
    for r in filtered:
        p = r["product"]
        if p not in products:
            products[p] = []
        products[p].append(r)
    
    lines = [f"📊 {resort} 价格趋势分析\n"]
    
    for p_name, p_records in products.items():
        # 按日期排序
        p_records.sort(key=lambda x: x["date"])
        
        prices = [r["price"] for r in p_records]
        min_price = min(prices)
        max_price = max(prices)
        avg_price = sum(prices) / len(prices)
        latest = p_records[-1]
        
        lines.append(f"\n### {p_name}")
        lines.append(f"| 统计项 | 数值 |")
        lines.append(f"|--------|------|")
        lines.append(f"| 历史最低 | ¥{min_price:.0f} |")
        lines.append(f"| 历史最高 | ¥{max_price:.0f} |")
        lines.append(f"| 历史平均 | ¥{avg_price:.0f} |")
        lines.append(f"| 当前/最新 | ¥{latest['price']:.0f} |")
        lines.append(f"| 数据点数 | {len(prices)} |")
        
        # 与历史最低对比
        if latest["price"] <= min_price * 1.05:
            lines.append(f"\n💚 **当前价格接近历史最低，建议购买**")
        elif latest["price"] >= max_price * 0.95:
            lines.append(f"\n💛 **当前价格接近历史最高，可观望或等待促销**")
        else:
            ratio = (latest["price"] - min_price) / (max_price - min_price) if max_price > min_price else 0
            if ratio < 0.3:
                lines.append(f"\n💚 **当前价格处于低位（低于历史区间30%）**")
            elif ratio > 0.7:
                lines.append(f"\n💛 **当前价格处于高位（高于历史区间70%）**")
            else:
                lines.append(f"\n💙 **当前价格处于中等水平**")
        
        # 显示最近 5 条记录
        lines.append(f"\n最近记录：")
        for r in p_records[-5:]:
            marker = " ← 最新" if r == latest else ""
            lines.append(f"  - {r['date']}: ¥{r['price']}{marker}")
    
    return "\n".join(lines)


def buying_advice(params: dict) -> str:
    """
    基于当前日期和历史数据，给出购买时机建议。
    
    参数:
    {
        "resort": "万龙滑雪场",
        "product": "早鸟季卡"  // 可选
    }
    """
    resort = params.get("resort", "").strip()
    product = params.get("product", "").strip()
    
    if not resort:
        return "⚠️ 请提供雪场名称。"
    
    now = datetime.now(CST)
    month = now.month
    
    lines = [f"💡 {resort} 购买时机建议\n"]
    lines.append(f"当前时间：{now.strftime('%Y年%m月%d日')}\n")
    
    # 基于月份的一般性建议
    lines.append("### 📅 一般性规律")
    if 4 <= month <= 6:
        lines.append("- **早鸟票窗口期**：崇礼/东北雪场通常在 4-6 月放早鸟票")
        lines.append("- **建议动作**：关注雪场官方公众号，加入预售监听")
    elif 7 <= month <= 9:
        lines.append("- **早鸟票中后期**：部分雪场可能仍有早鸟价，但选择减少")
        lines.append("- **建议动作**：对比早鸟剩余 vs 正价，计算差价是否值得等待")
    elif 10 <= month <= 11:
        lines.append("- **雪季前最后窗口**：可能有限时促销或尾单")
        lines.append("- **建议动作**：关注 OTA 平台促销，考虑住滑套餐")
    elif 12 <= month <= 2:
        lines.append("- **雪季中**：早鸟已结束，价格通常为正价")
        lines.append("- **建议动作**：关注次卡/季卡转让，或预订下季早鸟")
    else:  # 3月
        lines.append("- **雪季尾声**：可能有本季末促销或下季早鸟预告")
        lines.append("- **建议动作**：总结本季消费，规划下季早鸟策略")
    
    # 如果有历史数据，加上个性化建议
    history = _load_price_history()
    records = [r for r in history.get("records", []) if r["resort"] == resort]
    if product:
        records = [r for r in records if r["product"] == product]
    
    if records:
        lines.append("\n### 📊 基于历史数据的建议")
        trend_result = price_trend(params)
        # 提取关键结论
        if "建议购买" in trend_result:
            lines.append("- **价格判断**：当前价格接近历史低位，可考虑入手")
        elif "可观望" in trend_result:
            lines.append("- **价格判断**：当前价格偏高，建议等待或寻找替代方案")
    
    lines.append("\n### ⚠️ 免责声明")
    lines.append("以上建议基于历史规律和有限数据，实际价格受市场供需影响，请以官方渠道为准。")
    
    return "\n".join(lines)


def check_all() -> str:
    """
    生成所有监听项的搜索关键词列表，供 Agent 批量搜索后调用 check。
    这是一个手动触发命令，无需外部定时任务。

    使用方式：
    1. 运行 check-all 获取搜索关键词
    2. Agent 用 WebSearch 批量搜索
    3. 将搜索结果传入 check 命令
    """
    wl = _load_watchlist()
    if not wl["resorts"]:
        return "📡 当前没有监听任何雪场。使用 watch 命令添加。"

    lines = ["🔍 预售监听搜索任务\n"]
    lines.append("请按以下关键词依次搜索，并将结果传入 check 命令：\n")

    for r in wl["resorts"]:
        if r.get("last_status") == "已开售":
            lines.append(f"  ✅ {r['name']} — 已开售，无需重复检查")
            continue
        keywords = r.get("keywords", [f"{r['name']} 早鸟票"])
        lines.append(f"  🔴 {r['name']}")
        for kw in keywords:
            lines.append(f"     搜索：\"{kw} 2026\"")
        lines.append("")

    lines.append(f"\n共需检查 {sum(1 for r in wl['resorts'] if r.get('last_status') != '已开售')} 个雪场")
    lines.append("搜索完成后，使用 check 命令传入结果。")

    return "\n".join(lines)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]

    try:
        if cmd == "watch":
            track_usage("presale_monitor.watch")
            params = json.loads(sys.argv[2]) if len(sys.argv) > 2 else json.load(sys.stdin)
            print(watch(params))
        elif cmd == "list":
            track_usage("presale_monitor.list")
            print(list_watchlist())
        elif cmd == "check":
            track_usage("presale_monitor.check")
            params = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {"results": []}
            print(check(params))
        elif cmd == "remove":
            track_usage("presale_monitor.remove")
            params = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {"resorts": []}
            print(remove(params))
        elif cmd == "status":
            track_usage("presale_monitor.status")
            print(status())
        elif cmd == "check-all":
            track_usage("presale_monitor.check-all")
            print(check_all())
        elif cmd == "record-price":
            track_usage("presale_monitor.record-price")
            params = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
            print(record_price(params))
        elif cmd == "price-trend":
            track_usage("presale_monitor.price-trend")
            params = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
            print(price_trend(params))
        elif cmd == "buying-advice":
            track_usage("presale_monitor.buying-advice")
            params = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
            print(buying_advice(params))
        else:
            print(f"❌ 未知命令: {cmd}")
            print(__doc__)
            sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"❌ JSON 参数格式错误：{e}")
        print(f"💡 请使用有效的 JSON 字符串，例如：")
        print(f'   echo \'{{"resort":"万龙"}}\' | python scripts/presale_monitor.py {cmd}')
        sys.exit(1)
    except Exception as e:
        print(f"❌ 执行出错：{type(e).__name__}: {e}")
        sys.exit(1)
