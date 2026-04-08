#!/usr/bin/env python3
"""
早鸟票/住滑套餐预售监听工具
用法: python scripts/presale_monitor.py <command> [args]

命令:
  watch    '<json>'    添加/更新监听项
  list                 列出所有监听项
  check                检查所有监听项的预售状态变化，输出通知内容
  check-all            🆕 生成搜索关键词列表，供 Agent 批量搜索（无需外部定时任务）
  remove   '<json>'    移除监听项
  status               输出当前监听状态摘要

监听数据存储：通过 utils.py 统一管理，默认 ~/.ski-assistant/watchlist.json

工作流程（手动模式，无需外部定时任务）：
1. 运行 check-all 获取所有待检查雪场的搜索关键词
2. Agent 用 WebSearch 批量搜索
3. 将搜索结果传入 check 命令，自动更新状态并生成通知
"""

import json
import os
import sys
from datetime import datetime

# ─── 导入共享工具 ───
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SCRIPT_DIR)
from utils import WATCHLIST_PATH, CST, ensure_dir, load_json, save_json


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
            params = json.loads(sys.argv[2]) if len(sys.argv) > 2 else json.load(sys.stdin)
            print(watch(params))
        elif cmd == "list":
            print(list_watchlist())
        elif cmd == "check":
            params = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {"results": []}
            print(check(params))
        elif cmd == "remove":
            params = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {"resorts": []}
            print(remove(params))
        elif cmd == "status":
            print(status())
        elif cmd == "check-all":
            print(check_all())
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
