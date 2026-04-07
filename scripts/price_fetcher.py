#!/usr/bin/env python3
"""
联网查价模块 — 实时获取机票、酒店、雪票价格

用法:
  python scripts/price_fetcher.py search-queries '<json>'   生成搜索策略（供 Agent WebSearch）
  python scripts/price_fetcher.py parse-results  '<json>'   解析搜索结果，生成结构化报价
  python scripts/price_fetcher.py live-costs      '<json>'   一步到位：返回搜索策略 + 预算模板

设计理念：
  脚本负责 "搜什么 + 怎么算"，Agent 负责 "怎么搜"。
  这样不依赖任何第三方 API Key，任何 Agent 平台都能用。

工作流：
  1. Agent 调用 search-queries → 拿到各品类的搜索关键词 + OTA 直达链接
  2. Agent 用自身 WebSearch 能力搜索，收集价格信息
  3. Agent 调用 parse-results → 传入搜索到的价格数据 → 拿到结构化预算报告

数据存储：搜索结果缓存在数据目录下的 price_cache.json，有效期 24 小时。
"""

import json
import os
import sys
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Tuple

# ─── 导入共享工具 ───
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SCRIPT_DIR)
from utils import (
    DATA_DIR, CST, ensure_dir, load_json, save_json,
    load_resorts_db, haversine, CITY_COORDS,
)

_CACHE_PATH = os.path.join(DATA_DIR, "price_cache.json")
_CACHE_TTL_HOURS = 24


# ─── 缓存管理 ───

def _cache_key(params: dict) -> str:
    """生成缓存键"""
    key_str = json.dumps(params, sort_keys=True, ensure_ascii=False)
    return hashlib.md5(key_str.encode()).hexdigest()[:12]


def _get_cached(key: str) -> Optional[dict]:
    """获取缓存，过期返回 None"""
    cache = load_json(_CACHE_PATH, {})
    entry = cache.get(key)
    if not entry:
        return None
    cached_at = datetime.fromisoformat(entry.get("cached_at", "2000-01-01"))
    if datetime.now(CST) - cached_at > timedelta(hours=_CACHE_TTL_HOURS):
        return None
    return entry.get("data")


def _set_cache(key: str, data: dict):
    """写入缓存"""
    cache = load_json(_CACHE_PATH, {})
    cache[key] = {
        "cached_at": datetime.now(CST).isoformat(),
        "data": data,
    }
    # 清理过期条目（保留最近 50 条）
    if len(cache) > 50:
        items = sorted(cache.items(), key=lambda x: x[1].get("cached_at", ""), reverse=True)
        cache = dict(items[:50])
    save_json(_CACHE_PATH, cache)


# ─── 机场/火车站映射 ───

# 城市 → 机场代码/火车站（用于生成更精准的搜索词）
_AIRPORT_CODES = {
    "北京": {"airport": "PEK/PKX", "airports": ["首都T2/T3", "大兴"], "train_station": "北京西站/北京北站"},
    "上海": {"airport": "PVG/SHA", "airports": ["浦东", "虹桥"], "train_station": "上海虹桥站"},
    "广州": {"airport": "CAN", "airports": ["白云"], "train_station": "广州南站"},
    "深圳": {"airport": "SZX", "airports": ["宝安"], "train_station": "深圳北站"},
    "成都": {"airport": "TFU/CTU", "airports": ["天府", "双流"], "train_station": "成都东站"},
    "杭州": {"airport": "HGH", "airports": ["萧山"], "train_station": "杭州东站"},
    "南京": {"airport": "NKG", "airports": ["禄口"], "train_station": "南京南站"},
    "武汉": {"airport": "WUH", "airports": ["天河"], "train_station": "武汉站"},
    "西安": {"airport": "XIY", "airports": ["咸阳"], "train_station": "西安北站"},
    "重庆": {"airport": "CKG", "airports": ["江北"], "train_station": "重庆北站"},
    "长沙": {"airport": "CSX", "airports": ["黄花"], "train_station": "长沙南站"},
    "沈阳": {"airport": "SHE", "airports": ["桃仙"], "train_station": "沈阳北站"},
    "长春": {"airport": "CGQ", "airports": ["龙嘉"], "train_station": "长春站"},
    "哈尔滨": {"airport": "HRB", "airports": ["太平"], "train_station": "哈尔滨西站"},
    "天津": {"airport": "TSN", "airports": ["滨海"], "train_station": "天津站"},
    "乌鲁木齐": {"airport": "URC", "airports": ["地窝堡"], "train_station": "乌鲁木齐站"},
    "济南": {"airport": "TNA", "airports": ["遥墙"], "train_station": "济南西站"},
    "大连": {"airport": "DLC", "airports": ["周水子"], "train_station": "大连北站"},
    "郑州": {"airport": "CGO", "airports": ["新郑"], "train_station": "郑州东站"},
    "石家庄": {"airport": "SJW", "airports": ["正定"], "train_station": "石家庄站"},
    "太原": {"airport": "TYN", "airports": ["武宿"], "train_station": "太原南站"},
    "昆明": {"airport": "KMG", "airports": ["长水"], "train_station": "昆明南站"},
    "合肥": {"airport": "HFE", "airports": ["新桥"], "train_station": "合肥南站"},
    "福州": {"airport": "FOC", "airports": ["长乐"], "train_station": "福州站"},
    "厦门": {"airport": "XMN", "airports": ["高崎"], "train_station": "厦门北站"},
    "东京": {"airport": "NRT/HND", "airports": ["成田", "羽田"]},
    "大阪": {"airport": "KIX", "airports": ["关西"]},
    "首尔": {"airport": "ICN", "airports": ["仁川"]},
    "香港": {"airport": "HKG", "airports": ["赤鱲角"]},
}

# 雪场 → 最近机场/到达城市
_RESORT_ARRIVAL = {
    # 崇礼区域
    "万龙滑雪场": {"arrive_city": "张家口", "arrive_station": "太子城站", "train_from": "北京北站", "train_hours": 1},
    "太舞滑雪小镇": {"arrive_city": "张家口", "arrive_station": "太子城站", "train_from": "北京北站", "train_hours": 1},
    "云顶滑雪公园": {"arrive_city": "张家口", "arrive_station": "太子城站", "train_from": "北京北站", "train_hours": 1},
    "富龙滑雪场": {"arrive_city": "张家口", "arrive_station": "崇礼站", "train_from": "北京北站", "train_hours": 1.2},
    # 东北
    "北大湖滑雪场": {"arrive_city": "长春", "arrive_airport": "龙嘉机场", "transfer": "机场大巴/租车 2h"},
    "松花湖滑雪场": {"arrive_city": "长春", "arrive_airport": "龙嘉机场", "transfer": "机场大巴/租车 1.5h"},
    "亚布力滑雪场": {"arrive_city": "哈尔滨", "arrive_airport": "太平机场", "transfer": "高铁+大巴 3h"},
    "长白山滑雪场": {"arrive_city": "长白山", "arrive_airport": "长白山机场", "transfer": "机场大巴 30min"},
    # 新疆
    "将军山滑雪场": {"arrive_city": "乌鲁木齐", "arrive_airport": "地窝堡机场", "transfer": "飞机到阿勒泰 1h + 市区30min"},
    "可可托海滑雪场": {"arrive_city": "乌鲁木齐", "arrive_airport": "地窝堡机场", "transfer": "飞机到富蕴 1h + 大巴1h"},
    # 日本（与 resorts_db.json 中的名称对齐）
    "二世谷（Niseko）": {"arrive_city": "札幌", "arrive_airport": "新千岁机场", "transfer": "巴士 2.5h"},
    "白马（Hakuba）": {"arrive_city": "东京/长野", "arrive_airport": "成田/羽田", "transfer": "新干线到长野 1.5h + 巴士 1h"},
    "志贺高原（Shiga Kogen）": {"arrive_city": "东京/长野", "arrive_airport": "成田/羽田", "transfer": "新干线到长野 1.5h + 巴士 1.5h"},
    "留寿都（Rusutsu）": {"arrive_city": "札幌", "arrive_airport": "新千岁机场", "transfer": "巴士 2h"},
    "富良野（Furano）": {"arrive_city": "札幌", "arrive_airport": "新千岁机场", "transfer": "JR 2h"},
    "妙高高原（Myoko Kogen）": {"arrive_city": "东京", "arrive_airport": "成田/羽田", "transfer": "新干线到上越妙高 2h + 巴士 30min"},
    "安比高原（Appi Kogen）": {"arrive_city": "东京", "arrive_airport": "成田/羽田", "transfer": "新干线到盛冈 2.5h + 巴士 45min"},
    # 韩国
    "龙平（YongPyong）": {"arrive_city": "首尔", "arrive_airport": "仁川机场", "transfer": "巴士 2.5h"},
    "凤凰平昌（Phoenix）": {"arrive_city": "首尔", "arrive_airport": "仁川机场", "transfer": "KTX到珍富 1.5h + 出租 20min"},
    "High1滑雪场": {"arrive_city": "首尔", "arrive_airport": "仁川机场", "transfer": "巴士 3h"},
    # 欧洲
    "三峡谷（Les 3 Vallées）": {"arrive_city": "日内瓦/里昂", "arrive_airport": "日内瓦机场", "transfer": "大巴/租车 3h"},
    "采尔马特（Zermatt）": {"arrive_city": "日内瓦/苏黎世", "arrive_airport": "日内瓦/苏黎世机场", "transfer": "火车 3-4h"},
    "夏蒙尼（Chamonix）": {"arrive_city": "日内瓦", "arrive_airport": "日内瓦机场", "transfer": "大巴 1.5h"},
    "圣安东（St. Anton）": {"arrive_city": "因斯布鲁克", "arrive_airport": "因斯布鲁克机场", "transfer": "火车 1.5h"},
    "多洛米蒂（Dolomiti Superski）": {"arrive_city": "威尼斯/因斯布鲁克", "arrive_airport": "威尼斯机场", "transfer": "租车 2.5h"},
    "基茨比尔（Kitzbühel）": {"arrive_city": "因斯布鲁克", "arrive_airport": "因斯布鲁克机场", "transfer": "火车 1h"},
    # 北美
    "惠斯勒（Whistler）": {"arrive_city": "温哥华", "arrive_airport": "温哥华机场", "transfer": "大巴/租车 2h"},
    "范尔（Vail）": {"arrive_city": "丹佛", "arrive_airport": "丹佛机场", "transfer": "大巴/租车 2h"},
    "帕克城（Park City）": {"arrive_city": "盐湖城", "arrive_airport": "盐湖城机场", "transfer": "租车 45min"},
    "杰克逊霍尔（Jackson Hole）": {"arrive_city": "杰克逊", "arrive_airport": "杰克逊霍尔机场", "transfer": "出租 15min"},
    "大天空（Big Sky）": {"arrive_city": "波兹曼", "arrive_airport": "波兹曼机场", "transfer": "租车 1h"},
    "阿斯本（Aspen Snowmass）": {"arrive_city": "丹佛/阿斯本", "arrive_airport": "阿斯本机场/丹佛机场", "transfer": "直飞或丹佛租车 4h"},
    # 南半球
    "Cardrona": {"arrive_city": "皇后镇", "arrive_airport": "皇后镇机场", "transfer": "租车 1h"},
    "Treble Cone": {"arrive_city": "皇后镇", "arrive_airport": "皇后镇机场", "transfer": "租车 1.5h"},
    "皇后镇（Remarkables）": {"arrive_city": "皇后镇", "arrive_airport": "皇后镇机场", "transfer": "租车 30min"},
    "Coronet Peak": {"arrive_city": "皇后镇", "arrive_airport": "皇后镇机场", "transfer": "租车 25min"},
    "Thredbo": {"arrive_city": "悉尼/堪培拉", "arrive_airport": "悉尼机场", "transfer": "自驾 5-6h 或飞堪培拉+自驾 2.5h"},
    "Perisher": {"arrive_city": "悉尼/堪培拉", "arrive_airport": "悉尼机场", "transfer": "自驾 5-6h 或飞堪培拉+自驾 2.5h"},
}


def _fuzzy_match_resort(name: str) -> Optional[str]:
    """模糊匹配雪场名称：支持简称、英文名、括号内名称"""
    db = load_resorts_db()
    # 精确匹配
    if name in db:
        return name
    # 去掉空格/括号再试
    name_clean = name.strip()
    for db_name in db:
        if db_name == "_meta":
            continue
        # 数据库名称包含用户输入，或用户输入包含数据库名称
        if name_clean in db_name or db_name in name_clean:
            return db_name
        # 匹配括号内的英文名
        if "（" in db_name:
            cn_part = db_name.split("（")[0]
            en_part = db_name.split("（")[1].rstrip("）")
            if name_clean.lower() in [cn_part.lower(), en_part.lower()]:
                return db_name
            if cn_part in name_clean or en_part.lower() in name_clean.lower():
                return db_name
    return None


# ─── OTA 平台链接模板 ───

_OTA_LINKS = {
    "flights_cn": [
        {"name": "携程机票", "url": "https://flights.ctrip.com/online/list/oneway-{from_city}-{to_city}?depdate={date_start}"},
        {"name": "飞猪", "url": "https://www.fliggy.com/"},
        {"name": "去哪儿", "url": "https://flight.qunar.com/"},
    ],
    "flights_intl": [
        {"name": "Google Flights", "url": "https://www.google.com/travel/flights"},
        {"name": "Skyscanner", "url": "https://www.skyscanner.com/"},
        {"name": "携程国际", "url": "https://flights.ctrip.com/"},
    ],
    "trains_cn": [
        {"name": "12306", "url": "https://www.12306.cn/"},
        {"name": "携程火车票", "url": "https://trains.ctrip.com/"},
    ],
    "hotels_cn": [
        {"name": "携程酒店", "url": "https://hotels.ctrip.com/"},
        {"name": "美团", "url": "https://hotel.meituan.com/"},
        {"name": "飞猪酒店", "url": "https://hotel.fliggy.com/"},
    ],
    "hotels_intl": [
        {"name": "Booking.com", "url": "https://www.booking.com/"},
        {"name": "Agoda", "url": "https://www.agoda.com/"},
        {"name": "携程海外酒店", "url": "https://hotels.ctrip.com/"},
    ],
    "ski_tickets_cn": [
        {"name": "去哪儿门票", "url": "https://piao.qunar.com/"},
        {"name": "美团门票", "url": "https://www.meituan.com/"},
        {"name": "飞猪门票", "url": "https://www.fliggy.com/"},
        {"name": "闲鱼（二手）", "url": "https://www.goofish.com/"},
    ],
    "ski_tickets_jp": [
        {"name": "WAmazing Snow", "url": "https://snow.wamazing.com/"},
        {"name": "KLOOK", "url": "https://www.klook.com/"},
        {"name": "日本滑雪指南", "url": "https://www.snowjapan.com/"},
    ],
    "ski_tickets_intl": [
        {"name": "Liftopia", "url": "https://www.liftopia.com/"},
        {"name": "Ikon Pass", "url": "https://www.ikonpass.com/"},
        {"name": "Epic Pass", "url": "https://www.epicpass.com/"},
    ],
    "ski_tickets_kr": [
        {"name": "KLOOK", "url": "https://www.klook.com/"},
        {"name": "Trip.com", "url": "https://www.trip.com/"},
        {"name": "韩游网", "url": "https://www.hanyouwang.com/"},
    ],
    "ski_tickets_eu": [
        {"name": "KLOOK", "url": "https://www.klook.com/"},
        {"name": "GetYourGuide", "url": "https://www.getyourguide.com/"},
        {"name": "雪场官网", "url": ""},
    ],
}


# ─── 核心功能 ───

def _get_resort_info(resort_name: str) -> Tuple[Optional[dict], Optional[dict]]:
    """获取雪场信息和到达信息（支持模糊匹配）"""
    db = load_resorts_db()
    # 先尝试模糊匹配拿到标准名称
    matched_name = _fuzzy_match_resort(resort_name)
    if not matched_name:
        return None, None
    resort = db.get(matched_name)
    arrival = _RESORT_ARRIVAL.get(matched_name, {})
    return resort, arrival


def _determine_transport_type(from_city: str, resort: dict, arrival: dict) -> str:
    """判断最佳交通方式：flight/train/drive"""
    if not from_city or from_city not in CITY_COORDS:
        return "flight"

    from_coord = CITY_COORDS[from_city]
    dist = haversine(from_coord[0], from_coord[1], resort["lat"], resort["lon"])

    # 国际目的地
    country = resort.get("country", "CN")
    if country != "CN":
        return "flight"

    # 崇礼特殊：北京/天津/石家庄 优先高铁
    province = resort.get("province", "")
    if "崇礼" in province:
        if from_city in ("北京", "天津", "石家庄", "张家口"):
            return "train"
        elif dist < 500:
            return "drive"
        else:
            return "flight_then_train"

    # 通用规则
    if dist < 300:
        return "drive"
    elif dist < 800:
        # 看有没有直达高铁
        if arrival.get("arrive_station"):
            return "train"
        return "flight"
    else:
        return "flight"


def generate_search_queries(params: dict) -> str:
    """
    生成搜索策略。
    输入: {
        "resort": "北大湖滑雪场",
        "from_city": "上海",
        "date_start": "2026-01-15",
        "date_end": "2026-01-18",
        "people": 2,
        "hotel_type": "经济型|中档|高档"  // 可选
    }
    输出: JSON 包含三组搜索关键词 + OTA 链接 + 数据库参考价
    """
    resort_name = params.get("resort", "")
    from_city = params.get("from_city", "")
    date_start = params.get("date_start", "")
    date_end = params.get("date_end", "")
    people = params.get("people", 1)
    hotel_type = params.get("hotel_type", "中档")

    # 模糊匹配雪场名称
    matched_name = _fuzzy_match_resort(resort_name)
    if matched_name:
        resort_name = matched_name

    resort, arrival = _get_resort_info(resort_name)
    if not resort:
        db = load_resorts_db()
        available = [k for k in db if k != "_meta"]
        return json.dumps({"error": f"未找到雪场「{resort_name}」", "available": available}, ensure_ascii=False)

    country = resort.get("country", "CN")
    is_domestic = country == "CN"
    province = resort.get("province", "")
    nearby_city = resort.get("nearby_city", "")

    # 计算天数
    if date_start and date_end:
        try:
            d1 = datetime.strptime(date_start, "%Y-%m-%d")
            d2 = datetime.strptime(date_end, "%Y-%m-%d")
            days = (d2 - d1).days
        except ValueError:
            days = 4
        year = date_start[:4]
        month = date_start[5:7]
    else:
        days = params.get("days", 4)
        year = str(datetime.now(CST).year)
        month = ""

    ski_days = min(days, days - 1) if days > 1 else 1

    # 交通类型
    transport_type = _determine_transport_type(from_city, resort, arrival)

    result = {
        "resort": resort_name,
        "from_city": from_city,
        "dates": {"start": date_start, "end": date_end, "days": days, "ski_days": ski_days},
        "people": people,
        "transport_type": transport_type,
        "db_reference": {
            "ticket_range_cny": resort.get("ticket_range_cny", [0, 0]),
            "hotel_range_cny": resort.get("hotel_range_cny", [0, 0]),
            "transport_ref": resort.get("transport_ref", {}),
        },
    }

    # ─── 1. 交通搜索策略 ───
    transport_queries = []
    arrive_city = arrival.get("arrive_city", nearby_city)
    transfer_info = arrival.get("transfer", "")

    if transport_type == "flight":
        if is_domestic:
            transport_queries.append({
                "type": "flight",
                "query": f"{from_city}到{arrive_city} 机票 {date_start}",
                "query_return": f"{arrive_city}到{from_city} 机票 {date_end}",
                "hint": f"搜索{from_city}→{arrive_city}往返机票，关注含税价",
            })
            result["ota_links"] = _OTA_LINKS["flights_cn"]
        else:
            transport_queries.append({
                "type": "international_flight",
                "query": f"{from_city} to {arrive_city} flight {date_start}",
                "query_cn": f"{from_city}飞{arrive_city} 机票 {date_start} 往返",
                "hint": f"搜索{from_city}→{arrive_city}国际往返机票，注意含税价和行李额",
            })
            result["ota_links"] = _OTA_LINKS["flights_intl"]

    elif transport_type == "train":
        station = arrival.get("arrive_station", "")
        transport_queries.append({
            "type": "train",
            "query": f"{from_city}到{station or arrive_city} 高铁 {date_start}",
            "hint": f"搜索{from_city}→{station or arrive_city}高铁票价",
        })
        result["ota_links"] = _OTA_LINKS["trains_cn"]

    elif transport_type == "drive":
        transport_queries.append({
            "type": "drive",
            "query": f"{from_city}到{resort_name} 自驾 距离 油费 过路费",
            "hint": "搜索自驾距离和费用估算",
        })
        result["ota_links"] = []

    elif transport_type == "flight_then_train":
        transport_queries.append({
            "type": "flight_then_train",
            "query_flight": f"{from_city}到张家口 或 北京 机票 {date_start}",
            "query_train": f"北京北站到太子城站 高铁 {date_start}",
            "hint": f"先飞北京，再高铁到太子城（约1小时）",
        })
        result["ota_links"] = _OTA_LINKS["flights_cn"] + _OTA_LINKS["trains_cn"]

    if transfer_info:
        transport_queries.append({
            "type": "local_transfer",
            "info": f"到达后接驳：{transfer_info}",
        })

    result["transport_search"] = transport_queries

    # ─── 2. 住宿搜索策略 ───
    hotel_queries = []
    # 基于区域生成搜索词
    if is_domestic:
        hotel_area = province.split("·")[-1] if "·" in province else province
        hotel_queries.append({
            "query": f"{resort_name} 附近酒店 {hotel_type} {date_start} 价格",
            "query_alt": f"{hotel_area} 滑雪酒店 {year}{'年' + month + '月' if month else ''}",
            "hint": f"搜索{resort_name}周边{hotel_type}住宿，{days-1}晚",
        })
        result["hotel_ota_links"] = _OTA_LINKS["hotels_cn"]
    else:
        hotel_queries.append({
            "query": f"{resort_name} hotel {date_start} price",
            "query_cn": f"{resort_name} 酒店 {hotel_type} 价格 {year}",
            "hint": f"搜索{resort_name}周边住宿（{hotel_type}），{days-1}晚",
        })
        result["hotel_ota_links"] = _OTA_LINKS["hotels_intl"]

    # 特殊住宿提示
    if "崇礼" in province:
        hotel_queries[0]["tip"] = "崇礼住宿选择：雪场slope-side酒店（贵但方便）、崇礼县城（经济实惠需通勤）、万龙/太舞小镇公寓"
    elif "吉林" in province:
        hotel_queries[0]["tip"] = "北大湖：山上Club Med/凯悦（高档）、雪场公寓/民宿（中档）、吉林市区（经济需通勤2h）"

    result["hotel_search"] = hotel_queries

    # ─── 3. 雪票搜索策略 ───
    ticket_queries = []
    ticket_range = resort.get("ticket_range_cny", [0, 0])

    if is_domestic:
        ticket_queries.append({
            "query": f"{resort_name} 雪票 价格 {year}{'年' + month + '月' if month else '雪季'}",
            "query_discount": f"{resort_name} 特价票 残票 优惠 {year}",
            "hint": f"搜索当季雪票价格，数据库参考价 ¥{ticket_range[0]}-{ticket_range[1]}/天",
            "db_price": ticket_range,
        })
        result["ticket_ota_links"] = _OTA_LINKS["ski_tickets_cn"]
    elif "日本" in resort.get("region", ""):
        ticket_queries.append({
            "query": f"{resort_name} lift ticket price {year}",
            "query_cn": f"{resort_name} 雪票 价格 {year}",
            "hint": f"搜索当季雪票价格（日元），数据库参考价 ¥{ticket_range[0]}-{ticket_range[1]}/天（人民币）",
            "db_price": ticket_range,
        })
        result["ticket_ota_links"] = _OTA_LINKS["ski_tickets_jp"]
    elif "韩国" in resort.get("region", ""):
        ticket_queries.append({
            "query": f"{resort_name} lift ticket price {year}",
            "query_cn": f"{resort_name} 雪票 价格 {year}",
            "hint": f"搜索当季雪票价格（韩元），数据库参考价 ¥{ticket_range[0]}-{ticket_range[1]}/天（人民币）",
            "db_price": ticket_range,
        })
        result["ticket_ota_links"] = _OTA_LINKS["ski_tickets_kr"]
    elif "欧洲" in resort.get("region", ""):
        ticket_queries.append({
            "query": f"{resort_name} lift ticket price {year} season",
            "query_cn": f"{resort_name} 雪票 价格 {year}",
            "hint": f"搜索当季雪票价格（欧元/瑞士法郎），数据库参考价 ¥{ticket_range[0]}-{ticket_range[1]}/天（人民币）",
            "db_price": ticket_range,
        })
        result["ticket_ota_links"] = _OTA_LINKS["ski_tickets_eu"]
    else:
        # 北美、南半球等
        ticket_queries.append({
            "query": f"{resort_name} lift ticket price {year} season",
            "hint": f"搜索当季雪票价格，数据库参考价 ¥{ticket_range[0]}-{ticket_range[1]}/天（人民币）",
            "db_price": ticket_range,
        })
        result["ticket_ota_links"] = _OTA_LINKS["ski_tickets_intl"]

    result["ticket_search"] = ticket_queries

    # ─── 4. Agent 指引 ───
    result["agent_instruction"] = {
        "workflow": [
            f"1. 使用 WebSearch 依次搜索以上关键词（交通 {len(transport_queries)} 组、住宿 {len(hotel_queries)} 组、雪票 {len(ticket_queries)} 组）",
            "2. 从搜索结果中提取具体价格数据（优先 OTA 平台价格）",
            "3. 将收集到的价格传入 parse-results 命令生成完整预算报告",
            "4. 如果某项搜索无结果，可使用数据库参考价（db_reference）作为备选",
        ],
        "parse_template": {
            "resort": resort_name,
            "from_city": from_city,
            "dates": {"start": date_start, "end": date_end, "days": days},
            "people": people,
            "prices": {
                "flight_per_person": "搜索到的机票单价（往返）",
                "train_per_person": "搜索到的火车票单价（往返）",
                "hotel_per_night": "搜索到的每晚住宿价格",
                "ticket_per_day": "搜索到的每天雪票价格",
                "local_transport": "当地接驳费用（单程，每人）",
                "sources": {
                    "flight_source": "价格来源（如：携程）",
                    "hotel_source": "价格来源",
                    "ticket_source": "价格来源",
                },
            },
        },
    }

    return json.dumps(result, ensure_ascii=False, indent=2)


def parse_results(params: dict) -> str:
    """
    解析 Agent 搜索到的价格数据，生成结构化预算报告。
    输入: {
        "resort": "北大湖滑雪场",
        "from_city": "上海",
        "dates": {"start": "2026-01-15", "end": "2026-01-18", "days": 3},
        "people": 2,
        "prices": {
            "flight_per_person": 1200,         // 往返含税
            "train_per_person": 0,              // 不走火车则 0
            "hotel_per_night": 450,             // 每晚
            "hotel_nights": 2,                  // 可选，默认 days-1
            "ticket_per_day": 580,              // 每天
            "ticket_days": 2,                   // 可选，默认 days-1
            "rental_per_day": 200,              // 装备租赁/天（可选）
            "food_per_day": 150,                // 餐饮/天/人（可选）
            "local_transport_per_person": 100,  // 当地接驳/人（可选）
            "insurance_per_person": 50,         // 保险/人（可选）
            "extras_per_person": 0,             // 其他/人（可选）
            "sources": {                        // 价格来源标注
                "flight_source": "携程",
                "hotel_source": "美团",
                "ticket_source": "去哪儿"
            }
        }
    }
    """
    resort_name = params.get("resort", "")
    from_city = params.get("from_city", "")
    dates = params.get("dates", {})
    people = params.get("people", 1)
    prices = params.get("prices", {})
    days = dates.get("days", 4)

    # 模糊匹配雪场名称
    matched_name = _fuzzy_match_resort(resort_name)
    if matched_name:
        resort_name = matched_name

    resort, _ = _get_resort_info(resort_name)

    # 填充缺省值（用数据库参考价）
    if resort:
        db_ticket = resort.get("ticket_range_cny", [0, 0])
        db_hotel = resort.get("hotel_range_cny", [0, 0])
        db_transport = resort.get("transport_ref", {}).get("cost_cny", [0, 0])
    else:
        db_ticket = db_hotel = db_transport = [0, 0]

    flight_pp = prices.get("flight_per_person", 0)
    train_pp = prices.get("train_per_person", 0)
    transport_pp = flight_pp or train_pp  # 取非零的那个
    if transport_pp == 0:
        transport_pp = sum(db_transport) / 2  # 数据库均值作为备选

    hotel_per_night = prices.get("hotel_per_night", 0)
    if hotel_per_night == 0:
        hotel_per_night = sum(db_hotel) / 2

    hotel_nights = prices.get("hotel_nights", max(days - 1, 1))

    ticket_per_day = prices.get("ticket_per_day", 0)
    if ticket_per_day == 0:
        ticket_per_day = sum(db_ticket) / 2

    ticket_days = prices.get("ticket_days", max(days - 1, 1))

    rental_per_day = prices.get("rental_per_day", 0)
    food_per_day = prices.get("food_per_day", 150)
    local_transport_pp = prices.get("local_transport_per_person", 0)
    insurance_pp = prices.get("insurance_per_person", 50)
    extras_pp = prices.get("extras_per_person", 0)

    sources = prices.get("sources", {})

    # 计算
    transport_total = transport_pp * people
    hotel_total = hotel_per_night * hotel_nights
    ticket_total = ticket_per_day * ticket_days * people
    rental_total = rental_per_day * ticket_days * people
    food_total = food_per_day * days * people
    local_total = local_transport_pp * people * 2  # 往返
    insurance_total = insurance_pp * people
    extras_total = extras_pp * people

    grand_total = (transport_total + hotel_total + ticket_total + rental_total
                   + food_total + local_total + insurance_total + extras_total)
    per_person = grand_total / people if people > 0 else grand_total

    # 缓存结果
    cache_key = _cache_key({"resort": resort_name, "from": from_city, "dates": dates})
    _set_cache(cache_key, {
        "grand_total": grand_total, "per_person": per_person,
        "breakdown": {
            "transport": transport_total, "hotel": hotel_total,
            "ticket": ticket_total, "rental": rental_total,
            "food": food_total, "local": local_total,
            "insurance": insurance_total, "extras": extras_total,
        }
    })

    # 格式化输出
    symbol = "¥"
    date_str = f"{dates.get('start', '')} ~ {dates.get('end', '')}" if dates.get("start") else f"{days}天"
    lines = [f"💰 {resort_name} 实时费用估算（{people}人 {date_str}）\n"]

    if from_city:
        lines.append(f"📍 出发城市：{from_city}\n")

    lines.append("| 项目 | 单价 | 数量 | 小计 | 人均 | 来源 |")
    lines.append("|------|------|------|------|------|------|")

    items = []

    # 交通
    source_label = sources.get("flight_source", sources.get("train_source", ""))
    transport_type_label = "机票往返" if flight_pp > 0 else "火车往返" if train_pp > 0 else "交通往返"
    is_db_fallback = (flight_pp == 0 and train_pp == 0)
    source_text = f"{source_label}" if source_label else ("数据库参考" if is_db_fallback else "")
    items.append((transport_type_label, f"{symbol}{transport_pp:.0f}/人", f"×{people}人",
                   transport_total, transport_total / people, source_text))

    # 住宿
    hotel_source = sources.get("hotel_source", "")
    is_hotel_db = (prices.get("hotel_per_night", 0) == 0)
    items.append(("住宿", f"{symbol}{hotel_per_night:.0f}/晚", f"×{hotel_nights}晚",
                   hotel_total, hotel_total / people,
                   hotel_source if hotel_source else ("数据库参考" if is_hotel_db else "")))

    # 雪票
    ticket_source = sources.get("ticket_source", "")
    is_ticket_db = (prices.get("ticket_per_day", 0) == 0)
    items.append(("雪票", f"{symbol}{ticket_per_day:.0f}/天/人", f"×{ticket_days}天×{people}人",
                   ticket_total, ticket_total / people,
                   ticket_source if ticket_source else ("数据库参考" if is_ticket_db else "")))

    # 装备租赁
    if rental_total > 0:
        items.append(("装备租赁", f"{symbol}{rental_per_day:.0f}/天/人", f"×{ticket_days}天×{people}人",
                       rental_total, rental_total / people, ""))

    # 餐饮
    items.append(("餐饮", f"{symbol}{food_per_day:.0f}/天/人", f"×{days}天×{people}人",
                   food_total, food_total / people, "估算"))

    # 当地接驳
    if local_total > 0:
        items.append(("当地接驳", f"{symbol}{local_transport_pp:.0f}/人/单程", f"×{people}人×往返",
                       local_total, local_total / people, ""))

    # 保险
    items.append(("滑雪保险", f"{symbol}{insurance_pp:.0f}/人", f"×{people}人",
                   insurance_total, insurance_total / people, "建议"))

    # 其他
    if extras_total > 0:
        items.append(("其他费用", f"{symbol}{extras_pp:.0f}/人", f"×{people}人",
                       extras_total, extras_total / people, ""))

    for name, unit, qty, total, pp, src in items:
        src_col = f"📌{src}" if src else ""
        lines.append(f"| {name} | {unit} | {qty} | {symbol}{total:.0f} | {symbol}{pp:.0f} | {src_col} |")

    lines.append(f"| **合计** | | | **{symbol}{grand_total:.0f}** | **{symbol}{per_person:.0f}** | |")

    # 数据库对比
    if resort:
        db_ref = resort.get("transport_ref", {})
        db_est = (sum(db_ticket) / 2 * ticket_days +
                  sum(db_hotel) / 2 * hotel_nights +
                  sum(db_ref.get("cost_cny", [0, 0])) / 2) * people + food_total + insurance_total
        diff = grand_total - db_est
        diff_pct = (diff / db_est * 100) if db_est > 0 else 0
        lines.append(f"\n📊 **与数据库参考价对比**：")
        lines.append(f"  · 数据库估算：约 {symbol}{db_est:.0f}（{symbol}{db_est/people:.0f}/人）")
        if abs(diff_pct) > 5:
            direction = "高于" if diff > 0 else "低于"
            lines.append(f"  · 实时价格{direction}参考价 {abs(diff_pct):.0f}%")
        else:
            lines.append(f"  · 实时价格与参考价基本一致")

    # 省钱建议
    lines.append(f"\n💡 **省钱建议**：")
    if ticket_per_day > 0:
        lines.append(f"  · 雪票：提前在 OTA 平台购买通常比现场便宜 10-20%")
    if hotel_per_night > 300:
        lines.append(f"  · 住宿：考虑雪场周边民宿/公寓，多人出行可平摊")
    if transport_pp > 1000:
        lines.append(f"  · 交通：提前 2-4 周购买机票，关注航司会员日特价")
    lines.append(f"  · 综合：关注雪场套餐（雪票+住宿捆绑通常有折扣）")

    # JSON 输出供程序使用
    result_json = {
        "resort": resort_name,
        "from_city": from_city,
        "dates": dates,
        "people": people,
        "grand_total": round(grand_total),
        "per_person": round(per_person),
        "breakdown": {
            "transport": round(transport_total),
            "hotel": round(hotel_total),
            "ticket": round(ticket_total),
            "rental": round(rental_total),
            "food": round(food_total),
            "local_transport": round(local_total),
            "insurance": round(insurance_total),
            "extras": round(extras_total),
        },
        "sources": sources,
    }

    lines.append("\n<!-- LIVE_COSTS_JSON -->")
    lines.append(json.dumps(result_json, ensure_ascii=False))

    return "\n".join(lines)


def live_costs_guide(params: dict) -> str:
    """
    一步到位：返回搜索策略 + 简化版预算模板。
    适用于 Agent 第一次调用时，一次性拿到所有需要的信息。
    """
    queries_json = generate_search_queries(params)
    queries = json.loads(queries_json)

    if "error" in queries:
        return queries_json

    # 生成简洁版输出
    lines = [f"🔍 **{queries['resort']}** 联网查价策略\n"]
    lines.append(f"📍 {queries['from_city']} → {queries['resort']}  |  {queries['dates']['days']}天{queries['people']}人\n")

    # 数据库参考价快览
    db = queries.get("db_reference", {})
    lines.append("📦 **数据库参考价**（如搜索无结果可用此备选）：")
    lines.append(f"  · 雪票：¥{db.get('ticket_range_cny', [0,0])[0]}-{db.get('ticket_range_cny', [0,0])[1]}/天")
    lines.append(f"  · 住宿：¥{db.get('hotel_range_cny', [0,0])[0]}-{db.get('hotel_range_cny', [0,0])[1]}/晚")
    ref = db.get("transport_ref", {})
    if ref:
        lines.append(f"  · 交通：¥{ref.get('cost_cny', [0,0])[0]}-{ref.get('cost_cny', [0,0])[1]}/人（参考自{ref.get('from', '?')}）\n")

    # 搜索关键词
    lines.append("🔎 **请依次搜索以下关键词**：\n")

    lines.append("**交通：**")
    for q in queries.get("transport_search", []):
        if q["type"] == "local_transfer":
            lines.append(f"  📌 {q['info']}")
        else:
            for key in ["query", "query_return", "query_flight", "query_train", "query_cn"]:
                if key in q:
                    lines.append(f"  · `{q[key]}`")
            if q.get("hint"):
                lines.append(f"    💡 {q['hint']}")

    lines.append("\n**住宿：**")
    for q in queries.get("hotel_search", []):
        for key in ["query", "query_alt", "query_cn"]:
            if key in q:
                lines.append(f"  · `{q[key]}`")
        if q.get("hint"):
            lines.append(f"    💡 {q['hint']}")
        if q.get("tip"):
            lines.append(f"    📌 {q['tip']}")

    lines.append("\n**雪票：**")
    for q in queries.get("ticket_search", []):
        for key in ["query", "query_discount", "query_cn"]:
            if key in q:
                lines.append(f"  · `{q[key]}`")
        if q.get("hint"):
            lines.append(f"    💡 {q['hint']}")

    # OTA 快速链接
    all_links = []
    for key in ["ota_links", "hotel_ota_links", "ticket_ota_links"]:
        for link in queries.get(key, []):
            if link not in all_links:
                all_links.append(link)

    if all_links:
        lines.append("\n🔗 **OTA 快速入口**：")
        for link in all_links:
            lines.append(f"  · [{link['name']}]({link['url']})")

    # Agent 指引
    lines.append("\n---")
    lines.append("📋 **搜索完成后**，请将价格填入以下模板并调用 `parse-results`：")
    template = queries.get("agent_instruction", {}).get("parse_template", {})
    lines.append(f"```json\npython scripts/price_fetcher.py parse-results '{json.dumps(template, ensure_ascii=False)}'\n```")

    # 附带 JSON
    lines.append("\n<!-- SEARCH_QUERIES_JSON -->")
    lines.append(queries_json)

    return "\n".join(lines)


# ─── 主入口 ───

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "search-queries":
        params = json.loads(sys.argv[2]) if len(sys.argv) > 2 else json.load(sys.stdin)
        print(generate_search_queries(params))
    elif cmd == "parse-results":
        params = json.loads(sys.argv[2]) if len(sys.argv) > 2 else json.load(sys.stdin)
        print(parse_results(params))
    elif cmd == "live-costs":
        params = json.loads(sys.argv[2]) if len(sys.argv) > 2 else json.load(sys.stdin)
        print(live_costs_guide(params))
    else:
        print(f"未知命令: {cmd}")
        print(__doc__)
        sys.exit(1)
