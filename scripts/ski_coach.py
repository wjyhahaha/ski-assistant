#!/usr/bin/env python3
"""
滑雪电子教练 - 数据管理与进步追踪
用法: python scripts/ski_coach.py <command> [args]

命令:
  record   '<json>'    记录一次滑雪分析结果
  history  [json]      查看历史记录（可选过滤条件）
  progress [json]      生成进步报告
  season   [json]      生成雪季总结
  config   '<json>'    配置分析模型和偏好
  show-config          显示当前配置
  stats                输出统计摘要
  export   [path]      导出所有数据为 JSON

数据存储：通过 utils.py 统一管理，默认 ~/.ski-assistant/
"""

import json
import os
import sys
from datetime import datetime
from collections import defaultdict

# ─── 导入共享工具 ───
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SCRIPT_DIR)
from utils import (
    DATA_DIR, RECORDS_PATH, CONFIG_PATH, CST,
    ensure_dir, load_json, save_json, level_label,
)

# ─── 评分维度定义 ───

SCORE_DIMENSIONS = {
    "posture": {
        "label": "基础姿态",
        "sub": {
            "center_of_gravity": "重心位置",
            "knee_bend": "膝盖弯曲",
            "upper_body": "上半身姿态",
            "arm_position": "手臂位置",
            "hip_alignment": "髋部对齐",
            "ankle_flex": "踝关节屈曲",
        }
    },
    "turning": {
        "label": "转弯技术",
        "sub": {
            "parallel_stance": "平行站姿",
            "edge_angle": "立刃角度",
            "edge_transition": "换刃时机",
            "carving_quality": "卡宾质量",
            "turn_shape": "弯型控制",
            "pole_plant": "点杖技术",
        }
    },
    "freestyle": {
        "label": "自由式/公园",
        "sub": {
            "takeoff": "起跳",
            "air_control": "空中控制",
            "landing": "落地",
            "trick_execution": "技巧完成度",
            "style": "风格表现",
        }
    },
    "overall": {
        "label": "综合滑行",
        "sub": {
            "speed_control": "速度控制",
            "line_choice": "路线选择",
            "terrain_adaptation": "地形适应",
            "rhythm": "节奏感",
            "confidence": "自信度",
            "safety_awareness": "安全意识",
        }
    }
}

DEFAULT_CONFIG = {
    "model": {
        "provider": "auto",
        "name": "",
        "api_key_env": "",
        "note": "设为 auto 时使用当前 Agent 的默认视觉模型；也可指定 provider 和 model name"
    },
    "analysis_preset": {
        "dimensions": ["posture", "turning", "overall"],
        "level": "intermediate",
        "sport_type": "alpine",
        "language": "zh-CN"
    },
    "scoring": {
        "scale": 10,
        "show_sub_scores": True,
        "min_improvement_threshold": 0.5
    },
    "available_providers": [
        {"provider": "auto", "description": "使用当前 Agent 默认视觉模型"},
        {"provider": "openai", "models": ["gpt-4o", "gpt-4o-mini"], "description": "OpenAI GPT-4 Vision"},
        {"provider": "anthropic", "models": ["claude-sonnet-4-20250514", "claude-3.5-sonnet"], "description": "Anthropic Claude Vision"},
        {"provider": "google", "models": ["gemini-2.0-flash", "gemini-2.0-pro"], "description": "Google Gemini Vision"},
        {"provider": "qwen", "models": ["qwen-vl-max", "qwen-vl-plus"], "description": "通义千问视觉模型"},
        {"provider": "doubao", "models": ["doubao-vision-pro", "doubao-vision-lite"], "description": "豆包视觉模型"},
        {"provider": "stepfun", "models": ["step-1v"], "description": "阶跃星辰视觉模型"},
        {"provider": "zhipu", "models": ["glm-4v-plus", "glm-4v"], "description": "智谱 GLM-4V 视觉模型"}
    ]
}


# ─── 基础工具 ───

def _load_records() -> list:
    return load_json(RECORDS_PATH, [])

def _save_records(records: list):
    save_json(RECORDS_PATH, records)

def _load_config() -> dict:
    cfg = load_json(CONFIG_PATH, {})
    if not cfg:
        return DEFAULT_CONFIG.copy()
    # Merge with defaults for any missing keys
    for k, v in DEFAULT_CONFIG.items():
        if k not in cfg:
            cfg[k] = v
    return cfg

def _save_config(cfg: dict):
    save_json(CONFIG_PATH, cfg)


def _avg(values: list) -> float:
    return round(sum(values) / len(values), 1) if values else 0


def _score_bar(score: float, scale: int = 10) -> str:
    filled = round(score / scale * 10)
    return "█" * filled + "░" * (10 - filled)


# level_label 已从 utils 导入，不再重复定义


# ─── 核心命令 ───

def record(params: dict) -> str:
    """
    记录一次滑雪分析结果。
    参数示例:
    {
        "session_id": "20260115-wanlong",
        "date": "2026-01-15",
        "resort": "万龙滑雪场",
        "run_name": "金龙道 第3趟",
        "trail_difficulty": "黑道",
        "snow_condition": "粉雪",
        "media_type": "video",
        "media_path": "/path/to/video.mp4",
        "level": "intermediate",
        "sport_type": "alpine",
        "scores": {
            "posture": {
                "center_of_gravity": 7.5,
                "knee_bend": 6.0,
                "upper_body": 8.0,
                "arm_position": 7.0,
                "hip_alignment": 6.5,
                "ankle_flex": 5.5
            },
            "turning": {
                "parallel_stance": 7.0,
                "edge_angle": 6.5,
                "edge_transition": 5.5,
                "carving_quality": 6.0,
                "turn_shape": 7.0,
                "pole_plant": 4.0
            },
            "overall": {
                "speed_control": 7.5,
                "line_choice": 7.0,
                "terrain_adaptation": 6.0,
                "rhythm": 6.5,
                "confidence": 7.5,
                "safety_awareness": 8.0
            }
        },
        "highlights": ["重心前倾意识有进步", "卡宾弧度比上次更流畅"],
        "issues": ["换刃时上半身有反向旋转", "点杖时机偏晚"],
        "advice": [
            "练习原地换刃: 在缓坡反复练习，关注上半身保持面向山下",
            "点杖节奏训练: 用点杖引导转弯节奏，先在蓝道练习"
        ],
        "coach_note": "整体进步明显，重心控制是本次最大亮点。下次重点攻克换刃时的上半身稳定性。"
    }
    """
    records = _load_records()
    cfg = _load_config()
    scale = cfg.get("scoring", {}).get("scale", 10)

    entry = {
        "id": params.get("session_id", datetime.now(CST).strftime("%Y%m%d-%H%M%S")),
        "date": params.get("date", datetime.now(CST).strftime("%Y-%m-%d")),
        "resort": params.get("resort", ""),
        "run_name": params.get("run_name", ""),
        "trail_difficulty": params.get("trail_difficulty", ""),
        "snow_condition": params.get("snow_condition", ""),
        "media_type": params.get("media_type", "photo"),
        "media_path": params.get("media_path", ""),
        "level": params.get("level", cfg.get("analysis_preset", {}).get("level", "")),
        "sport_type": params.get("sport_type", cfg.get("analysis_preset", {}).get("sport_type", "alpine")),
        "scores": params.get("scores", {}),
        "dimension_averages": {},
        "total_score": 0,
        "highlights": params.get("highlights", []),
        "issues": params.get("issues", []),
        "advice": params.get("advice", []),
        "coach_note": params.get("coach_note", ""),
        "recorded_at": datetime.now(CST).isoformat(),
    }

    # Calculate dimension averages and total
    dim_scores = []
    for dim, sub_scores in entry["scores"].items():
        if isinstance(sub_scores, dict):
            vals = [v for v in sub_scores.values() if isinstance(v, (int, float))]
            avg = _avg(vals)
        elif isinstance(sub_scores, (int, float)):
            avg = float(sub_scores)
        else:
            continue
        entry["dimension_averages"][dim] = avg
        dim_scores.append(avg)

    entry["total_score"] = _avg(dim_scores)

    records.append(entry)
    _save_records(records)

    # Format output
    lines = [f"🎿 滑雪分析已记录\n"]
    lines.append(f"📍 {entry['resort']} | {entry['run_name']} | {entry['date']}")
    lines.append(f"🏔️ {entry['trail_difficulty']} | {entry['snow_condition']} | {level_label(entry['level'])}\n")

    lines.append(f"### 综合评分：{entry['total_score']}/{scale}\n")

    for dim, avg in entry["dimension_averages"].items():
        dim_info = SCORE_DIMENSIONS.get(dim, {})
        label = dim_info.get("label", dim)
        bar = _score_bar(avg, scale)
        lines.append(f"**{label}** {bar} {avg}/{scale}")

        if cfg.get("scoring", {}).get("show_sub_scores", True):
            sub_scores = entry["scores"].get(dim, {})
            if isinstance(sub_scores, dict):
                sub_defs = dim_info.get("sub", {})
                for sk, sv in sub_scores.items():
                    sub_label = sub_defs.get(sk, sk)
                    lines.append(f"  · {sub_label}: {sv}/{scale}")
        lines.append("")

    if entry["highlights"]:
        lines.append("✅ **亮点**")
        for h in entry["highlights"]:
            lines.append(f"  - {h}")
        lines.append("")

    if entry["issues"]:
        lines.append("⚠️ **待改进**")
        for i in entry["issues"]:
            lines.append(f"  - {i}")
        lines.append("")

    if entry["advice"]:
        lines.append("📝 **训练建议**")
        for a in entry["advice"]:
            lines.append(f"  - {a}")
        lines.append("")

    if entry["coach_note"]:
        lines.append(f"💬 **教练点评**：{entry['coach_note']}")

    lines.append(f"\n📊 本雪季累计记录：{len(records)} 次")

    return "\n".join(lines)


def history(params: dict = None) -> str:
    """查看历史记录。可选过滤: {"season": "2025-26", "resort": "万龙", "limit": 10}"""
    records = _load_records()
    cfg = _load_config()
    scale = cfg.get("scoring", {}).get("scale", 10)

    if not records:
        return "📋 暂无滑雪记录。上传滑雪照片或视频开始你的第一次分析吧！"

    params = params or {}
    filtered = records

    if params.get("resort"):
        filtered = [r for r in filtered if params["resort"] in r.get("resort", "")]
    if params.get("season"):
        season = params["season"]
        start_year = int(season.split("-")[0])
        filtered = [r for r in filtered
                    if r.get("date", "")[:4] in (str(start_year), str(start_year + 1))]
    if params.get("level"):
        filtered = [r for r in filtered if r.get("level") == params["level"]]
    if params.get("sport_type"):
        filtered = [r for r in filtered if r.get("sport_type") == params["sport_type"]]

    limit = params.get("limit", 20)
    filtered = filtered[-limit:]

    lines = [f"📋 滑雪记录（共 {len(records)} 条，显示 {len(filtered)} 条）\n"]
    lines.append("| 日期 | 雪场 | 雪道 | 难度 | 综合分 | 亮点 | 待改进 |")
    lines.append("|------|------|------|------|--------|------|--------|")

    for r in filtered:
        highlights = r.get("highlights", [])
        issues = r.get("issues", [])
        h_text = highlights[0][:15] + "..." if highlights else "-"
        i_text = issues[0][:15] + "..." if issues else "-"
        lines.append(
            f"| {r.get('date', '')} | {r.get('resort', '')} "
            f"| {r.get('run_name', '')} | {r.get('trail_difficulty', '')} "
            f"| {r.get('total_score', 0)}/{scale} | {h_text} | {i_text} |"
        )

    return "\n".join(lines)


def progress(params: dict = None) -> str:
    """
    生成进步报告。
    可选参数: {"last_n": 10} 或 {"from": "2026-01-01", "to": "2026-03-31"}
    """
    records = _load_records()
    cfg = _load_config()
    scale = cfg.get("scoring", {}).get("scale", 10)
    threshold = cfg.get("scoring", {}).get("min_improvement_threshold", 0.5)

    if len(records) < 2:
        return "📈 至少需要 2 次记录才能生成进步报告。继续滑雪并记录吧！"

    params = params or {}
    filtered = records

    if params.get("from"):
        filtered = [r for r in filtered if r.get("date", "") >= params["from"]]
    if params.get("to"):
        filtered = [r for r in filtered if r.get("date", "") <= params["to"]]
    if params.get("last_n"):
        filtered = filtered[-params["last_n"]:]

    if len(filtered) < 2:
        return "📈 筛选后记录不足 2 条，无法生成对比。请调整条件。"

    first = filtered[0]
    last = filtered[-1]

    lines = [f"📈 滑雪进步报告\n"]
    lines.append(f"📅 {first['date']} → {last['date']}（共 {len(filtered)} 次记录）\n")

    # Dimension trends
    lines.append("### 各维度变化趋势\n")
    lines.append("| 维度 | 首次 | 最近 | 变化 | 趋势 |")
    lines.append("|------|------|------|------|------|")

    improved_dims = []
    declined_dims = []

    all_dims = set()
    for r in filtered:
        all_dims.update(r.get("dimension_averages", {}).keys())

    for dim in all_dims:
        dim_info = SCORE_DIMENSIONS.get(dim, {})
        label = dim_info.get("label", dim)

        first_vals = [r["dimension_averages"][dim] for r in filtered[:3]
                      if dim in r.get("dimension_averages", {})]
        last_vals = [r["dimension_averages"][dim] for r in filtered[-3:]
                     if dim in r.get("dimension_averages", {})]

        if not first_vals or not last_vals:
            continue

        first_avg = _avg(first_vals)
        last_avg = _avg(last_vals)
        change = round(last_avg - first_avg, 1)

        if change > threshold:
            trend = "📈 进步"
            improved_dims.append((label, change))
        elif change < -threshold:
            trend = "📉 退步"
            declined_dims.append((label, change))
        else:
            trend = "➡️ 稳定"

        sign = "+" if change > 0 else ""
        lines.append(f"| {label} | {first_avg}/{scale} | {last_avg}/{scale} | {sign}{change} | {trend} |")

    # Total score trend
    total_scores = [r.get("total_score", 0) for r in filtered if r.get("total_score")]
    if len(total_scores) >= 2:
        first_total = _avg(total_scores[:3])
        last_total = _avg(total_scores[-3:])
        total_change = round(last_total - first_total, 1)
        sign = "+" if total_change > 0 else ""
        lines.append(f"\n**综合评分趋势**：{first_total} → {last_total}（{sign}{total_change}）\n")

    # Sub-dimension details
    lines.append("### 细项进步最大 Top 5\n")
    sub_changes = []
    for dim in all_dims:
        dim_info = SCORE_DIMENSIONS.get(dim, {})
        sub_defs = dim_info.get("sub", {})
        for sub_key, sub_label in sub_defs.items():
            first_sub = [r["scores"].get(dim, {}).get(sub_key)
                         for r in filtered[:3]
                         if isinstance(r.get("scores", {}).get(dim), dict)
                         and sub_key in r["scores"][dim]]
            last_sub = [r["scores"].get(dim, {}).get(sub_key)
                        for r in filtered[-3:]
                        if isinstance(r.get("scores", {}).get(dim), dict)
                        and sub_key in r["scores"][dim]]

            first_sub = [v for v in first_sub if v is not None]
            last_sub = [v for v in last_sub if v is not None]

            if first_sub and last_sub:
                change = round(_avg(last_sub) - _avg(first_sub), 1)
                sub_changes.append((f"{dim_info.get('label', dim)} > {sub_label}",
                                    _avg(first_sub), _avg(last_sub), change))

    sub_changes.sort(key=lambda x: x[3], reverse=True)

    lines.append("| 细项 | 首次 | 最近 | 进步幅度 |")
    lines.append("|------|------|------|----------|")
    for name, f_val, l_val, change in sub_changes[:5]:
        sign = "+" if change > 0 else ""
        lines.append(f"| {name} | {f_val} | {l_val} | {sign}{change} |")

    # Recurring issues
    lines.append("\n### 反复出现的问题\n")
    issue_count = defaultdict(int)
    for r in filtered:
        for issue in r.get("issues", []):
            issue_count[issue] += 1

    recurring = sorted(issue_count.items(), key=lambda x: -x[1])[:5]
    if recurring:
        for issue, count in recurring:
            lines.append(f"  - ({count}次) {issue}")
    else:
        lines.append("  暂无反复出现的问题，表现稳定！")

    # Summary
    lines.append("\n### 总结\n")
    if improved_dims:
        names = "、".join([d[0] for d in improved_dims])
        lines.append(f"✅ 明显进步的维度：{names}")
    if declined_dims:
        names = "、".join([d[0] for d in declined_dims])
        lines.append(f"⚠️ 需要关注的维度：{names}")

    return "\n".join(lines)


def season_summary(params: dict = None) -> str:
    """
    生成雪季总结。
    参数: {"season": "2025-26"} 或自动检测当前雪季
    """
    records = _load_records()
    cfg = _load_config()
    scale = cfg.get("scoring", {}).get("scale", 10)

    if not records:
        return "🏔️ 暂无滑雪记录，无法生成雪季总结。"

    params = params or {}
    season_label = params.get("season", "")

    # Auto-detect season from records
    if not season_label:
        dates = sorted([r.get("date", "") for r in records if r.get("date")])
        if dates:
            year = int(dates[-1][:4])
            month = int(dates[-1][5:7])
            if month >= 10:
                season_label = f"{year}-{str(year + 1)[-2:]}"
            else:
                season_label = f"{year - 1}-{str(year)[-2:]}"

    # Filter records for the season
    start_year = int(season_label.split("-")[0])
    season_start = f"{start_year}-10-01"
    season_end = f"{start_year + 1}-05-31"
    filtered = [r for r in records
                if season_start <= r.get("date", "") <= season_end]

    if not filtered:
        return f"🏔️ {season_label} 雪季暂无记录。"

    lines = [f"🏔️ {season_label} 雪季总结\n"]
    lines.append(f"📅 {filtered[0]['date']} — {filtered[-1]['date']}\n")

    # Basic stats
    total_sessions = len(filtered)
    resorts = set(r.get("resort", "") for r in filtered if r.get("resort"))
    difficulties = defaultdict(int)
    sport_types = defaultdict(int)
    for r in filtered:
        if r.get("trail_difficulty"):
            difficulties[r["trail_difficulty"]] += 1
        if r.get("sport_type"):
            sport_types[r["sport_type"]] += 1

    lines.append(f"### 数据概览\n")
    lines.append(f"  - 总滑雪次数：**{total_sessions}** 次")
    lines.append(f"  - 去过的雪场：**{len(resorts)}** 个（{'、'.join(resorts)}）")
    if difficulties:
        diff_str = "、".join([f"{k} {v}次" for k, v in
                             sorted(difficulties.items(), key=lambda x: -x[1])])
        lines.append(f"  - 雪道难度分布：{diff_str}")
    lines.append("")

    # Score evolution
    total_scores = [r.get("total_score", 0) for r in filtered if r.get("total_score")]
    if total_scores:
        lines.append("### 评分变化\n")
        lines.append(f"  - 首次综合分：**{total_scores[0]}/{scale}**")
        lines.append(f"  - 最近综合分：**{total_scores[-1]}/{scale}**")
        lines.append(f"  - 最高综合分：**{max(total_scores)}/{scale}**")
        lines.append(f"  - 平均综合分：**{_avg(total_scores)}/{scale}**")
        change = round(total_scores[-1] - total_scores[0], 1)
        sign = "+" if change > 0 else ""
        lines.append(f"  - 整季变化：**{sign}{change}**")
        lines.append("")

    # Dimension progress
    all_dims = set()
    for r in filtered:
        all_dims.update(r.get("dimension_averages", {}).keys())

    if all_dims:
        lines.append("### 各维度成长\n")
        lines.append("| 维度 | 赛季初 | 赛季末 | 最高 | 成长幅度 |")
        lines.append("|------|--------|--------|------|----------|")

        for dim in all_dims:
            dim_info = SCORE_DIMENSIONS.get(dim, {})
            label = dim_info.get("label", dim)
            vals = [r["dimension_averages"][dim]
                    for r in filtered if dim in r.get("dimension_averages", {})]
            if len(vals) >= 2:
                change = round(vals[-1] - vals[0], 1)
                sign = "+" if change > 0 else ""
                lines.append(
                    f"| {label} | {vals[0]} | {vals[-1]} | {max(vals)} | {sign}{change} |"
                )
        lines.append("")

    # Top highlights and recurring issues
    all_highlights = []
    all_issues = defaultdict(int)
    for r in filtered:
        all_highlights.extend(r.get("highlights", []))
        for issue in r.get("issues", []):
            all_issues[issue] += 1

    if all_highlights:
        lines.append("### 本季亮点时刻\n")
        # Show unique highlights
        seen = set()
        for h in all_highlights:
            if h not in seen:
                lines.append(f"  - {h}")
                seen.add(h)
                if len(seen) >= 8:
                    break
        lines.append("")

    if all_issues:
        lines.append("### 持续改进方向\n")
        sorted_issues = sorted(all_issues.items(), key=lambda x: -x[1])[:5]
        for issue, count in sorted_issues:
            status = "✅ 已改善" if count == 1 else f"🔄 出现 {count} 次"
            lines.append(f"  - {issue}（{status}）")
        lines.append("")

    # Level progression
    levels = [r.get("level", "") for r in filtered if r.get("level")]
    if levels and levels[0] != levels[-1]:
        lines.append(f"### 🎯 水平提升：{level_label(levels[0])} → {level_label(levels[-1])}\n")

    # Next season advice
    lines.append("### 下赛季建议\n")
    lines.append("基于本季数据，AI 教练将结合你的薄弱环节为下赛季制定针对性训练计划。")

    return "\n".join(lines)


def config(params: dict) -> str:
    """
    配置分析模型和偏好。
    参数示例:
    {
        "model": {
            "provider": "openai",
            "name": "gpt-4o",
            "api_key_env": "OPENAI_API_KEY"
        },
        "analysis_preset": {
            "dimensions": ["posture", "turning", "freestyle", "overall"],
            "level": "advanced",
            "sport_type": "alpine",
            "language": "zh-CN"
        },
        "scoring": {
            "scale": 10,
            "show_sub_scores": true,
            "min_improvement_threshold": 0.5
        }
    }
    """
    cfg = _load_config()

    # Deep merge
    for key, val in params.items():
        if isinstance(val, dict) and isinstance(cfg.get(key), dict):
            cfg[key].update(val)
        else:
            cfg[key] = val

    _save_config(cfg)

    lines = ["⚙️ 电子教练配置已更新\n"]

    model = cfg.get("model", {})
    provider = model.get("provider", "auto")
    model_name = model.get("name", "")
    if provider == "auto":
        lines.append("🤖 分析模型：自动（使用当前 Agent 默认视觉模型）")
    else:
        lines.append(f"🤖 分析模型：{provider} / {model_name}")

    preset = cfg.get("analysis_preset", {})
    dims = preset.get("dimensions", [])
    dim_labels = [SCORE_DIMENSIONS.get(d, {}).get("label", d) for d in dims]
    lines.append(f"📊 评分维度：{' | '.join(dim_labels)}")
    lines.append(f"🎿 水平设定：{level_label(preset.get('level', ''))}")
    lines.append(f"🏂 运动类型：{preset.get('sport_type', 'alpine')}")

    scoring = cfg.get("scoring", {})
    lines.append(f"📏 评分量程：{scoring.get('scale', 10)} 分制")

    return "\n".join(lines)


def show_config() -> str:
    cfg = _load_config()

    lines = ["⚙️ 当前电子教练配置\n"]

    model = cfg.get("model", {})
    provider = model.get("provider", "auto")
    if provider == "auto":
        lines.append("🤖 **分析模型**：auto（使用当前 Agent 默认视觉模型）")
    else:
        lines.append(f"🤖 **分析模型**：{provider} / {model.get('name', '')}")

    lines.append("\n📋 **可选模型列表**：")
    lines.append("| 提供商 | 可用模型 | 说明 |")
    lines.append("|--------|----------|------|")
    for p in cfg.get("available_providers", DEFAULT_CONFIG["available_providers"]):
        models = ", ".join(p.get("models", ["-"]))
        lines.append(f"| {p['provider']} | {models} | {p['description']} |")

    preset = cfg.get("analysis_preset", {})
    dims = preset.get("dimensions", [])
    dim_labels = [SCORE_DIMENSIONS.get(d, {}).get("label", d) for d in dims]
    lines.append(f"\n📊 **评分维度**：{' | '.join(dim_labels)}")
    lines.append(f"🎿 **水平设定**：{level_label(preset.get('level', ''))}")
    lines.append(f"🏂 **运动类型**：{preset.get('sport_type', 'alpine')}")

    scoring = cfg.get("scoring", {})
    lines.append(f"📏 **评分量程**：{scoring.get('scale', 10)} 分制")
    lines.append(f"📝 **显示细分项**：{'是' if scoring.get('show_sub_scores') else '否'}")

    lines.append(f"\n💾 数据目录：{DATA_DIR}")
    lines.append(f"💾 配置文件：{CONFIG_PATH}")
    lines.append(f"💾 记录文件：{RECORDS_PATH}")

    return "\n".join(lines)


def stats() -> str:
    records = _load_records()
    cfg = _load_config()
    scale = cfg.get("scoring", {}).get("scale", 10)

    if not records:
        return "📊 暂无统计数据。"

    total = len(records)
    resorts = set(r.get("resort", "") for r in records if r.get("resort"))
    total_scores = [r.get("total_score", 0) for r in records if r.get("total_score")]
    dates = sorted([r.get("date", "") for r in records if r.get("date")])

    lines = ["📊 滑雪数据统计\n"]
    lines.append(f"  - 总记录数：{total} 次")
    lines.append(f"  - 雪场数量：{len(resorts)} 个")
    if dates:
        lines.append(f"  - 记录时间跨度：{dates[0]} ~ {dates[-1]}")
    if total_scores:
        lines.append(f"  - 综合评分范围：{min(total_scores)} ~ {max(total_scores)}/{scale}")
        lines.append(f"  - 平均综合评分：{_avg(total_scores)}/{scale}")
        if len(total_scores) >= 2:
            trend = round(total_scores[-1] - total_scores[0], 1)
            sign = "+" if trend > 0 else ""
            lines.append(f"  - 评分变化趋势：{sign}{trend}")

    return "\n".join(lines)


def export_data(path: str = None) -> str:
    records = _load_records()
    cfg = _load_config()

    data = {
        "exported_at": datetime.now(CST).isoformat(),
        "config": cfg,
        "records": records,
        "total_records": len(records),
    }

    if path:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return f"📁 数据已导出到：{path}（共 {len(records)} 条记录）"
    else:
        return json.dumps(data, ensure_ascii=False, indent=2)


# ─── 主入口 ───

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "record":
        params = json.loads(sys.argv[2]) if len(sys.argv) > 2 else json.load(sys.stdin)
        print(record(params))
    elif cmd == "history":
        params = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
        print(history(params))
    elif cmd == "progress":
        params = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
        print(progress(params))
    elif cmd == "season":
        params = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
        print(season_summary(params))
    elif cmd == "config":
        params = json.loads(sys.argv[2]) if len(sys.argv) > 2 else json.load(sys.stdin)
        print(config(params))
    elif cmd == "show-config":
        print(show_config())
    elif cmd == "stats":
        print(stats())
    elif cmd == "export":
        path = sys.argv[2] if len(sys.argv) > 2 else None
        print(export_data(path))
    else:
        print(f"未知命令: {cmd}")
        print(__doc__)
        sys.exit(1)
