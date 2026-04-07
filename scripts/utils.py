#!/usr/bin/env python3
"""
ski-assistant 共享工具模块
提供：统一存储路径、雪场数据库加载、通用工具函数
"""

import json
import os
from datetime import timezone, timedelta
from math import radians, sin, cos, sqrt, atan2

# ─── 统一存储路径 ───
# 优先使用环境变量，其次检测常见平台目录，最后用通用 ~/.ski-assistant/
# 这样不绑定 QoderWork，任何平台都能用

def _resolve_data_dir() -> str:
    """解析数据存储根目录，优先级：环境变量 > QoderWork > 通用路径"""
    # 1. 用户通过环境变量自定义
    env = os.environ.get("SKI_ASSISTANT_DATA_DIR")
    if env:
        return os.path.expanduser(env)
    # 2. 检测是否在 QoderWork 环境（向后兼容）
    qw_dir = os.path.expanduser("~/.qoderwork/ski-coach")
    if os.path.isdir(qw_dir):
        return qw_dir
    # 3. 通用路径
    return os.path.expanduser("~/.ski-assistant")


DATA_DIR = _resolve_data_dir()
PROFILE_PATH = os.path.join(DATA_DIR, "user_profile.json")
RECORDS_PATH = os.path.join(DATA_DIR, "records.json")
CONFIG_PATH = os.path.join(DATA_DIR, "config.json")
WATCHLIST_PATH = os.path.join(DATA_DIR, "watchlist.json")
CUSTOM_RESORTS_PATH = os.path.join(DATA_DIR, "custom_resorts.json")

CST = timezone(timedelta(hours=8))


def ensure_dir():
    """确保数据目录存在"""
    os.makedirs(DATA_DIR, exist_ok=True)


def load_json(path: str, default=None):
    """安全加载 JSON 文件"""
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default if default is not None else {}


def save_json(path: str, data):
    """安全保存 JSON 文件"""
    ensure_dir()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ─── 通用工具函数 ───

def level_label(level: str) -> str:
    """滑雪水平代码转中文标签"""
    return {
        "beginner": "初学者",
        "intermediate": "中级",
        "advanced": "高级",
        "expert": "发烧友/竞技"
    }.get(level, level)


def sport_label(sport_type: str) -> str:
    """运动类型代码转中文"""
    return {"ski": "双板", "snowboard": "单板", "both": "双板+单板"}.get(sport_type, sport_type)


def haversine(lat1, lon1, lat2, lon2) -> float:
    """计算两个坐标点之间的距离（公里）"""
    R = 6371
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return R * 2 * atan2(sqrt(a), sqrt(1 - a))


# ─── 雪场数据库加载（支持动态更新） ───

# 内置脚本目录（用于定位 resorts_db.json）
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_BUILTIN_DB_PATH = os.path.join(_SCRIPT_DIR, "resorts_db.json")


def load_resorts_db() -> dict:
    """
    加载雪场数据库。合并策略：
    1. 先加载内置数据（scripts/resorts_db.json）
    2. 再加载用户自定义数据（~/.ski-assistant/custom_resorts.json）
    3. 用户数据可覆盖/新增内置数据
    
    用户可通过 custom_resorts.json 添加新雪场或修正内置数据。
    """
    db = {}
    # 内置数据
    if os.path.exists(_BUILTIN_DB_PATH):
        with open(_BUILTIN_DB_PATH, "r", encoding="utf-8") as f:
            db = json.load(f)
    # 用户自定义覆盖/扩展
    if os.path.exists(CUSTOM_RESORTS_PATH):
        with open(CUSTOM_RESORTS_PATH, "r", encoding="utf-8") as f:
            custom = json.load(f)
            db.update(custom)
    return db


# ─── 主要城市坐标 ───

CITY_COORDS = {
    "北京": (39.90, 116.40), "上海": (31.23, 121.47), "广州": (23.13, 113.26),
    "深圳": (22.54, 114.06), "成都": (30.57, 104.07), "杭州": (30.27, 120.15),
    "南京": (32.06, 118.80), "武汉": (30.59, 114.30), "西安": (34.26, 108.94),
    "重庆": (29.56, 106.55), "长沙": (28.23, 112.94), "郑州": (34.75, 113.65),
    "沈阳": (41.80, 123.43), "大连": (38.91, 121.60), "长春": (43.88, 125.32),
    "哈尔滨": (45.75, 126.65), "天津": (39.13, 117.20), "乌鲁木齐": (43.83, 87.62),
    "济南": (36.65, 116.98), "青岛": (36.07, 120.38), "石家庄": (38.04, 114.51),
    "太原": (37.87, 112.55), "合肥": (31.82, 117.23), "福州": (26.07, 119.30),
    "厦门": (24.48, 118.09), "昆明": (25.04, 102.68), "贵阳": (26.65, 106.63),
    "兰州": (36.06, 103.83), "呼和浩特": (40.84, 111.75), "银川": (38.49, 106.23),
    "拉萨": (29.65, 91.13), "海口": (20.02, 110.35),
    "东京": (35.68, 139.69), "大阪": (34.69, 135.50), "首尔": (37.57, 126.98),
    "香港": (22.32, 114.17), "台北": (25.03, 121.57),
}
