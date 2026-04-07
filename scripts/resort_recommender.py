#!/usr/bin/env python3
"""
雪场智能推荐引擎
用法: python scripts/resort_recommender.py <command> [args]

命令:
  profile  '<json>'   设置/更新用户画像
  show-profile        显示当前用户画像
  recommend [json]    基于用户画像推荐雪场
  weather  '<json>'   获取指定雪场的专业高山天气预报
  compare  '<json>'   多雪场综合对比（天气+票价+交通+住宿）
  costs    '<json>'   估算前往某雪场的交通+住宿费用
  update-db           从 GitHub 拉取最新雪场数据库

数据存储：通过 utils.py 统一管理，默认 ~/.ski-assistant/
天气数据来源：Open-Meteo API（专业高山天气，按雪场海拔获取）
雪场数据库：scripts/resorts_db.json（内置） + ~/.ski-assistant/custom_resorts.json（用户自定义）
"""

import json
import os
import sys
import urllib.request
import urllib.parse
from datetime import datetime

# ─── 导入共享工具 ───
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SCRIPT_DIR)
from utils import (
    DATA_DIR, PROFILE_PATH, CST,
    ensure_dir, load_json, save_json,
    level_label, sport_label, haversine, load_resorts_db,
    CITY_COORDS,
)

# ─── WMO 天气代码映射 ───

WMO_CODES = {
    0: "晴", 1: "基本晴朗", 2: "多云", 3: "阴天",
    45: "雾", 48: "雾凇", 51: "小毛毛雨", 53: "毛毛雨", 55: "大毛毛雨",
    61: "小雨", 63: "中雨", 65: "大雨",
    66: "冻雨（小）", 67: "冻雨（大）",
    71: "小雪", 73: "中雪", 75: "大雪", 77: "米雪",
    80: "小阵雨", 81: "中阵雨", 82: "大阵雨",
    85: "小阵雪", 86: "大阵雪",
    95: "雷暴", 96: "雷暴+冰雹（小）", 99: "雷暴+冰雹（大）",
}

# ─── 工具函数 ───

def _load_profile() -> dict:
    return load_json(PROFILE_PATH, {})

def _save_profile(p: dict):
    save_json(PROFILE_PATH, p)

def _fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "ski-assistant/2.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))

def _transport_field(resort: dict) -> dict:
    """兼容旧版 transport_from_beijing 和新版 transport_ref"""
    return resort.get("transport_ref") or resort.get("transport_from_beijing") or {}


# ─── 高山天气 API ───

def fetch_mountain_weather(lat: float, lon: float, elevation: int, days: int = 7) -> dict:
    """
    从 Open-Meteo 获取专业高山天气预报。
    按指定海拔高度获取数据，包含降雪、雪深、风速、能见度等关键指标。
    """
    params = {
        "latitude": lat, "longitude": lon, "elevation": elevation,
        "hourly": "temperature_2m,apparent_temperature,snowfall,snow_depth,rain,windspeed_10m,windgusts_10m,cloudcover,visibility,weathercode",
        "daily": "weathercode,temperature_2m_max,temperature_2m_min,apparent_temperature_max,apparent_temperature_min,snowfall_sum,rain_sum,windspeed_10m_max,windgusts_10m_max",
        "timezone": "auto",
        "forecast_days": min(days, 16),
    }
    url = "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(params)
    data = _fetch_json(url)

    daily = data.get("daily", {})
    dates = daily.get("time", [])
    result = {
        "elevation_m": elevation,
        "lat": lat, "lon": lon,
        "timezone": data.get("timezone", ""),
        "forecast_days": len(dates),
        "daily": [],
    }

    for i, date in enumerate(dates):
        wcode = daily.get("weathercode", [None])[i]
        day = {
            "date": date,
            "weather": WMO_CODES.get(wcode, f"代码{wcode}"),
            "weather_code": wcode,
            "temp_max": daily.get("temperature_2m_max", [None])[i],
            "temp_min": daily.get("temperature_2m_min", [None])[i],
            "feels_like_max": daily.get("apparent_temperature_max", [None])[i],
            "feels_like_min": daily.get("apparent_temperature_min", [None])[i],
            "snowfall_cm": daily.get("snowfall_sum", [0])[i],
            "rain_mm": daily.get("rain_sum", [0])[i],
            "wind_max_kmh": daily.get("windspeed_10m_max", [None])[i],
            "gust_max_kmh": daily.get("windgusts_10m_max", [None])[i],
        }
        # 滑雪条件评分 (1-10)
        score = 10
        if day["temp_max"] is not None:
            if day["temp_max"] > 10: score -= 4       # 山顶超10°C，雪面融化严重
            elif day["temp_max"] > 5: score -= 2      # 偏暖，雪质变差
            if day["temp_min"] is not None and day["temp_min"] < -25: score -= 1
        if day["wind_max_kmh"] is not None:
            if day["wind_max_kmh"] > 50: score -= 4    # 持续风速>50km/h，缆车可能停运
            elif day["wind_max_kmh"] > 35: score -= 2  # 强风，体感差、影响平衡
        if day["gust_max_kmh"] is not None:
            if day["gust_max_kmh"] > 70: score -= 2    # 阵风>70km/h，极端危险
            elif day["gust_max_kmh"] > 55: score -= 1  # 阵风强，阵性影响体验
        if day["snowfall_cm"] and day["snowfall_cm"] > 5: score += 2
        if day["rain_mm"] and day["rain_mm"] > 0:     # 降雨分级惩罚
            if day["rain_mm"] > 5: score -= 4         # 大雨
            elif day["rain_mm"] > 2: score -= 3       # 中雨
            else: score -= 2                          # 小雨也严重影响体验
        if wcode in (71, 73, 85): score += 1
        day["ski_condition_score"] = max(1, min(10, score))

        ski_labels = {(1, 3): "差", (4, 5): "一般", (6, 7): "良好", (8, 9): "优秀", (10, 10): "完美"}
        for (lo, hi), label in ski_labels.items():
            if lo <= day["ski_condition_score"] <= hi:
                day["ski_condition_label"] = label
                break

        result["daily"].append(day)

    # 7天总结
    snow_total = sum(d.get("snowfall_cm", 0) or 0 for d in result["daily"])
    avg_temp = sum((d.get("temp_max", 0) or 0) + (d.get("temp_min", 0) or 0) for d in result["daily"]) / (2 * max(len(result["daily"]), 1))
    avg_score = sum(d.get("ski_condition_score", 5) for d in result["daily"]) / max(len(result["daily"]), 1)
    result["summary"] = {
        "total_snowfall_cm": round(snow_total, 1),
        "avg_temperature": round(avg_temp, 1),
        "avg_ski_score": round(avg_score, 1),
        "best_days": sorted(result["daily"], key=lambda d: -d.get("ski_condition_score", 0))[:3],
    }
    return result


# ─── 核心命令 ───

def set_profile(params: dict) -> str:
    """设置用户画像。"""
    profile = _load_profile()
    profile.update(params)
    profile["updated_at"] = datetime.now(CST).isoformat()
    _save_profile(profile)

    lines = ["🎿 用户画像已更新\n"]
    if params.get("city"):
        lines.append(f"📍 出发城市：{params['city']}")
        if params["city"] not in CITY_COORDS:
            lines.append(f"  ⚠️ 「{params['city']}」不在内置城市坐标库中，距离计算和交通推荐可能不准确。")
            lines.append(f"  💡 支持的城市：{'、'.join(list(CITY_COORDS.keys())[:10])} 等 {len(CITY_COORDS)} 个城市")
    if params.get("level"): lines.append(f"🏔️ 滑雪水平：{level_label(params['level'])}")
    if params.get("sport_type"):
        lines.append(f"🎿 运动类型：{sport_label(params['sport_type'])}")
    if params.get("preferences"): lines.append(f"❤️ 偏好：{'、'.join(params['preferences'])}")
    if params.get("budget_per_trip_cny"): lines.append(f"💰 预算：¥{params['budget_per_trip_cny']}/次")
    if params.get("available_days"): lines.append(f"📅 可用天数：{params['available_days']}天")
    if params.get("travel_dates"): lines.append(f"📅 出行时间：{params['travel_dates']}")
    return "\n".join(lines)


def show_profile() -> str:
    profile = _load_profile()
    if not profile:
        return "🎿 尚未设置用户画像。请先告诉我你的出发城市、滑雪水平和偏好。"

    lines = ["🎿 当前用户画像\n"]
    fields = [
        ("city", "📍 出发城市"), ("level", "🏔️ 滑雪水平"),
        ("sport_type", "🎿 运动类型"), ("preferences", "❤️ 偏好"),
        ("budget_per_trip_cny", "💰 预算"), ("available_days", "📅 可用天数"),
        ("travel_dates", "📅 出行时间"), ("companions", "👥 同行"),
        ("region_preference", "🌍 地区偏好"), ("must_have", "✅ 必须有"),
        ("avoid", "❌ 避免"),
    ]
    for key, label in fields:
        val = profile.get(key)
        if val:
            if key == "level": val = level_label(val)
            elif key == "sport_type": val = sport_label(val)
            elif isinstance(val, list): val = "、".join(val)
            elif key == "budget_per_trip_cny": val = f"¥{val}"
            elif key == "available_days": val = f"{val}天"
            lines.append(f"{label}：{val}")
    return "\n".join(lines)


def recommend(params: dict = None) -> str:
    """
    基于用户画像推荐雪场。可选参数覆盖画像字段。
    额外参数: {"top_n": 3, "include_weather": true, "indoor_only": false}
    """
    resorts_db = load_resorts_db()
    profile = _load_profile()
    if params:
        profile.update(params)

    city = profile.get("city", "北京")
    level = profile.get("level", "intermediate")
    sport_type = profile.get("sport_type", "ski")
    preferences = set(profile.get("preferences", []))
    budget = profile.get("budget_per_trip_cny", 999999)
    available_days = profile.get("available_days", 5)
    region_pref = profile.get("region_preference", "不限")
    must_have = set(profile.get("must_have", []))
    avoid = set(profile.get("avoid", []))
    top_n = (params or {}).get("top_n", 3)
    include_weather = (params or {}).get("include_weather", False)
    indoor_only = (params or {}).get("indoor_only", False)

    city_coord = CITY_COORDS.get(city)

    # 判断是否为非雪季（北半球 4-10 月视为非雪季）
    # 优先使用用户的出行日期，否则用当前月份
    travel_dates = profile.get("travel_dates", "")
    if travel_dates:
        try:
            travel_month = int(travel_dates.split("-")[1]) if "-" in travel_dates else datetime.now(CST).month
        except (ValueError, IndexError):
            travel_month = datetime.now(CST).month
    else:
        travel_month = datetime.now(CST).month
    off_season = 4 <= travel_month <= 10

    scored = []
    for name, r in resorts_db.items():
        if name == "_meta":
            continue
        is_indoor = r.get("indoor", False)

        # 室内/室外过滤
        if indoor_only and not is_indoor:
            continue

        # 基础过滤
        if level not in r.get("suited_for", []): continue
        if region_pref != "不限":
            # 同时匹配 region 和 province 字段（如 "新疆" 匹配 province "新疆·阿勒泰"）
            region_match = region_pref in r.get("region", "") or region_pref in r.get("province", "") or region_pref in r.get("country", "")
            if not region_match: continue
        if sport_type == "snowboard" and not r.get("board_friendly"): continue
        if must_have:
            resort_features = set(r.get("features", []))
            if "公园" in must_have or "park" in must_have:
                if not r.get("park"): continue
            if "夜滑" in must_have and "夜滑" not in resort_features: continue

        # 评分（满分 100，封顶 100）
        score = 50  # 基础分

        # 偏好匹配 (每个 +8, 封顶 +32)
        resort_features = set(r.get("features", []))
        matched_prefs = preferences & resort_features
        score += min(len(matched_prefs) * 8, 32)

        # 交通便利性（距离）
        transport = _transport_field(r)
        if city_coord:
            dist = haversine(city_coord[0], city_coord[1], r["lat"], r["lon"])
            if dist < 300: score += 15
            elif dist < 800: score += 8
            elif dist < 2000: score += 3

            # 时间匹配
            hours = transport.get("hours", 10)
            if available_days <= 3 and hours > 6: score -= 10
            if available_days >= 5 and hours > 6: score += 3

            # 室内雪场：同城大幅加分
            if is_indoor and dist < 100: score += 12
        else:
            dist = None

        # 预算匹配
        ticket_avg = sum(r.get("ticket_range_cny", [0, 0])) / 2
        hotel_avg = sum(r.get("hotel_range_cny", [0, 0])) / 2
        transport_cost_avg = sum(transport.get("cost_cny", [0, 0])) / 2
        if is_indoor and city_coord and dist and dist < 200:
            est_total = ticket_avg * min(available_days, 2) + transport_cost_avg
        else:
            est_total = ticket_avg * min(available_days, 3) + hotel_avg * (available_days - 1) + transport_cost_avg
        if est_total <= budget: score += 12
        elif est_total <= budget * 1.3: score += 4
        else: score -= 8

        # 雪场规模和落差加分（室内用面积，室外用落差+面积）
        if is_indoor:
            indoor_sqm = r.get("indoor_area_sqm", 0)
            score += min(indoor_sqm / 15000, 5)
        else:
            score += min(r.get("vertical_drop", 0) / 150, 6)
            score += min(r.get("area_km2", 0) / 2, 5)

        # 公园偏好
        if sport_type == "snowboard" and r.get("park"): score += 8

        # 非雪季：室内雪场加分，室外雪场如不在雪季则大幅扣分
        if off_season:
            if is_indoor:
                score += 15
            else:
                season_str = r.get("season", "")
                # 南半球(6-10月)在北半球非雪季时正当季
                is_southern = r.get("country", "") in ("新西兰", "澳大利亚") or "南半球" in r.get("region", "")
                if is_southern:
                    score += 10  # 反季加分
                elif "全年" not in season_str:
                    score -= 30  # 已过季大幅扣分

        # 避免项扣分
        for a in avoid:
            if a in resort_features: score -= 12

        # 最终封顶 0-100
        score = max(0, min(100, score))

        scored.append({
            "name": name, "score": round(score, 1), "resort": r,
            "distance_km": round(dist) if dist else None,
            "est_total_cny": round(est_total),
            "matched_preferences": list(matched_prefs),
        })

    scored.sort(key=lambda x: -x["score"])
    top = scored[:top_n]

    if not top:
        return "😅 未找到匹配的雪场，请调整筛选条件（放宽地区、预算或水平要求）。"

    lines = [f"🎿 为你推荐的雪场（基于{city}出发、{level_label(level)}水平）\n"]

    for i, item in enumerate(top, 1):
        r = item["resort"]
        name = item["name"]
        is_indoor = r.get("indoor", False)
        transport = _transport_field(r)

        lines.append(f"### {'🥇' if i == 1 else '🥈' if i == 2 else '🥉'} 推荐 {i}：{name}{'  🏢 室内' if is_indoor else ''}\n")

        if is_indoor:
            lines.append(f"📍 {r['province']}  |  室内面积 {r.get('indoor_area_sqm', '?')}m²  |  恒温 {r.get('indoor_temp', -5)}°C")
            lines.append(f"🏔️ 最长雪道 {r.get('max_slope_length_m', '?')}m  |  落差 {r['vertical_drop']}m")
        else:
            lines.append(f"📍 {r['province']}  |  海拔 {r.get('elevation_base', '?')}-{r.get('elevation_top', '?')}m  |  落差 {r['vertical_drop']}m")

        # 雪道信息
        trails = r.get("trails", {})
        trail_str = f"绿道{trails.get('green', 0)} · 蓝道{trails.get('blue', 0)} · 黑道{trails.get('black', 0)} · 双黑{trails.get('double_black', 0)}"
        total_trails = sum(trails.values())
        if is_indoor:
            lines.append(f"🏔️ {trail_str}（共{total_trails}条）")
        else:
            lines.append(f"🏔️ {trail_str}（共{total_trails}条）  |  面积 {r.get('area_km2', '?')}km²")

        # 特色
        lines.append(f"✨ 特色：{'、'.join(r.get('features', []))}")

        # 匹配的偏好
        if item["matched_preferences"]:
            lines.append(f"❤️ 匹配偏好：{'、'.join(item['matched_preferences'])}")

        # 雪季状态警告
        if not is_indoor and off_season:
            season_str = r.get("season", "")
            is_southern = r.get("country", "") in ("新西兰", "澳大利亚") or "南半球" in r.get("region", "")
            if is_southern:
                lines.append(f"🌏 反季雪场，雪季 {season_str}")
            elif "全年" not in season_str:
                lines.append(f"⚠️ 当前非雪季（雪季 {season_str}），雪场可能已关闭")

        # 费用估算（显示用户出发城市，不再固定显示北京）
        lines.append(f"\n💰 **费用估算**")
        lines.append(f"  · 雪票：¥{r['ticket_range_cny'][0]}-{r['ticket_range_cny'][1]}/天")
        ref_city = transport.get("from", "参考城市")
        lines.append(f"  · 交通：{transport.get('method', '?')}  约{transport.get('hours', '?')}小时  ¥{transport.get('cost_cny', [0,0])[0]}-{transport.get('cost_cny', [0,0])[1]}/人（参考自{ref_city}）")
        lines.append(f"  · 住宿：¥{r['hotel_range_cny'][0]}-{r['hotel_range_cny'][1]}/晚")
        lines.append(f"  · 预估总费用：约 ¥{item['est_total_cny']}/人（{available_days}天）")

        # 天气
        if include_weather:
            if is_indoor:
                lines.append(f"\n🌡️ **室内恒温环境**：{r.get('indoor_temp', -5)}°C，全年可滑，不受天气影响")
            else:
                try:
                    wx = fetch_mountain_weather(r["lat"], r["lon"], r["elevation_top"], days=7)
                    lines.append(f"\n🌨️ **7天高山天气预报**（海拔 {r['elevation_top']}m）")
                    lines.append(f"  · 未来7天降雪总量：{wx['summary']['total_snowfall_cm']}cm")
                    lines.append(f"  · 平均气温：{wx['summary']['avg_temperature']}°C")
                    lines.append(f"  · 平均滑雪指数：{wx['summary']['avg_ski_score']}/10")
                    lines.append("  | 日期 | 天气 | 温度 | 体感 | 降雪 | 风速 | 滑雪指数 |")
                    lines.append("  |------|------|------|------|------|------|----------|")
                    for d in wx["daily"][:5]:
                        temp = f"{d['temp_min']}~{d['temp_max']}°C"
                        feels = f"{d['feels_like_min']}~{d['feels_like_max']}°C"
                        snow = f"{d['snowfall_cm']}cm" if d['snowfall_cm'] else "-"
                        wind = f"{d['wind_max_kmh']}km/h"
                        ski = f"{d['ski_condition_score']}/10 {d['ski_condition_label']}"
                        lines.append(f"  | {d['date']} | {d['weather']} | {temp} | {feels} | {snow} | {wind} | {ski} |")
                except Exception as e:
                    lines.append(f"\n⚠️ 天气数据获取失败：{e}")

        lines.append(f"\n🏂 单板友好：{'✅' if r.get('board_friendly') else '❌'}  |  公园/地形：{'✅' if r.get('park') else '❌'}")
        lines.append(f"📅 雪季：{r.get('season', '?')}")
        lines.append(f"📊 推荐匹配度：{item['score']}/100\n")

    lines.append("---")
    lines.append("💡 可以说「对比这几个雪场的天气」或「帮我做 XX 的攻略」继续深入。")

    # JSON for programmatic use
    lines.append("\n<!-- RECOMMEND_JSON -->")
    lines.append(json.dumps([{"name": t["name"], "score": t["score"], "est_total": t["est_total_cny"]} for t in top], ensure_ascii=False))

    return "\n".join(lines)


def get_weather(params: dict) -> str:
    """
    获取指定雪场的专业高山天气。
    参数: {"resort": "万龙滑雪场", "days": 7}
    或: {"lat": 40.93, "lon": 115.44, "elevation": 2110, "days": 7, "name": "万龙"}
    """
    resorts_db = load_resorts_db()
    resort_name = params.get("resort", "")
    days = params.get("days", 7)

    if resort_name and resort_name in resorts_db:
        r = resorts_db[resort_name]
        if r.get("indoor"):
            lines = [f"🌡️ {resort_name} - 室内雪场\n"]
            lines.append(f"📍 {r.get('province', '')}  |  室内面积 {r.get('indoor_area_sqm', '?')}m²")
            lines.append(f"🌡️ 恒温 {r.get('indoor_temp', -5)}°C，全年可滑，不受天气影响")
            lines.append(f"🏔️ 最长雪道 {r.get('max_slope_length_m', '?')}m  |  落差 {r['vertical_drop']}m")
            lines.append(f"\n📌 室内雪场无需关注外部天气，任何季节都可前往。")
            return "\n".join(lines)
        lat, lon, elev = r["lat"], r["lon"], r["elevation_top"]
    else:
        lat = params.get("lat")
        lon = params.get("lon")
        elev = params.get("elevation", 2000)
        resort_name = params.get("name", f"({lat},{lon})")

    if not lat or not lon:
        return "⚠️ 请提供雪场名称或经纬度坐标。"

    try:
        wx = fetch_mountain_weather(lat, lon, elev, days)
    except Exception as e:
        return f"⚠️ 天气数据获取失败：{e}\n\n请稍后重试，或检查网络连接。"

    lines = [f"🌨️ {resort_name} 高山天气预报\n"]
    lines.append(f"📍 海拔 {elev}m  |  坐标 ({lat}, {lon})")

    # 雪场运营状态提示
    if resort_name in resorts_db:
        r = resorts_db[resort_name]
        season_str = r.get("season", "")
        if season_str and not r.get("indoor"):
            import re
            from datetime import datetime as _dt
            now_month = _dt.now().month
            # 提取所有月份数字
            month_nums = [int(x) for x in re.findall(r'(\d{1,2})月', season_str)]
            if len(month_nums) >= 2:
                start_m, end_m = month_nums[0], month_nums[-1]
                if start_m > end_m:  # 跨年（如11月-4月）
                    _season_months = list(range(start_m, 13)) + list(range(1, end_m + 1))
                else:  # 同年（如6月-10月）
                    _season_months = list(range(start_m, end_m + 1))
            elif r.get("lat", 0) < 0:
                _season_months = [6, 7, 8, 9, 10]
            else:
                _season_months = [11, 12, 1, 2, 3, 4]

            if now_month not in _season_months:
                lines.append(f"⚠️ **该雪场当前不在运营期**（雪季：{season_str}），天气数据仅供参考。")

    lines.append(f"📅 未来 {wx['forecast_days']} 天预报\n")

    lines.append("| 日期 | 天气 | 温度范围 | 体感温度 | 降雪 | 降雨 | 最大风速 | 阵风 | 滑雪指数 |")
    lines.append("|------|------|----------|---------|------|------|---------|------|---------|")

    for d in wx["daily"]:
        temp = f"{d['temp_min']}~{d['temp_max']}°C"
        feels = f"{d['feels_like_min']}~{d['feels_like_max']}°C"
        snow = f"{d['snowfall_cm']}cm" if d['snowfall_cm'] else "-"
        rain = f"{d['rain_mm']}mm" if d['rain_mm'] else "-"
        wind = f"{d['wind_max_kmh']}km/h" if d['wind_max_kmh'] else "-"
        gust = f"{d['gust_max_kmh']}km/h" if d['gust_max_kmh'] else "-"
        ski = f"{d['ski_condition_score']}/10 {d['ski_condition_label']}"
        lines.append(f"| {d['date']} | {d['weather']} | {temp} | {feels} | {snow} | {rain} | {wind} | {gust} | {ski} |")

    s = wx["summary"]
    lines.append(f"\n📊 **总结**")
    lines.append(f"  · 未来{wx['forecast_days']}天累计降雪：{s['total_snowfall_cm']}cm")
    lines.append(f"  · 平均气温：{s['avg_temperature']}°C")
    lines.append(f"  · 平均滑雪指数：{s['avg_ski_score']}/10")

    best = s.get("best_days", [])
    if best:
        lines.append(f"  · 最佳滑雪日：{best[0]['date']}（{best[0]['weather']}，指数 {best[0]['ski_condition_score']}/10）")

    lines.append("\n<!-- WEATHER_JSON -->")
    lines.append(json.dumps(wx, ensure_ascii=False))

    return "\n".join(lines)


def compare_resorts(params: dict) -> str:
    """
    多雪场综合对比。
    参数: {"resorts": ["万龙滑雪场", "北大湖滑雪场", "太舞滑雪小镇"], "include_weather": true}
    """
    resorts_db = load_resorts_db()
    names = params.get("resorts", [])
    include_weather = params.get("include_weather", True)
    profile = _load_profile()
    city = profile.get("city", "北京")
    days = profile.get("available_days", 4)

    if len(names) < 2:
        return "⚠️ 请提供至少 2 个雪场名称进行对比。"

    lines = [f"🏔️ 雪场综合对比\n"]

    # Header
    header = ["指标"] + names
    lines.append("| " + " | ".join(header) + " |")
    lines.append("| " + " | ".join(["---"] * len(header)) + " |")

    # 基础数据行
    rows = [
        ("类型", lambda n, r: "🏢 室内" if r.get("indoor") else "⛰️ 室外"),
        ("地区", lambda n, r: r.get("province", "")),
        ("海拔/规模", lambda n, r: f"室内 {r.get('indoor_area_sqm', '?')}m²" if r.get("indoor") else f"{r.get('elevation_base', '?')}-{r.get('elevation_top', '?')}m"),
        ("落差", lambda n, r: f"{r['vertical_drop']}m"),
        ("面积", lambda n, r: f"{r.get('indoor_area_sqm', '?')}m²" if r.get("indoor") else f"{r.get('area_km2', '?')}km²"),
        ("雪道总数", lambda n, r: str(sum(r.get("trails", {}).values()))),
        ("雪季", lambda n, r: r.get("season", "?")),
        ("特色", lambda n, r: "、".join(r.get("features", [])[:3])),
        ("单板友好", lambda n, r: "✅" if r.get("board_friendly") else "❌"),
        ("公园/地形", lambda n, r: "✅" if r.get("park") else "❌"),
        ("雪票价格", lambda n, r: f"¥{r['ticket_range_cny'][0]}-{r['ticket_range_cny'][1]}/天"),
        ("住宿价格", lambda n, r: f"¥{r['hotel_range_cny'][0]}-{r['hotel_range_cny'][1]}/晚"),
    ]

    # 交通行（显示参考城市）
    def _transport_method(n, r):
        t = _transport_field(r)
        ref = t.get("from", "")
        return f"{t.get('method', '?')}（自{ref}）" if ref else t.get("method", "?")

    def _transport_hours(n, r):
        t = _transport_field(r)
        return f"约{t.get('hours', '?')}小时"

    def _transport_cost(n, r):
        t = _transport_field(r)
        costs = t.get("cost_cny", [0, 0])
        return f"¥{costs[0]}-{costs[1]}/人"

    rows.extend([
        ("交通方式", _transport_method),
        ("交通耗时", _transport_hours),
        ("交通费用", _transport_cost),
    ])

    for label, fn in rows:
        vals = []
        for name in names:
            r = resorts_db.get(name, {})
            vals.append(fn(name, r) if r else "N/A")
        lines.append("| " + label + " | " + " | ".join(vals) + " |")

    # 预估总费用（修复表格格式 bug）
    est_vals = []
    for name in names:
        r = resorts_db.get(name, {})
        if r:
            ticket_avg = sum(r.get("ticket_range_cny", [0, 0])) / 2
            hotel_avg = sum(r.get("hotel_range_cny", [0, 0])) / 2
            transport = _transport_field(r)
            transport_avg = sum(transport.get("cost_cny", [0, 0])) / 2
            total = ticket_avg * min(days, 3) + hotel_avg * (days - 1) + transport_avg
            est_vals.append(f"约¥{round(total)}/人")
        else:
            est_vals.append("N/A")
    lines.append("| 预估总费用 | " + " | ".join(est_vals) + " |")

    # 天气对比
    if include_weather:
        lines.append(f"\n### 🌨️ 高山天气对比（未来7天）\n")
        wx_header = ["指标"] + names
        lines.append("| " + " | ".join(wx_header) + " |")
        lines.append("| " + " | ".join(["---"] * len(wx_header)) + " |")

        weather_data = {}
        weather_errors = {}
        for name in names:
            r = resorts_db.get(name)
            if r and not r.get("indoor"):
                try:
                    weather_data[name] = fetch_mountain_weather(r["lat"], r["lon"], r["elevation_top"], 7)
                except Exception as e:
                    weather_data[name] = None
                    weather_errors[name] = str(e)[:80]

        wx_rows = [
            ("监测海拔", lambda n: "室内恒温" if resorts_db.get(n, {}).get("indoor") else f"{resorts_db.get(n, {}).get('elevation_top', '?')}m"),
            ("7天累计降雪", lambda n: "N/A（室内）" if resorts_db.get(n, {}).get("indoor") else (f"{weather_data.get(n, {}).get('summary', {}).get('total_snowfall_cm', '?')}cm" if weather_data.get(n) else "N/A")),
            ("平均气温", lambda n: f"{resorts_db.get(n, {}).get('indoor_temp', -5)}°C（恒温）" if resorts_db.get(n, {}).get("indoor") else (f"{weather_data.get(n, {}).get('summary', {}).get('avg_temperature', '?')}°C" if weather_data.get(n) else "N/A")),
            ("平均滑雪指数", lambda n: "全年可滑" if resorts_db.get(n, {}).get("indoor") else (f"{weather_data.get(n, {}).get('summary', {}).get('avg_ski_score', '?')}/10" if weather_data.get(n) else "N/A")),
        ]

        for label, fn in wx_rows:
            vals = [fn(name) for name in names]
            lines.append("| " + label + " | " + " | ".join(vals) + " |")

        if weather_errors:
            lines.append(f"\n⚠️ 天气数据获取失败：")
            for n, err in weather_errors.items():
                lines.append(f"  · {n}：{err}")

    return "\n".join(lines)


def estimate_costs(params: dict) -> str:
    """
    估算费用（增强版，合并了 budget_calculator 的详细功能）。
    参数: {"resort": "万龙滑雪场", "days": 4, "people": 2, "from_city": "北京",
           "rental_per_day": 200, "extras_per_person": 100}
    """
    resorts_db = load_resorts_db()
    name = params.get("resort", "")
    r = resorts_db.get(name)
    if not r:
        return f"⚠️ 未找到雪场「{name}」，请检查名称。可用雪场：{', '.join(k for k in resorts_db if k != '_meta')}"

    days = params.get("days", 4)
    people = params.get("people", 1)
    ski_days = min(days, params.get("ski_days", days - 1))
    from_city = params.get("from_city", "")

    ticket_lo = r["ticket_range_cny"][0] * ski_days * people
    ticket_hi = r["ticket_range_cny"][1] * ski_days * people
    hotel_lo = r["hotel_range_cny"][0] * (days - 1)
    hotel_hi = r["hotel_range_cny"][1] * (days - 1)

    transport = _transport_field(r)
    transport_lo = transport.get("cost_cny", [0, 0])[0] * people
    transport_hi = transport.get("cost_cny", [0, 0])[1] * people
    transport_ref_city = transport.get("from", "参考城市")

    # 可选：装备租赁
    rental_per_day = params.get("rental_per_day", 0)
    rental_total = rental_per_day * ski_days * people

    # 餐饮
    food = 150 * days * people

    # 保险
    insurance = 50 * people

    # 其他费用
    extras = params.get("extras_per_person", 0) * people

    total_lo = ticket_lo + hotel_lo + transport_lo + rental_total + food + insurance + extras
    total_hi = ticket_hi + hotel_hi + transport_hi + rental_total + food + insurance + extras

    lines = [f"💰 {name} 费用估算（{people}人{days}天，滑{ski_days}天）\n"]

    if from_city and from_city != transport_ref_city:
        lines.append(f"📌 注意：交通费用为自{transport_ref_city}的参考价，从{from_city}出发请自行调整。\n")

    lines.append("| 项目 | 低预算 | 高预算 | 人均（低） | 人均（高） |")
    lines.append("|------|--------|--------|----------|----------|")
    items = [
        ("雪票", ticket_lo, ticket_hi),
        ("住宿", hotel_lo, hotel_hi),
        (f"交通（参考自{transport_ref_city}）", transport_lo, transport_hi),
    ]
    if rental_total > 0:
        items.append(("装备租赁", rental_total, rental_total))
    items.extend([
        ("餐饮", food, food),
        ("保险", insurance, insurance),
    ])
    if extras > 0:
        items.append(("其他", extras, extras))

    for label, lo, hi in items:
        lines.append(f"| {label} | ¥{lo} | ¥{hi} | ¥{lo // people} | ¥{hi // people} |")
    lines.append(f"| **合计** | **¥{total_lo}** | **¥{total_hi}** | **¥{total_lo // people}** | **¥{total_hi // people}** |")

    return "\n".join(lines)


# ─── 数据库更新 ───

_GITHUB_RAW_URL = "https://raw.githubusercontent.com/wjyhahaha/ski-assistant/main/scripts/resorts_db.json"

def update_db() -> str:
    """从 GitHub 拉取最新 resorts_db.json 并覆盖本地内置数据库。"""
    import shutil
    local_path = os.path.join(_SCRIPT_DIR, "resorts_db.json")

    # 备份当前文件
    backup_path = local_path + ".bak"
    if os.path.exists(local_path):
        shutil.copy2(local_path, backup_path)

    try:
        data = _fetch_json(_GITHUB_RAW_URL)
    except Exception as e:
        return f"❌ 拉取失败：{e}\n\n本地数据库未受影响。"

    if not isinstance(data, dict) or "_meta" not in data:
        return "❌ 远程文件格式异常（缺少 _meta 字段），已跳过更新。"

    # 对比版本
    try:
        with open(local_path, "r", encoding="utf-8") as f:
            local_data = json.load(f)
        local_ver = local_data.get("_meta", {}).get("version", "0.0.0")
        local_updated = local_data.get("_meta", {}).get("updated", "")
        local_count = sum(1 for k, v in local_data.items() if k != "_meta" and isinstance(v, dict) and "lat" in v)
    except Exception:
        local_ver, local_updated, local_count = "0.0.0", "", 0

    remote_ver = data.get("_meta", {}).get("version", "0.0.0")
    remote_updated = data.get("_meta", {}).get("updated", "")
    remote_count = sum(1 for k, v in data.items() if k != "_meta" and isinstance(v, dict) and "lat" in v)

    # 写入
    with open(local_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    lines = ["🔄 雪场数据库已更新\n"]
    if local_ver != remote_ver:
        lines.append(f"版本：{local_ver} → {remote_ver}")
    else:
        lines.append(f"版本：{remote_ver}（与本地一致）")
    lines.append(f"日期：{local_updated or '未知'} → {remote_updated}")
    lines.append(f"雪场数量：{local_count} → {remote_count}")

    new_resorts = set(k for k, v in data.items() if k != "_meta" and isinstance(v, dict) and "lat" in v)
    old_resorts = set(k for k, v in local_data.items() if k != "_meta" and isinstance(v, dict) and "lat" in v) if local_count > 0 else set()
    added = new_resorts - old_resorts
    removed = old_resorts - new_resorts
    if added:
        lines.append(f"新增雪场：{', '.join(sorted(added))}")
    if removed:
        lines.append(f"移除雪场：{', '.join(sorted(removed))}")

    lines.append(f"\n备份：{backup_path}")
    return "\n".join(lines)


# ─── 主入口 ───

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "profile":
        params = json.loads(sys.argv[2]) if len(sys.argv) > 2 else json.load(sys.stdin)
        print(set_profile(params))
    elif cmd == "show-profile":
        print(show_profile())
    elif cmd == "recommend":
        params = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
        print(recommend(params))
    elif cmd == "weather":
        params = json.loads(sys.argv[2]) if len(sys.argv) > 2 else json.load(sys.stdin)
        print(get_weather(params))
    elif cmd == "compare":
        params = json.loads(sys.argv[2]) if len(sys.argv) > 2 else json.load(sys.stdin)
        print(compare_resorts(params))
    elif cmd == "costs":
        params = json.loads(sys.argv[2]) if len(sys.argv) > 2 else json.load(sys.stdin)
        print(estimate_costs(params))
    elif cmd == "update-db":
        print(update_db())
    else:
        print(f"未知命令: {cmd}")
        print(__doc__)
        sys.exit(1)
