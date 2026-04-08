#!/usr/bin/env python3
"""
滑雪电子教练 - 视觉分析、数据管理与进步追踪
用法: python scripts/ski_coach.py <command> [args]

命令:
  analyze  '<json>'      分析单张滑雪照片/视频截图（调用视觉模型 API）
  analyze-batch '<json>' 批量分析多张图片（支持 images 列表或 dir 目录扫描）
  record   '<json>'      记录一次滑雪分析结果
  history  [json]        查看历史记录（可选过滤条件）
  progress [json]        生成进步报告
  season   [json]        生成雪季总结
  config   '<json>'      配置分析模型和偏好
  show-config            显示当前配置
  stats                  输出统计摘要
  export   [path]        导出所有数据为 JSON

数据存储：通过 utils.py 统一管理，默认 ~/.ski-assistant/
"""

import base64
import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime
from collections import defaultdict

# ─── 导入共享工具 ───
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SCRIPT_DIR)
from utils import (
    DATA_DIR, RECORDS_PATH, CONFIG_PATH, CST,
    ensure_dir, load_json, save_json, level_label, sport_label,
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
    data = load_json(RECORDS_PATH, [])
    if not isinstance(data, list):
        return []
    return data

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
    ratio = min(score / scale, 1.0)  # 防止溢出
    filled = round(ratio * 10)
    return "█" * filled + "░" * (10 - filled)


# 常用非标准维度名的中文映射（fallback）
_EXTRA_DIM_LABELS = {
    "edge_control": "立刃控制",
    "speed_control": "速度控制",
    "balance": "平衡感",
    "carving": "卡宾技术",
    "park": "公园技术",
    "jump": "跳跃",
    "switch": "反脚滑行",
    "mogul": "猫跳",
    "powder": "粉雪技术",
    "confidence": "自信度",
    "safety": "安全意识",
    "rhythm": "节奏感",
    "line_choice": "路线选择",
    "style": "风格",
}


# level_label 已从 utils 导入，不再重复定义


# ─── 视觉分析 API 调用 ───

_ANALYSIS_PROMPT = """你是一个专业滑雪教练，请分析这张滑雪照片/截图。

用户信息：水平={level}，运动类型={sport_type}。
{extra_context}

请按以下 JSON 格式输出评分和建议（所有分数满分10分）：
{{
  "scores": {{
    "posture": {{"center_of_gravity": 分数, "knee_bend": 分数, "upper_body": 分数, "arm_position": 分数, "hip_alignment": 分数}},
    "turning": {{"edge_angle": 分数, "turn_shape": 分数, "edge_transition": 分数, "carving_quality": 分数}},
    "overall": {{"speed_control": 分数, "line_choice": 分数, "terrain_adaptation": 分数, "confidence": 分数, "safety_awareness": 分数}}
  }},
  "highlights": ["亮点1", "亮点2"],
  "issues": ["问题1", "问题2"],
  "advice": ["建议1", "建议2"],
  "coach_note": "一句话总结"
}}

严格只输出 JSON，不要输出其他任何内容。"""


def _encode_image(image_path: str) -> tuple:
    """读取图片并 base64 编码，返回 (base64_str, media_type)"""
    ext = os.path.splitext(image_path)[1].lower()
    media_types = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
                   ".webp": "image/webp", ".gif": "image/gif"}
    media_type = media_types.get(ext, "image/jpeg")
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8"), media_type


def _call_openai_vision(api_key: str, model: str, image_b64: str, media_type: str, prompt: str) -> str:
    """调用 OpenAI 兼容的视觉 API"""
    url = os.environ.get("OPENAI_API_BASE", "https://api.openai.com") + "/v1/chat/completions"
    payload = {
        "model": model or "gpt-4o",
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{image_b64}"}}
        ]}],
        "max_tokens": 2000, "temperature": 0.3
    }
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        result = json.loads(resp.read())
    return result["choices"][0]["message"]["content"]


def _call_anthropic_vision(api_key: str, model: str, image_b64: str, media_type: str, prompt: str) -> str:
    """调用 Anthropic Claude Vision API"""
    url = "https://api.anthropic.com/v1/messages"
    payload = {
        "model": model or "claude-sonnet-4-20250514",
        "max_tokens": 2000,
        "messages": [{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": image_b64}},
            {"type": "text", "text": prompt}
        ]}]
    }
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"x-api-key": api_key, "anthropic-version": "2023-06-01",
                                          "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        result = json.loads(resp.read())
    return result["content"][0]["text"]


def _call_google_vision(api_key: str, model: str, image_b64: str, media_type: str, prompt: str) -> str:
    """调用 Google Gemini Vision API"""
    model = model or "gemini-2.0-flash"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [
            {"text": prompt},
            {"inline_data": {"mime_type": media_type, "data": image_b64}}
        ]}]
    }
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        result = json.loads(resp.read())
    return result["candidates"][0]["content"]["parts"][0]["text"]


def _call_qwen_vision(api_key: str, model: str, image_b64: str, media_type: str, prompt: str) -> str:
    """调用通义千问 VL API（OpenAI 兼容格式，使用 dashscope 端点）"""
    old_base = os.environ.get("OPENAI_API_BASE")
    os.environ["OPENAI_API_BASE"] = "https://dashscope.aliyuncs.com/compatible-mode"
    try:
        return _call_openai_vision(api_key, model or "qwen-vl-max", image_b64, media_type, prompt)
    finally:
        if old_base is not None:
            os.environ["OPENAI_API_BASE"] = old_base
        else:
            os.environ.pop("OPENAI_API_BASE", None)


def _call_doubao_vision(api_key: str, model: str, image_b64: str, media_type: str, prompt: str) -> str:
    """调用豆包视觉模型（火山引擎 ARK，OpenAI 兼容格式）"""
    old_base = os.environ.get("OPENAI_API_BASE")
    os.environ["OPENAI_API_BASE"] = os.environ.get("DOUBAO_API_BASE", "https://ark.cn-beijing.volces.com/api/v3").rstrip("/v1/chat/completions")
    try:
        return _call_openai_vision(api_key, model or "doubao-vision-pro", image_b64, media_type, prompt)
    finally:
        if old_base is not None:
            os.environ["OPENAI_API_BASE"] = old_base
        else:
            os.environ.pop("OPENAI_API_BASE", None)


def _call_stepfun_vision(api_key: str, model: str, image_b64: str, media_type: str, prompt: str) -> str:
    """调用阶跃星辰视觉模型（OpenAI 兼容格式）"""
    old_base = os.environ.get("OPENAI_API_BASE")
    os.environ["OPENAI_API_BASE"] = "https://api.stepfun.com"
    try:
        return _call_openai_vision(api_key, model or "step-1v", image_b64, media_type, prompt)
    finally:
        if old_base is not None:
            os.environ["OPENAI_API_BASE"] = old_base
        else:
            os.environ.pop("OPENAI_API_BASE", None)


def _call_zhipu_vision(api_key: str, model: str, image_b64: str, media_type: str, prompt: str) -> str:
    """调用智谱 GLM-4V 视觉模型（OpenAI 兼容格式）"""
    old_base = os.environ.get("OPENAI_API_BASE")
    os.environ["OPENAI_API_BASE"] = "https://open.bigmodel.cn/api/paas"
    try:
        return _call_openai_vision(api_key, model or "glm-4v-plus", image_b64, media_type, prompt)
    finally:
        if old_base is not None:
            os.environ["OPENAI_API_BASE"] = old_base
        else:
            os.environ.pop("OPENAI_API_BASE", None)


_VISION_CALLERS = {
    "openai": ("OPENAI_API_KEY", _call_openai_vision),
    "anthropic": ("ANTHROPIC_API_KEY", _call_anthropic_vision),
    "google": ("GOOGLE_API_KEY", _call_google_vision),
    "qwen": ("DASHSCOPE_API_KEY", _call_qwen_vision),
    "doubao": ("DOUBAO_API_KEY", _call_doubao_vision),
    "stepfun": ("STEPFUN_API_KEY", _call_stepfun_vision),
    "zhipu": ("ZHIPU_API_KEY", _call_zhipu_vision),
}


def analyze(params: dict) -> str:
    """
    分析滑雪照片。
    参数:
    {
        "image": "/path/to/photo.jpg",       # 必填：图片路径
        "resort": "万龙滑雪场",               # 可选
        "run": "银龙道",                      # 可选
        "difficulty": "blue",                 # 可选
        "context": "这是第二趟中级道"          # 可选：额外上下文
    }
    """
    image_path = params.get("image", "")
    if not image_path or not os.path.exists(image_path):
        return f"❌ 图片不存在：{image_path}\n请提供有效的图片路径。"

    cfg = _load_config()
    model_cfg = cfg.get("model", {})
    if isinstance(model_cfg, str):
        model_cfg = {"provider": model_cfg}

    provider = model_cfg.get("provider", "auto")
    model_name = model_cfg.get("name", "")

    # auto 模式：按优先级尝试已配置 API key 的提供商
    if provider == "auto":
        for p, (env_key, _) in _VISION_CALLERS.items():
            if os.environ.get(env_key) or os.environ.get(model_cfg.get("api_key_env", "")):
                provider = p
                break
        if provider == "auto":
            # 降级为 Agent 自身视觉分析模式
            preset = cfg.get("analysis_preset", {})
            level = preset.get("level", "intermediate")
            sport = preset.get("sport_type", "alpine")
            extra = params.get("context", "")
            if params.get("resort"):
                extra += f"\n雪场：{params['resort']}"
            if params.get("run"):
                extra += f"\n雪道：{params['run']}"

            prompt = _ANALYSIS_PROMPT.format(level=level_label(level), sport_type=sport,
                                              extra_context=extra if extra else "无额外信息")

            record_tpl = {
                "date": datetime.now(CST).strftime("%Y-%m-%d"),
                "resort": params.get("resort", ""),
                "run_name": params.get("run", params.get("run_name", "")),
                "trail_difficulty": params.get("difficulty", params.get("trail_difficulty", "")),
                "media_type": "photo",
                "media_path": image_path,
                "sport_type": sport,
                "level": level,
            }

            fallback = {
                "mode": "agent_vision",
                "image_path": image_path,
                "analysis_prompt": prompt,
                "record_template": record_tpl,
                "instruction": (
                    "未检测到外部视觉模型 API Key，请 Agent 使用自身视觉能力完成以下步骤：\n"
                    "1. 查看图片文件（上方 image_path）\n"
                    "2. 按照 analysis_prompt 中的要求分析并输出 JSON\n"
                    "3. 将分析结果（scores/highlights/issues/advice/coach_note）合并到 record_template 中\n"
                    "4. 调用 python scripts/ski_coach.py record '<合并后的完整JSON>' 完成记录"
                )
            }
            return json.dumps(fallback, ensure_ascii=False, indent=2)

    if provider not in _VISION_CALLERS:
        return f"❌ 不支持的模型提供商：{provider}。可选：{', '.join(_VISION_CALLERS.keys())}"

    env_key, caller = _VISION_CALLERS[provider]
    api_key = os.environ.get(model_cfg.get("api_key_env", "")) or os.environ.get(env_key, "")
    if not api_key:
        return f"❌ 缺少 API Key。请设置环境变量 {env_key} 或在 config 中指定 api_key_env。"

    # 构建分析提示
    preset = cfg.get("analysis_preset", {})
    level = preset.get("level", "intermediate")
    sport = preset.get("sport_type", "alpine")
    extra = params.get("context", "")
    if params.get("resort"):
        extra += f"\n雪场：{params['resort']}"
    if params.get("run"):
        extra += f"\n雪道：{params['run']}"

    prompt = _ANALYSIS_PROMPT.format(level=level_label(level), sport_type=sport,
                                      extra_context=extra if extra else "无额外信息")

    # 编码图片
    image_b64, media_type = _encode_image(image_path)

    # 调用 API
    try:
        raw = caller(api_key, model_name, image_b64, media_type, prompt)
    except urllib.error.HTTPError as e:
        body = e.read().decode() if hasattr(e, 'read') else str(e)
        return f"❌ API 调用失败（{e.code}）：{body[:500]}"
    except Exception as e:
        return f"❌ API 调用失败：{str(e)}"

    # 解析 JSON 结果
    try:
        # 提取 JSON（可能被 ```json ``` 包裹）
        clean = raw.strip()
        if clean.startswith("```"):
            clean = clean.split("\n", 1)[1].rsplit("```", 1)[0]
        analysis = json.loads(clean)
    except json.JSONDecodeError:
        return f"❌ 模型返回格式异常，无法解析：\n{raw[:1000]}"

    # 自动记录
    record_params = {
        "date": datetime.now(CST).strftime("%Y-%m-%d"),
        "resort": params.get("resort", ""),
        "run_name": params.get("run", params.get("run_name", "")),
        "trail_difficulty": params.get("difficulty", params.get("trail_difficulty", "")),
        "media_type": "photo",
        "media_path": image_path,
        "sport_type": sport,
        "level": level,
        "scores": analysis.get("scores", {}),
        "highlights": analysis.get("highlights", []),
        "issues": analysis.get("issues", []),
        "advice": analysis.get("advice", []),
        "coach_note": analysis.get("coach_note", ""),
    }

    result_text = record(record_params)

    header = f"🤖 分析模型：{provider}" + (f" / {model_name}" if model_name else "")
    return f"{header}\n\n{result_text}"


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
    if not isinstance(params.get("scores"), dict) or not params.get("scores"):
        return "❌ scores 参数缺失或格式错误，需要一个包含评分维度的 JSON 对象。\n示例：{\"scores\":{\"posture\":{\"center_of_gravity\":7.5,...},\"turning\":{...},\"overall\":{...}}}"

    records = _load_records()
    cfg = _load_config()
    scale = cfg.get("scoring", {}).get("scale", 10)

    entry = {
        "id": params.get("session_id", datetime.now(CST).strftime("%Y%m%d-%H%M%S")),
        "date": params.get("date", datetime.now(CST).strftime("%Y-%m-%d")),
        "resort": params.get("resort", ""),
        "run_name": params.get("run_name", params.get("run", "")),
        "trail_difficulty": params.get("trail_difficulty", params.get("difficulty", "")),
        "snow_condition": params.get("snow_condition", ""),
        "media_type": params.get("media_type", "photo"),
        "media_path": params.get("media_path", ""),
        "level": params.get("level", cfg.get("analysis_preset", {}).get("level", "")),
        "sport_type": params.get("sport_type", cfg.get("analysis_preset", {}).get("sport_type", "alpine")),
        "scores": params.get("scores", {}) if isinstance(params.get("scores"), dict) else {},
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
    # 检测分数是否超出当前量程，若普遍超标（如0-100分但量程10），自动归一化
    all_raw_vals = []
    for dim, sub_scores in entry["scores"].items():
        if isinstance(sub_scores, dict):
            all_raw_vals.extend(v for v in sub_scores.values() if isinstance(v, (int, float)))
        elif isinstance(sub_scores, (int, float)):
            all_raw_vals.append(sub_scores)

    needs_normalize = False
    if all_raw_vals and max(all_raw_vals) > scale * 2:
        # 分数明显超出量程（如60分在10分制下），自动归一化到当前量程
        raw_max = max(all_raw_vals)
        norm_factor = scale / (100 if raw_max <= 100 else raw_max)
        needs_normalize = True
        normalize_note = f"（原始分数已从0-{100 if raw_max <= 100 else int(raw_max)}归一化到0-{scale}）"
    else:
        norm_factor = 1.0
        normalize_note = ""

    for dim, sub_scores in entry["scores"].items():
        if isinstance(sub_scores, dict):
            if needs_normalize:
                sub_scores = {k: round(v * norm_factor, 1) if isinstance(v, (int, float)) else v
                              for k, v in sub_scores.items()}
                entry["scores"][dim] = sub_scores
            vals = [v for v in sub_scores.values() if isinstance(v, (int, float))]
            avg = _avg(vals)
        elif isinstance(sub_scores, (int, float)):
            if needs_normalize:
                sub_scores = round(sub_scores * norm_factor, 1)
                entry["scores"][dim] = sub_scores
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

    lines.append(f"### 综合评分：{entry['total_score']}/{scale}")
    if normalize_note:
        lines.append(f"📌 {normalize_note}")
    lines.append("")

    for dim, avg in entry["dimension_averages"].items():
        dim_info = SCORE_DIMENSIONS.get(dim, {})
        label = dim_info.get("label") or _EXTRA_DIM_LABELS.get(dim, dim)
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


def analyze_batch(params: dict) -> str:
    """
    批量分析滑雪照片。
    参数:
    {
        "images": ["/path/to/photo1.jpg", "/path/to/photo2.jpg"],  # 图片列表
        "resort": "万龙滑雪场",    # 可选：统一雪场
        "difficulty": "blue",       # 可选：统一难度
        "skill": "parallel_turn"    # 可选：统一技巧类型
    }
    也支持传入 "dir" 参数扫描目录下所有图片：
    {"dir": "/path/to/photos/", "resort": "万龙"}
    """
    images = params.get("images", [])

    # 支持扫描目录
    scan_dir = params.get("dir", "")
    if scan_dir and os.path.isdir(scan_dir):
        for fname in sorted(os.listdir(scan_dir)):
            if fname.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
                images.append(os.path.join(scan_dir, fname))

    if not images:
        return "❌ 未找到任何图片。请提供 images 列表或 dir 目录路径。"

    cfg = _load_config()
    results = []
    errors = []

    for i, img_path in enumerate(images):
        if not os.path.exists(img_path):
            errors.append(f"  ⚠️ 图片不存在：{img_path}")
            continue

        # 使用 analyze 的降级逻辑
        image_path = img_path
        model_cfg = cfg.get("model", {})
        if isinstance(model_cfg, str):
            model_cfg = {"provider": model_cfg}
        provider = model_cfg.get("provider", "auto")

        if provider == "auto":
            for p, (env_key, _) in _VISION_CALLERS.items():
                if os.environ.get(env_key):
                    provider = p
                    break
            if provider == "auto":
                errors.append(f"  ⚠️ 未配置任何视觉模型 API Key，跳过第 {i+1} 张图片")
                continue

        caller_info = _VISION_CALLERS.get(provider)
        if not caller_info:
            errors.append(f"  ⚠️ 不支持的模型提供商：{provider}，跳过第 {i+1} 张图片")
            continue

        try:
            with open(image_path, "rb") as f:
                raw = f.read()
                image_b64 = base64.b64encode(raw).decode()
            media_type = "image/png" if image_path.lower().endswith(".png") else "image/jpeg"

            preset = cfg.get("analysis_preset", {})
            level = preset.get("level", "intermediate")
            sport = preset.get("sport_type", "alpine")
            extra = params.get("context", "")
            if params.get("resort"): extra += f"\n雪场：{params['resort']}"
            if params.get("run"): extra += f"\n雪道：{params['run']}"
            if params.get("difficulty"): extra += f"\n难度：{params['difficulty']}"
            if params.get("skill"): extra += f"\n技巧类型：{params['skill']}"

            prompt = _ANALYSIS_PROMPT.format(level=level_label(level), sport_type=sport,
                                              extra_context=extra.strip() if extra else "无额外信息")

            env_key, caller_fn = caller_info
            api_key = os.environ.get(env_key, "")
            result = caller_fn(api_key, model_cfg.get("name", ""), image_b64, media_type, prompt)

            if isinstance(result, str):
                result = json.loads(result)

            # 自动记录
            record_entry = {
                "date": params.get("date", datetime.now(CST).strftime("%Y-%m-%d")),
                "resort": params.get("resort", ""),
                "run_name": params.get("run", ""),
                "trail_difficulty": params.get("difficulty", ""),
                "media_type": "photo",
                "media_path": image_path,
                "sport_type": sport,
                "level": level,
            }
            record_entry.update(result)
            record(record_entry)

            score = result.get("scores", {})
            total = 0
            count = 0
            for dim, sub in score.items():
                if isinstance(sub, dict):
                    for v in sub.values():
                        if isinstance(v, (int, float)): total += v; count += 1
                elif isinstance(sub, (int, float)): total += sub; count += 1
            avg_score = round(total / count, 1) if count > 0 else 0

            results.append((os.path.basename(image_path), avg_score, result.get("advice", [])[:1]))
        except Exception as e:
            errors.append(f"  ❌ 分析失败 {os.path.basename(image_path)}：{e}")

    # 输出汇总
    lines = [f"📸 批量分析完成（共 {len(images)} 张图片）\n"]
    lines.append(f"✅ 成功：{len(results)} 张 | ⚠️ 失败：{len(errors)} 张\n")

    if results:
        lines.append("| 图片 | 综合评分 | 关键建议 |")
        lines.append("|------|---------|---------|")
        for name, score, advice in results:
            advice_text = advice[0][:20] + "..." if advice else "-"
            lines.append(f"| {name} | {score}/10 | {advice_text} |")

    if errors:
        lines.append("\n错误详情：")
        for err in errors:
            lines.append(err)

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

        # 取首次和最近的实际值（不做滑动平均，避免记录少时混淆）
        first_val = first.get("dimension_averages", {}).get(dim)
        last_val = last.get("dimension_averages", {}).get(dim)

        if first_val is None or last_val is None:
            continue

        first_avg = round(first_val, 1)
        last_avg = round(last_val, 1)
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
        first_total = round(total_scores[0], 1)
        last_total = round(total_scores[-1], 1)
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
            first_sub_val = first.get("scores", {}).get(dim, {}).get(sub_key) if isinstance(first.get("scores", {}).get(dim), dict) else None
            last_sub_val = last.get("scores", {}).get(dim, {}).get(sub_key) if isinstance(last.get("scores", {}).get(dim), dict) else None

            if first_sub_val is not None and last_sub_val is not None:
                change = round(last_sub_val - first_sub_val, 1)
                sub_changes.append((f"{dim_info.get('label', dim)} > {sub_label}",
                                    round(first_sub_val, 1), round(last_sub_val, 1), change))

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
        # 区分最新记录的 issues 和历史 issues
        latest_issues = set(filtered[-1].get("issues", [])) if filtered else set()
        sorted_issues = sorted(all_issues.items(), key=lambda x: -x[1])

        # 先列当前仍需改进的（最新记录中出现的）
        current = [(issue, count) for issue, count in sorted_issues if issue in latest_issues]
        resolved = [(issue, count) for issue, count in sorted_issues if issue not in latest_issues]

        for issue, count in current[:5]:
            if count > 1:
                lines.append(f"  - {issue}（🔄 持续关注，出现 {count} 次）")
            else:
                lines.append(f"  - {issue}（⚠️ 最新待改进）")

        for issue, count in resolved[:3]:
            lines.append(f"  - {issue}（✅ 已改善）")

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

    # Shorthand: {"model": "auto"} → {"model": {"provider": "auto"}}
    if "model" in params and isinstance(params["model"], str):
        params["model"] = {"provider": params["model"]}

    # 顶层快捷字段 → 路由到正确的子字典
    _preset_shortcuts = ("sport_type", "level", "dimensions", "language")
    _scoring_shortcuts = ("scale", "show_sub_scores", "min_improvement_threshold")
    for k in _preset_shortcuts:
        if k in params and not isinstance(params.get("analysis_preset"), dict):
            cfg.setdefault("analysis_preset", {})
            cfg["analysis_preset"][k] = params.pop(k)
    for k in _scoring_shortcuts:
        if k in params and not isinstance(params.get("scoring"), dict):
            cfg.setdefault("scoring", {})
            cfg["scoring"][k] = params.pop(k)

    # Deep merge
    for key, val in params.items():
        if isinstance(val, dict) and isinstance(cfg.get(key), dict):
            cfg[key].update(val)
        else:
            cfg[key] = val

    _save_config(cfg)

    lines = ["⚙️ 电子教练配置已更新\n"]

    model = cfg.get("model", {})
    if isinstance(model, str):
        model = {"provider": model}
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
    lines.append(f"🏂 运动类型：{sport_label(preset.get('sport_type', 'alpine'))}")

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
    lines.append(f"🏂 **运动类型**：{sport_label(preset.get('sport_type', 'alpine'))}")

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


def import_data(path: str) -> str:
    """从导出文件恢复数据。"""
    if not path or not os.path.exists(path):
        return f"❌ 文件不存在：{path}\n请提供有效的导出文件路径。"

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return f"❌ 读取文件失败：{e}"

    if not isinstance(data, dict) or "records" not in data:
        return "❌ 文件格式不正确，不是有效的 Ski Assistant 导出文件。"

    records = _load_records()
    cfg = _load_config()

    imported_records = data.get("records", [])
    imported_config = data.get("config", {})

    # 合并记录（去重 by id）
    existing_ids = {r.get("id") for r in records}
    new_count = 0
    for r in imported_records:
        if r.get("id") not in existing_ids:
            records.append(r)
            new_count += 1

    _save_records(records)

    # 合并配置（导入的配置优先，但不覆盖用户已修改的项）
    if imported_config:
        for k, v in imported_config.items():
            if k not in cfg or isinstance(v, dict):
                if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                    cfg[k].update(v)
                else:
                    cfg[k] = v
        _save_config(cfg)

    return f"📂 数据导入完成\n  · 新增记录：{new_count} 条\n  · 当前总记录：{len(records)} 条\n  · 导入时间：{datetime.now(CST).strftime('%Y-%m-%d %H:%M')}"


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

    try:
        if cmd == "analyze":
            if len(sys.argv) < 3:
                print("❌ 请提供参数，例如：")
                print('  python scripts/ski_coach.py analyze \'{"image":"/path/to/photo.jpg","resort":"万龙","run":"银龙道","difficulty":"blue"}\'')
                sys.exit(1)
            params = json.loads(sys.argv[2])
            print(analyze(params))
        elif cmd == "analyze-batch":
            params = json.loads(sys.argv[2]) if len(sys.argv) > 2 else json.load(sys.stdin)
            print(analyze_batch(params))
        elif cmd == "record":
            if len(sys.argv) < 3:
                print("❌ 请提供记录参数 JSON，例如：")
                print('  python scripts/ski_coach.py record \'{"date":"2026-01-15","resort":"万龙","scores":{...}}\'')
                sys.exit(1)
            params = json.loads(sys.argv[2])
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
            if len(sys.argv) < 3:
                print("❌ 请提供配置参数 JSON，例如：")
                print('  python scripts/ski_coach.py config \'{"model":{"provider":"openai"}}\'')
                sys.exit(1)
            params = json.loads(sys.argv[2])
            print(config(params))
        elif cmd == "show-config":
            print(show_config())
        elif cmd == "stats":
            print(stats())
        elif cmd == "export":
            path = sys.argv[2] if len(sys.argv) > 2 else None
            print(export_data(path))
        elif cmd == "import":
            if len(sys.argv) < 3:
                print("❌ 请提供导入文件路径，例如：")
                print("  python scripts/ski_coach.py import /path/to/export.json")
                sys.exit(1)
            print(import_data(sys.argv[2]))
        else:
            print(f"❌ 未知命令: {cmd}")
            print(__doc__)
            sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"❌ JSON 参数格式错误：{e}")
        print(f"💡 请使用有效的 JSON 字符串，例如：")
        print(f'   python scripts/ski_coach.py {cmd} \'{{"key":"value"}}\'')
        sys.exit(1)
    except FileNotFoundError as e:
        print(f"❌ 文件不存在：{e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ 执行出错：{type(e).__name__}: {e}")
        sys.exit(1)
