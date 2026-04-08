#!/usr/bin/env python3
"""
滑雪装备清单推荐模块
用法: python scripts/gear_guide.py '<json>'

根据用户水平、目的地、季节、出行天数生成个性化装备清单。
区分"必须携带"和"可选"，标注租用 vs 购买建议。
室内雪场和户外雪场清单差异自动适配。

参数:
{
    "level": "beginner",           # 水平: beginner/intermediate/advanced/expert
    "resort_type": "outdoor",       # 类型: outdoor/indoor
    "destination": "崇礼",          # 目的地（影响气候）
    "days": 3,                      # 出行天数
    "has_own_gear": ["helmet"],     # 已有装备列表
    "budget_tier": "mid",           # 预算档位: budget/mid/premium
    "sport_type": "ski",            # 运动类型: ski/snowboard
    "season": "winter",             # 季节: winter/early_winter/spring/summer
}
"""

import json
import os
import re
import sys

# ─── 导入共享工具 ───
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SCRIPT_DIR)
from utils import level_label, sport_label

# ─── 装备数据库 ───

_GEAR_DB = {
    # === 必须装备（安全相关）===
    "helmet": {
        "label": "滑雪头盔",
        "essential": True,
        "can_rent": False,
        "price_range": {"budget": "¥150-250", "mid": "¥300-600", "premium": "¥600-1500"},
        "for_levels": ["beginner", "intermediate", "advanced", "expert"],
        "notes": "必戴！选择有 CE/ASTM 认证的产品",
    },
    "goggles": {
        "label": "滑雪镜",
        "essential": True,
        "can_rent": False,
        "price_range": {"budget": "¥80-150", "mid": "¥200-400", "premium": "¥400-1000"},
        "for_levels": ["beginner", "intermediate", "advanced", "expert"],
        "indoor_only": False,
        "notes": "户外必带防紫外线/防风，阴天用增光镜片（黄/橙色），晴天用偏光镜片",
    },
    "sunscreen": {
        "label": "高倍防晒霜（SPF50+）",
        "essential": True,
        "can_rent": False,
        "price_range": {"budget": "¥50-80", "mid": "¥100-150", "premium": "¥150-300"},
        "for_levels": ["beginner", "intermediate", "advanced", "expert"],
        "indoor_only": False,
        "seasons": ["winter", "early_winter", "spring"],
        "notes": "高海拔 + 雪地反射紫外线极强，必须涂抹",
    },

    # === 服装（户外）===
    "ski_jacket": {
        "label": "滑雪外套/冲锋衣",
        "essential": True,
        "can_rent": True,
        "rent_price": "¥50-100/天",
        "price_range": {"budget": "¥200-400", "mid": "¥500-1000", "premium": "¥1000-3000"},
        "for_levels": ["beginner", "intermediate", "advanced", "expert"],
        "indoor_only": False,
        "notes": "防水 10000mm+、透气 8000g+，颜色鲜艳（方便辨认）",
    },
    "ski_pants": {
        "label": "滑雪裤",
        "essential": True,
        "can_rent": True,
        "rent_price": "¥30-60/天",
        "price_range": {"budget": "¥150-300", "mid": "¥400-800", "premium": "¥800-2000"},
        "for_levels": ["beginner", "intermediate", "advanced", "expert"],
        "indoor_only": False,
        "notes": "背带裤防雪效果优于普通裤",
    },
    "base_layer_top": {
        "label": "速干内衣（排汗层）",
        "essential": True,
        "can_rent": False,
        "price_range": {"budget": "¥50-100", "mid": "¥100-200", "premium": "¥200-500"},
        "for_levels": ["beginner", "intermediate", "advanced", "expert"],
        "indoor_only": False,
        "notes": "棉质不透气，选聚酯纤维或美利奴羊毛",
    },
    "mid_layer": {
        "label": "保暖中间层（抓绒衣/轻薄羽绒）",
        "essential": True,
        "can_rent": False,
        "price_range": {"budget": "¥80-150", "mid": "¥200-400", "premium": "¥400-800"},
        "for_levels": ["beginner", "intermediate", "advanced", "expert"],
        "indoor_only": False,
        "notes": "崇礼/东北需要 -10°C 以下保暖层，日本北海道需更厚",
    },

    # === 手套/护具 ===
    "ski_gloves": {
        "label": "滑雪手套",
        "essential": True,
        "can_rent": True,
        "rent_price": "¥20-40/天",
        "price_range": {"budget": "¥50-100", "mid": "¥100-250", "premium": "¥250-600"},
        "for_levels": ["beginner", "intermediate", "advanced", "expert"],
        "indoor_only": False,
        "notes": "防水保暖，连指手套比五指更暖",
    },
    "wrist_guards": {
        "label": "护腕（单板必备）",
        "essential": True,
        "can_rent": True,
        "rent_price": "¥20-30/天",
        "price_range": {"budget": "¥50-100", "mid": "¥100-200", "premium": "¥200-400"},
        "for_levels": ["beginner", "intermediate"],
        "sport_type": "snowboard",
        "notes": "单板初学者必戴，大幅降低手腕骨折风险",
    },
    "knee_pads": {
        "label": "护膝（单板推荐）",
        "essential": False,
        "can_rent": True,
        "rent_price": "¥20-30/天",
        "price_range": {"budget": "¥50-100", "mid": "¥100-200", "premium": "¥200-400"},
        "for_levels": ["beginner", "intermediate"],
        "sport_type": "snowboard",
        "notes": "单板摔膝盖概率高，建议佩戴",
    },
    "butt_pad": {
        "label": "小乌龟/护臀（单板初学者推荐）",
        "essential": False,
        "can_rent": True,
        "rent_price": "¥15-30/天",
        "price_range": {"budget": "¥30-60", "mid": "¥60-120", "premium": "¥120-250"},
        "for_levels": ["beginner"],
        "sport_type": "snowboard",
        "notes": "减少摔跤痛苦，提高练习信心",
    },
    "back_protector": {
        "label": "护背（公园/进阶推荐）",
        "essential": False,
        "can_rent": True,
        "rent_price": "¥30-50/天",
        "price_range": {"budget": "¥100-200", "mid": "¥200-400", "premium": "¥400-800"},
        "for_levels": ["intermediate", "advanced"],
        "notes": "公园跳台或练刻滑时保护脊椎",
    },

    # === 袜子/配件 ===
    "ski_socks": {
        "label": "滑雪袜（长筒）",
        "essential": True,
        "can_rent": False,
        "price_range": {"budget": "¥30-50", "mid": "¥60-120", "premium": "¥120-250"},
        "for_levels": ["beginner", "intermediate", "advanced", "expert"],
        "notes": "选有压缩支撑的款式，减少小腿疲劳，不要穿两双袜子（影响血循环）",
    },
    "neck_gaiter": {
        "label": "围脖/面罩",
        "essential": True,
        "can_rent": True,
        "rent_price": "¥10-20/天",
        "price_range": {"budget": "¥20-40", "mid": "¥50-100", "premium": "¥100-200"},
        "for_levels": ["beginner", "intermediate", "advanced", "expert"],
        "indoor_only": False,
        "notes": "防风保暖，崇礼/东北必备",
    },

    # === 滑雪器材（可租可买）===
    "skis": {
        "label": "双板（板 + 固定器 + 雪杖）",
        "essential": True,
        "can_rent": True,
        "rent_price": "¥100-200/天（含固定器）",
        "price_range": {"budget": "¥1500-3000", "mid": "¥3000-6000", "premium": "¥6000-15000"},
        "for_levels": ["beginner", "intermediate", "advanced", "expert"],
        "sport_type": "ski",
        "notes": "初学者建议租雪场的，水平提升后再购买",
    },
    "snowboard": {
        "label": "单板（板 + 固定器）",
        "essential": True,
        "can_rent": True,
        "rent_price": "¥100-200/天（含固定器）",
        "price_range": {"budget": "¥1500-3000", "mid": "¥3000-6000", "premium": "¥6000-15000"},
        "for_levels": ["beginner", "intermediate", "advanced", "expert"],
        "sport_type": "snowboard",
        "notes": "初学者建议租雪场的，学会推坡和换刃后再购买",
    },
    "ski_boots": {
        "label": "滑雪鞋",
        "essential": True,
        "can_rent": True,
        "rent_price": "¥50-100/天",
        "price_range": {"budget": "¥800-1500", "mid": "¥1500-3000", "premium": "¥3000-6000"},
        "for_levels": ["beginner", "intermediate", "advanced", "expert"],
        "notes": "鞋子合脚最重要！建议先租再买，买前务必试穿",
    },

    # === 安全用品 ===
    "insurance": {
        "label": "滑雪专项保险",
        "essential": True,
        "can_rent": False,
        "price_range": {"budget": "¥30-50/天", "mid": "¥50-100/天", "premium": "¥100-200/天"},
        "for_levels": ["beginner", "intermediate", "advanced", "expert"],
        "notes": "普通旅游险通常不含滑雪，必须买专项险！国际出行需含紧急救援",
    },
    "avalanche_beacon": {
        "label": "雪崩搜救仪",
        "essential": False,
        "can_rent": True,
        "rent_price": "¥50-100/天",
        "price_range": {"budget": "¥800-1500", "mid": "¥1500-3000", "premium": "¥3000-5000"},
        "for_levels": ["advanced", "expert"],
        "notes": "野雪/非雪道区域必备，需搭配探杆和雪铲使用",
    },

    # === 电子产品 ===
    "action_camera": {
        "label": "运动相机（GoPro/Insta360）",
        "essential": False,
        "can_rent": True,
        "rent_price": "¥50-100/天",
        "price_range": {"budget": "¥500-1000", "mid": "¥1500-3000", "premium": "¥3000-5000"},
        "for_levels": ["beginner", "intermediate", "advanced", "expert"],
        "notes": "记录滑雪视频，方便 AI 教练分析动作",
    },
    "hand_warmers": {
        "label": "暖宝宝/暖手贴",
        "essential": False,
        "can_rent": False,
        "price_range": {"budget": "¥10-20/包", "mid": "¥20-40/包", "premium": "¥40-80/包"},
        "for_levels": ["beginner", "intermediate", "advanced", "expert"],
        "indoor_only": False,
        "seasons": ["winter", "early_winter"],
        "notes": "贴在手套里或鞋里，极寒天气必备",
    },
}

# 气候适配
_CLIMATE_GEAR = {
    "崇礼": {
        "extra": ["neck_gaiter", "hand_warmers"],
        "notes": "崇礼冬季 -10°C 至 -25°C，风寒效应明显，需充分保暖",
        "temperature_range": "-25°C ~ -5°C",
    },
    "东北": {
        "extra": ["neck_gaiter", "hand_warmers"],
        "notes": "东北冬季 -15°C 至 -35°C，全国最冷区域，需要极地级保暖",
        "temperature_range": "-35°C ~ -10°C",
    },
    "新疆": {
        "extra": ["neck_gaiter", "hand_warmers", "sunscreen"],
        "notes": "新疆阿勒泰粉雪天堂，-10°C 至 -25°C，紫外线强需防晒",
        "temperature_range": "-25°C ~ -5°C",
    },
    "北京周边": {
        "extra": ["sunscreen"],
        "notes": "北京周边 -5°C 至 -15°C，当日往返无需太多行李",
        "temperature_range": "-15°C ~ 0°C",
    },
    "日本": {
        "extra": ["hand_warmers", "sunscreen"],
        "notes": "日本粉雪区 -5°C 至 -15°C，降雪量大需防水性能好的装备",
        "temperature_range": "-15°C ~ 0°C",
    },
    "欧洲": {
        "extra": ["sunscreen"],
        "notes": "欧洲阿尔卑斯 -5°C 至 -20°C，海拔高紫外线强",
        "temperature_range": "-20°C ~ 0°C",
    },
    "北美": {
        "extra": ["sunscreen"],
        "notes": "北美各雪场 -10°C 至 5°C，温差大需分层穿衣",
        "temperature_range": "-15°C ~ 5°C",
    },
    "南半球": {
        "extra": ["sunscreen"],
        "notes": "反季滑雪（6-10月），白天可能到 5°C，注意防晒",
        "temperature_range": "-10°C ~ 5°C",
    },
    "室内": {
        "extra": [],
        "notes": "室内恒温 -3°C 至 -5°C，无需厚重保暖层",
        "temperature_range": "-5°C ~ -3°C（恒温）",
    },
}


def generate_gear_guide(params: dict) -> str:
    """生成装备清单。"""
    level = params.get("level", "beginner")
    sport_type = params.get("sport_type", "ski")
    resort_type = params.get("resort_type", "outdoor")
    destination = params.get("destination", "")
    days = params.get("days", 3)
    budget_tier = params.get("budget_tier", "mid")
    has_own = set(params.get("has_own_gear", []))

    # 确定季节
    season = params.get("season", "winter")
    if not season:
        from datetime import datetime
        month = datetime.now().month
        if month in (11, 12, 1, 2): season = "winter"
        elif month in (3, 4): season = "spring"
        elif month in (10): season = "early_winter"
        else: season = "summer"

    # 室内/户外
    is_indoor = resort_type == "indoor" or destination == "室内"

    # 获取气候信息
    # 目的地→气候区域的模糊映射（支持子地区匹配到父区域）
    _DEST_ALIAS = {
        "北海道": "日本", "白马": "日本", "妙高": "日本", "二世谷": "日本", "长野": "日本",
        "富良野": "日本", "留寿都": "日本", "志贺": "日本", "野泽": "日本",
        "阿尔卑斯": "欧洲", "夏蒙尼": "欧洲", "采尔马特": "欧洲",
        "惠斯勒": "北美", "范尔": "北美", "帕克城": "北美", "科罗拉多": "北美",
        "皇后镇": "南半球", "新西兰": "南半球", "澳大利亚": "南半球",
        "亚布力": "东北", "北大湖": "东北", "松花湖": "东北", "长白山": "东北",
        "将军山": "新疆", "可可托海": "新疆", "阿勒泰": "新疆",
        "南山": "北京周边", "军都山": "北京周边", "石京龙": "北京周边",
        "万龙": "崇礼", "太舞": "崇礼", "云顶": "崇礼", "富龙": "崇礼",
    }
    climate_key = "室内" if is_indoor else None
    if not climate_key:
        # 优先精确匹配 _CLIMATE_GEAR key
        for ck in _CLIMATE_GEAR:
            if ck in destination:
                climate_key = ck
                break
    if not climate_key:
        # 模糊匹配：检查目的地是否包含某个别名关键词
        for alias, region in _DEST_ALIAS.items():
            if alias in destination:
                climate_key = region
                break
    if not climate_key:
        climate_key = "崇礼"
    climate = _CLIMATE_GEAR.get(climate_key, _CLIMATE_GEAR["崇礼"])

    # 动态生成温度提示
    climate_notes = climate.get("notes", "")
    if destination and climate_key in _CLIMATE_GEAR and climate_key not in destination:
        # 匹配到了父区域，用目的地名替换提示
        climate_notes = f"{destination}（{climate_key}地区）{climate.get('temperature_range', '')}，{climate_notes.split('，', 1)[-1] if '，' in climate_notes else '注意保暖'}"

    # 筛选装备
    essential = []
    optional = []
    already_have = []

    for key, gear in _GEAR_DB.items():
        # 水平过滤
        if level not in gear.get("for_levels", []):
            continue
        # 运动类型过滤
        gear_sport = gear.get("sport_type")
        if gear_sport and gear_sport != sport_type and sport_type != "both":
            continue
        # 室内/户外过滤
        if gear.get("indoor_only") is False and is_indoor:
            if key in ("sunscreen", "ski_jacket", "ski_pants", "neck_gaiter"):
                # 室内也需要部分户外装备
                if key in ("ski_jacket", "ski_pants"):
                    pass  # 室内仍需要外套但不用太厚
                else:
                    continue  # 室内不需要围脖、防晒霜
        if gear.get("indoor_only") is True and not is_indoor:
            continue
        # 季节过滤
        gear_seasons = gear.get("seasons")
        if gear_seasons and season not in gear_seasons:
            continue

        # 检查是否已有
        if key in has_own:
            already_have.append(gear)
            continue

        if gear["essential"]:
            essential.append((key, gear))
        else:
            optional.append((key, gear))

    # 气候额外装备
    climate_extra = climate.get("extra", [])
    extra_gear = []
    for ek in climate_extra:
        if ek in dict(optional) and ek not in has_own:
            extra_gear.append((ek, _GEAR_DB[ek]))

    # 输出
    lines = [f"🎿 滑雪装备清单\n"]
    lines.append(f"📋 适用信息：{level_label(level)} | {sport_label(sport_type)} | {destination or '未指定'} | {days}天")
    lines.append(f"🌡️ 参考温度：{climate.get('temperature_range', '未知')}")
    lines.append(f"📝 {climate_notes}\n")

    if already_have:
        lines.append("✅ 已有装备（无需重复购买）：")
        for g in already_have:
            lines.append(f"  · {g['label']}")
        lines.append("")

    lines.append("### 📌 必须装备\n")
    lines.append("| 物品 | 可租用 | 参考价格 | 建议 |")
    lines.append("|------|--------|---------|------|")
    total_budget_low = 0
    total_budget_high = 0
    for key, gear in essential:
        price = gear.get("price_range", {}).get(budget_tier, "¥-")
        can_rent = "✅ 可租" if gear.get("can_rent") else "❌ 需购买"
        if gear.get("can_rent") and gear.get("rent_price"):
            can_rent = f"✅ 可租（{gear['rent_price']}）"
        suggestion = _suggest(gear, level, days, budget_tier)
        lines.append(f"| {gear['label']} | {can_rent} | {price} | {suggestion} |")

        # 估算费用
        if gear.get("can_rent"):
            rent_total = _calc_rent_cost(gear.get("rent_price", "0/天"), days)
            total_budget_low += rent_total
            total_budget_high += rent_total
        else:
            lo, hi = _parse_price(price)
            total_budget_low += lo
            total_budget_high += hi

    lines.append(f"\n**必须装备预估费用**：¥{total_budget_low} ~ ¥{total_budget_high}\n")

    if optional or extra_gear:
        lines.append("### 💡 推荐装备（非必须但建议携带）\n")
        lines.append("| 物品 | 用途 | 参考价格 |")
        lines.append("|------|------|---------|")
        # 去重：extra_gear 中已在 optional 里的不重复输出
        seen_keys = set()
        for key, gear in optional + extra_gear:
            if key in seen_keys:
                continue
            seen_keys.add(key)
            price = gear.get("price_range", {}).get(budget_tier, "¥-")
            usage = gear.get("notes", "")[:40]
            lines.append(f"| {gear['label']} | {usage} | {price} |")

    # 按天数的穿衣建议
    if days > 1 and not is_indoor:
        lines.append(f"\n### 👕 {days}天穿衣建议\n")
        if days <= 2:
            lines.append("  · 速干内衣：2 件（换洗）")
            lines.append(f"  · 滑雪外套/裤子：1 套")
            lines.append(f"  · 保暖中间层：1 件")
            lines.append(f"  · 滑雪袜：2 双")
        elif days <= 4:
            lines.append("  · 速干内衣：3 件（换洗）")
            lines.append(f"  · 滑雪外套/裤子：1 套")
            lines.append(f"  · 保暖中间层：2 件（可替换）")
            lines.append(f"  · 滑雪袜：3 双")
        else:
            lines.append("  · 速干内衣：带 1 件/天（可中途清洗）")
            lines.append(f"  · 滑雪外套/裤子：1-2 套")
            lines.append(f"  · 保暖中间层：2-3 件")
            lines.append(f"  · 滑雪袜：1 双/天")

    lines.append("\n### ⚠️ 安全提醒\n")
    lines.append("  1. **头盔必戴**！无论水平高低")
    lines.append("  2. **滑雪专项保险必买**，普通旅游险不含滑雪")
    if sport_type == "snowboard" and level == "beginner":
        lines.append("  3. **单板初学者必戴护腕**，可大幅降低手腕骨折风险")
    if is_indoor:
        lines.append(f"  3. 室内雪场温度恒定，无需厚重保暖层，但外套仍是必须")
    else:
        lines.append(f"  3. 崇礼/东北等极寒地区，建议贴暖宝宝在手套和鞋里")

    return "\n".join(lines)


def _suggest(gear, level, days, budget_tier):
    """给出购买/租赁建议。"""
    if level == "beginner" and gear.get("can_rent"):
        return f"初学建议租用，滑{min(days, 3)}天后再决定是否购买"
    if gear.get("can_rent") and days <= 3:
        return f"短期出行推荐租用（{gear.get('rent_price', '')}）"
    if days >= 5 and gear.get("can_rent"):
        return f"长期出行建议购买（{gear.get('price_range', {}).get(budget_tier, '')}）更划算"
    if not gear.get("can_rent"):
        return "必须购买"
    return "按需购买"


def _calc_rent_cost(rent_str, days):
    """从 "¥50-100/天" 格式计算总费用。"""
    m = re.search(r'¥(\d+)', rent_str)
    if m:
        return int(m.group(1)) * days
    return 0


def _parse_price(price_str):
    """从 "¥300-600" 格式解析价格范围。"""
    m = re.search(r'¥(\d+)[-~](\d+)', price_str)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.search(r'¥(\d+)', price_str)
    if m:
        return int(m.group(1)), int(m.group(1))
    return 0, 0


if __name__ == "__main__":
    try:
        if len(sys.argv) > 1:
            params = json.loads(sys.argv[1])
        else:
            params = json.load(sys.stdin)
        print(generate_gear_guide(params))
    except json.JSONDecodeError as e:
        print(f"❌ JSON 参数格式错误：{e}")
        print(f"💡 示例：echo '{{\"level\":\"beginner\",\"resort_type\":\"outdoor\",\"destination\":\"崇礼\",\"days\":3}}' | python scripts/gear_guide.py")
        sys.exit(1)
    except Exception as e:
        print(f"❌ 执行出错：{type(e).__name__}: {e}")
        sys.exit(1)
