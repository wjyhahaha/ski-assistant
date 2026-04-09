#!/usr/bin/env python3
"""
小红书分享卡片生成器
将滑雪分析结果转化为适合发布到小红书的图文卡片

依赖安装:
  pip install Pillow matplotlib numpy

用法:
  python scripts/xhs_card_generator.py score-card '<json>'    # 评分展示型
  python scripts/xhs_card_generator.py progress-card '<json>' # 进步对比型
  python scripts/xhs_card_generator.py milestone-card '<json>'# 里程碑型

输出: 生成图片文件路径，可直接用于小红书发布
"""

import json
import os
import sys
from datetime import datetime
from typing import Optional, Tuple, List, Dict

# ─── 导入共享工具 ───
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_ASSETS_DIR = os.path.join(os.path.dirname(_SCRIPT_DIR), "assets")
_FONTS_DIR = os.path.join(_ASSETS_DIR, "fonts")
sys.path.insert(0, _SCRIPT_DIR)

from utils import DATA_DIR, ensure_dir, load_json, CST, track_usage

# 输出目录
_EXPORTS_DIR = os.path.join(DATA_DIR, "exports")

# ═══════════════════════════════════════════════════════════════
# 依赖检查
# ═══════════════════════════════════════════════════════════════

def check_dependencies():
    """检查必要的依赖是否安装"""
    missing = []
    
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        missing.append("Pillow")
    
    try:
        import matplotlib
        import numpy
    except ImportError:
        missing.append("matplotlib")
        missing.append("numpy")
    
    if missing:
        deps = " ".join(set(missing))
        return False, f"缺少依赖: {deps}\n请运行: pip install {deps}"
    
    return True, None

# 延迟导入（依赖检查通过后）
def _import_pil():
    from PIL import Image, ImageDraw, ImageFont
    return Image, ImageDraw, ImageFont

def _import_mpl():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    return plt, np


# ═══════════════════════════════════════════════════════════════
# 常量定义
# ═══════════════════════════════════════════════════════════════

# 小红书图片规格
XHS_WIDTH = 1080
XHS_HEIGHT = 1440  # 3:4 比例

# 配色方案（滑雪主题）
COLORS = {
    "bg_gradient_top": (25, 55, 95),      # 深蓝
    "bg_gradient_bottom": (60, 120, 160), # 天蓝
    "accent": (255, 140, 60),             # 活力橙
    "accent_light": (255, 200, 120),      # 浅橙
    "white": (255, 255, 255),
    "text_primary": (40, 40, 40),
    "text_secondary": (100, 100, 100),
    "text_light": (255, 255, 255),
    "card_bg": (255, 255, 255, 230),      # 半透明白
    "score_high": (80, 180, 120),         # 高分绿
    "score_mid": (255, 180, 60),          # 中分黄
    "score_low": (230, 100, 100),         # 低分红
}

# 评分维度标签
DIMENSION_LABELS = {
    "posture": "基础姿态",
    "turning": "转弯技术",
    "freestyle": "自由式",
    "overall": "综合滑行",
}


# ═══════════════════════════════════════════════════════════════
# 字体处理
# ═══════════════════════════════════════════════════════════════

def _get_font(ImageFont, size: int, bold: bool = False):
    """获取字体，优先使用系统字体"""
    # 尝试的系统字体路径（macOS/Linux/Windows）
    font_paths = []
    if bold:
        font_paths = [
            "/System/Library/Fonts/PingFang.ttc",  # macOS 苹方
            "/System/Library/Fonts/STHeiti Light.ttc",
            "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",  # Linux
            "C:/Windows/Fonts/simhei.ttf",  # Windows 黑体
            "C:/Windows/Fonts/msyhbd.ttc",  # Windows 雅黑粗体
        ]
    else:
        font_paths = [
            "/System/Library/Fonts/PingFang.ttc",
            "/System/Library/Fonts/STHeiti Light.ttc",
            "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
            "C:/Windows/Fonts/simhei.ttf",
            "C:/Windows/Fonts/msyh.ttc",
        ]
    
    # 尝试加载
    for path in font_paths:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except:
                pass
    
    # 回退到默认字体
    try:
        return ImageFont.load_default()
    except:
        return None


# ═══════════════════════════════════════════════════════════════
# 图片生成工具函数
# ═══════════════════════════════════════════════════════════════

def _create_gradient_background(Image, width: int, height: int, 
                                 color_top: Tuple[int, int, int],
                                 color_bottom: Tuple[int, int, int]):
    """创建渐变背景"""
    img = Image.new('RGB', (width, height))
    pixels = img.load()
    
    for y in range(height):
        ratio = y / height
        r = int(color_top[0] * (1 - ratio) + color_bottom[0] * ratio)
        g = int(color_top[1] * (1 - ratio) + color_bottom[1] * ratio)
        b = int(color_top[2] * (1 - ratio) + color_bottom[2] * ratio)
        for x in range(width):
            pixels[x, y] = (r, g, b)
    
    return img


def _draw_rounded_rectangle(draw, xy: Tuple[int, int, int, int], 
                            radius: int, fill, outline=None, width=1):
    """绘制圆角矩形"""
    x1, y1, x2, y2 = xy
    
    # 主体矩形
    draw.rectangle([x1 + radius, y1, x2 - radius, y2], fill=fill)
    draw.rectangle([x1, y1 + radius, x2, y2 - radius], fill=fill)
    
    # 四个角
    draw.pieslice([x1, y1, x1 + radius * 2, y1 + radius * 2], 180, 270, fill=fill)
    draw.pieslice([x2 - radius * 2, y1, x2, y1 + radius * 2], 270, 360, fill=fill)
    draw.pieslice([x1, y2 - radius * 2, x1 + radius * 2, y2], 90, 180, fill=fill)
    draw.pieslice([x2 - radius * 2, y2 - radius * 2, x2, y2], 0, 90, fill=fill)


def _get_score_color(score: float, max_score: float = 10) -> Tuple[int, int, int]:
    """根据分数返回颜色"""
    ratio = score / max_score
    if ratio >= 0.8:
        return COLORS["score_high"]
    elif ratio >= 0.6:
        return COLORS["score_mid"]
    else:
        return COLORS["score_low"]


def _create_radar_chart(plt, np, scores: Dict[str, float], size: int = 400):
    """创建雷达图，返回 PIL Image"""
    # 准备数据
    dimensions = ["posture", "turning", "freestyle", "overall"]
    labels = [DIMENSION_LABELS.get(d, d) for d in dimensions]
    values = [scores.get(d, 0) for d in dimensions]
    values += values[:1]  # 闭合
    
    # 角度
    angles = np.linspace(0, 2 * np.pi, len(dimensions), endpoint=False).tolist()
    angles += angles[:1]
    
    # 创建图形
    fig, ax = plt.subplots(figsize=(size/100, size/100), subplot_kw=dict(polar=True))
    
    # 绘制
    ax.fill(angles, values, color='#FF8C3C', alpha=0.3)
    ax.plot(angles, values, color='#FF8C3C', linewidth=2)
    
    # 设置标签
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(labels, fontsize=10)
    ax.set_ylim(0, 10)
    
    # 美化
    ax.spines['polar'].set_visible(False)
    ax.grid(color='gray', alpha=0.3)
    
    # 保存到内存
    from io import BytesIO
    buf = BytesIO()
    plt.savefig(buf, format='png', transparent=True, bbox_inches='tight', pad_inches=0.1)
    buf.seek(0)
    img = Image.open(buf)
    plt.close(fig)
    
    return img


def _create_progress_bar(Image, color, width: int = 200, height: int = 20):
    """创建进度条背景"""
    img = Image.new('RGBA', (width, height), (255, 255, 255, 0))
    return img


# ═══════════════════════════════════════════════════════════════
# 卡片生成主函数
# ═══════════════════════════════════════════════════════════════

def generate_score_card(params: dict) -> str:
    """
    生成评分展示型卡片
    
    参数:
    {
        "resort": "万龙滑雪场",
        "run_name": "金龙道",
        "date": "2026-01-15",
        "scores": {
            "posture": 8.5,
            "turning": 7.2,
            "freestyle": 0,
            "overall": 7.8
        },
        "highlights": ["重心控制良好", "转弯节奏稳定"],
        "image_path": "/path/to/photo.jpg",  # 可选
        "style": "casual"  # casual|professional|humorous
    }
    """
    # 检查依赖
    ok, err_msg = check_dependencies()
    if not ok:
        return json.dumps({"error": err_msg}, ensure_ascii=False)
    
    Image, ImageDraw, ImageFont = _import_pil()
    
    # 提取参数
    resort = params.get("resort", "未知雪场")
    run_name = params.get("run_name", "")
    date = params.get("date", datetime.now().strftime("%Y-%m-%d"))
    scores = params.get("scores", {})
    highlights = params.get("highlights", [])
    style = params.get("style", "casual")
    
    # 计算总分
    valid_scores = [v for v in scores.values() if isinstance(v, (int, float)) and v > 0]
    total_score = sum(valid_scores) / len(valid_scores) if valid_scores else 0
    
    # 创建画布
    img = _create_gradient_background(Image, XHS_WIDTH, XHS_HEIGHT, 
                                       COLORS["bg_gradient_top"], 
                                       COLORS["bg_gradient_bottom"])
    draw = ImageDraw.Draw(img)
    
    # 加载字体
    font_title = _get_font(ImageFont, 72, bold=True)
    font_header = _get_font(ImageFont, 48, bold=True)
    font_body = _get_font(ImageFont, 32)
    font_small = _get_font(ImageFont, 24)
    font_score = _get_font(ImageFont, 120, bold=True)
    
    y_offset = 60
    
    # 1. 顶部标题区
    draw.text((XHS_WIDTH // 2, y_offset), "🏂 滑雪日记", 
              font=font_header, fill=COLORS["text_light"], anchor="mm")
    y_offset += 80
    
    # 雪场信息
    draw.text((XHS_WIDTH // 2, y_offset), f"{resort}", 
              font=font_body, fill=COLORS["accent_light"], anchor="mm")
    y_offset += 50
    if run_name:
        draw.text((XHS_WIDTH // 2, y_offset), f"{run_name} | {date}", 
                  font=font_small, fill=COLORS["text_light"], anchor="mm")
        y_offset += 60
    
    # 2. 主分数展示（大数字）
    y_offset += 40
    score_color = _get_score_color(total_score)
    draw.text((XHS_WIDTH // 2, y_offset), f"{total_score:.1f}", 
              font=font_score, fill=score_color, anchor="mm")
    draw.text((XHS_WIDTH // 2 + 120, y_offset + 20), "/10", 
              font=font_body, fill=COLORS["text_light"], anchor="mm")
    y_offset += 140
    
    # 3. 分项进度条
    card_margin = 80
    card_width = XHS_WIDTH - card_margin * 2
    
    y_offset += 20
    for dim, label in DIMENSION_LABELS.items():
        score = scores.get(dim, 0)
        if score <= 0:
            continue
        
        # 标签
        draw.text((card_margin + 20, y_offset + 10), label, 
                  font=font_small, fill=COLORS["text_light"])
        
        # 进度条背景
        bar_bg = Image.new('RGBA', (card_width - 200, 24), (230, 230, 230, 180))
        img.paste(bar_bg, (card_margin + 120, y_offset + 8), bar_bg)
        
        # 进度条填充
        ratio = min(score / 10, 1.0)
        fill_width = int((card_width - 200) * ratio)
        bar_color = (*_get_score_color(score), 220)
        bar_fill = Image.new('RGBA', (fill_width, 24), bar_color)
        img.paste(bar_fill, (card_margin + 120, y_offset + 8), bar_fill)
        
        # 分数
        draw.text((XHS_WIDTH - card_margin - 20, y_offset + 10), f"{score}", 
                  font=font_small, fill=COLORS["text_light"], anchor="rm")
        
        y_offset += 50
    y_offset += 30
    
    # 4. 亮点点评（白色卡片）
    if highlights:
        y_offset += 20
        card_height = min(80 + len(highlights) * 50, 300)
        
        # 绘制半透明卡片背景
        overlay = Image.new('RGBA', (card_width, card_height), COLORS["card_bg"])
        img.paste(overlay, (card_margin, y_offset), overlay)
        
        # 卡片内容
        card_draw = ImageDraw.Draw(img)
        card_y = y_offset + 20
        
        card_draw.text((XHS_WIDTH // 2, card_y), "✨ AI教练点评", 
                       font=font_body, fill=COLORS["accent"], anchor="mm")
        card_y += 50
        
        for highlight in highlights[:3]:  # 最多显示3条
            card_draw.text((card_margin + 30, card_y), f"• {highlight}", 
                           font=font_small, fill=COLORS["text_primary"])
            card_y += 45
        
        y_offset += card_height + 30
    
    # 5. 底部标签
    y_offset = XHS_HEIGHT - 100
    tags = ["#滑雪", "#单板滑雪", f"#{resort.replace('滑雪场', '').replace('滑雪', '')}"]
    tag_text = "  ".join(tags)
    draw.text((XHS_WIDTH // 2, y_offset), tag_text, 
              font=font_small, fill=COLORS["text_light"], anchor="mm")
    
    # 保存
    ensure_dir(_EXPORTS_DIR)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = os.path.join(_EXPORTS_DIR, f"xhs_score_{timestamp}.jpg")
    img.save(output_path, "JPEG", quality=95)
    
    return json.dumps({
        "success": True,
        "output_path": output_path,
        "total_score": round(total_score, 1),
        "style": style,
    }, ensure_ascii=False, indent=2)


def generate_progress_card(params: dict) -> str:
    """
    生成进步对比型卡片（简化版，先占位）
    """
    return json.dumps({"error": "Progress card not yet implemented. Use score-card instead."}, ensure_ascii=False)


def generate_milestone_card(params: dict) -> str:
    """
    生成里程碑型卡片（简化版，先占位）
    """
    return json.dumps({"error": "Milestone card not yet implemented. Use score-card instead."}, ensure_ascii=False)


# ═══════════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════════

def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    
    command = sys.argv[1]
    
    try:
        params = json.loads(sys.argv[2])
    except json.JSONDecodeError as e:
        print(json.dumps({"error": f"Invalid JSON: {e}"}, ensure_ascii=False))
        sys.exit(1)
    
    if command == "score-card":
        track_usage("xhs_card_generator.score-card")
        result = generate_score_card(params)
    elif command == "progress-card":
        track_usage("xhs_card_generator.progress-card")
        result = generate_progress_card(params)
    elif command == "milestone-card":
        track_usage("xhs_card_generator.milestone-card")
        result = generate_milestone_card(params)
    else:
        print(json.dumps({"error": f"Unknown command: {command}"}, ensure_ascii=False))
        sys.exit(1)
    
    print(result)


if __name__ == "__main__":
    main()
