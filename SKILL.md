---
name: ski-assistant
description: |
  Global ski resort assistant covering 899 resorts across 40+ countries. Plan trips, compare prices, analyze your form, and find early-bird deals.
  全球滑雪助手，覆盖 899 座雪场（40+ 国，中国 481 座最全）。帮你挑雪场、查价格、看动作、盯早鸟、报天气。
  Triggers / 触发词: ski, snowboard, 滑雪, 雪票, 雪场, 去哪滑, 外滑, 早鸟票, 季卡, 滑雪攻略, 动作分析, weather, budget, coaching.
  Responds naturally to casual requests in Chinese or English — no special keywords needed.
  自然语言触发：周末去哪滑、雪票太贵了、帮我看看这个动作、万龙多少钱、早鸟票什么时候买。
  Not for: non-ski travel, general city weather, non-winter sports.
  不覆盖：非滑雪旅行、城市天气预报、其他运动装备。
license: MIT
version: 5.2.3
allowed-tools: "Bash(python3 tools/price_api.py *) Bash(python3 tools/exchange_rate.py *) Bash(python3 tools/card_generator.py *) Bash(python3 tools/resort_discovery.py *) WebFetch WebSearch"
metadata:
  author: wjyhahaha
  version: 5.2.3
  category: travel-lifestyle
  tags: [skiing, travel, budget, weather, recommendation]
---

# Ski Assistant v5.2.3 — 全球滑雪综合服务助手

像一个懂滑雪的朋友——帮你挑雪场、比价捡漏、分析动作、盯早鸟、列清单、查山顶天气。

> 数据：`data/resorts_db.json`（899 座雪场） | 参考：`references/`（攻略、装备、教练评分、预算模板） | 工具：`tools/`（仅用于联网查询）

---

## 环境要求

Python 3.9+（标准库即可，零必装第三方依赖）。

可选依赖（缺失时自动降级，不影响核心功能）：

| 依赖 | 用途 | 缺失时行为 |
|------|------|-----------|
| `flyai` CLI（用户自行安装） | 实时机票/酒店价格查询 | 降级为 WebSearch + 数据库参考价 |
| Pillow（`pip install Pillow`） | 生成小红书分享卡片 | 提示安装命令，其他功能不受影响 |

本技能不会自动安装任何软件、创建后台服务或定时任务。

---

## 数据与隐私

### 本地数据（~/.ski-assistant/）

所有数据仅存储在用户本机，不上传到任何远程服务器：

| 文件 | 内容 | 创建时机 |
|------|------|---------|
| `user_profile.json` | 用户画像（水平、城市、偏好） | 首次设置画像 |
| `records.json` | 电子教练评分记录 | 保存分析结果 |
| `config.json` | 教练模型配置 | 配置视觉模型 |
| `watchlist.json` | 预售监听列表 | 添加监听 |
| `price_history.json` | 用户记录的价格数据 | 记录价格 |
| `custom_resorts.json` | 用户自定义雪场 | 手动创建 |
| `usage_stats.json` | 命令调用统计 | 任意功能首次使用 |
| `exports/` | 分享卡片图片 | 生成卡片 |

用户可随时查看、编辑或删除上述任何文件。

### 环境变量（均为可选）

本技能脚本**不依赖任何必需的环境变量**。以下环境变量仅用于可选配置：

| 变量 | 用途 | 默认值 |
|------|------|--------|
| `SKI_ASSISTANT_DATA_DIR` | 自定义用户数据目录路径 | `~/.ski-assistant/` |

**关于视觉分析功能的可选 API Key**：AI 电子教练模块使用 Agent 自身的视觉能力进行动作分析，**不需要**配置任何 API Key。如果用户希望通过特定视觉模型（如 OpenAI GPT-4o、Anthropic Claude、Google Gemini 等）增强分析能力，需要在 Agent 平台层面配置对应服务的 API Key——这是 Agent 平台的通用配置，不是本技能脚本的要求。用户不配置任何 Key 也不影响教练功能的基础使用。

### 网络请求（仅用户主动触发，无后台联网）

所有网络请求均由 Agent 在用户明确请求时触发，技能脚本**不会**创建任何后台服务、守护进程、定时任务或自动联网行为：

| 场景 | 目标 | 触发条件 |
|------|------|---------|
| 高山天气 | api.open-meteo.com | 用户查询雪场天气时 |
| 汇率换算 | api.exchangerate-api.com | 用户需要国际价格换算时 |
| 雪场发现 | overpass-api.de（主）/ overpass.kumi.systems（备）/ nominatim.openstreetmap.org（降级） | 用户运行 discover 命令时 |
| 数据库同步 | raw.githubusercontent.com | 用户运行 update-db 命令时 |
| 实时查价 | 通过 flyai CLI | 用户查机票/酒店且 flyai 可用时 |
| 联网搜索 | Agent 的 WebSearch/WebFetch | 用户要求查价、查攻略、搜低价票时 |

---

## 数据操作规范

### 数据目录

所有用户数据存储在 `~/.ski-assistant/`（可通过 `SKI_ASSISTANT_DATA_DIR` 环境变量自定义）。Agent 通过 Python 一行命令读写：

```bash
# 读取 JSON 文件
python3 -c "import json; data=json.load(open('$HOME/.ski-assistant/user_profile.json')); print(json.dumps(data, ensure_ascii=False, indent=2))"

# 写入/更新 JSON 文件（先读再写，保留已有字段）
python3 -c "
import json, os
path = os.path.expanduser('~/.ski-assistant/user_profile.json')
os.makedirs(os.path.dirname(path), exist_ok=True)
try:
    data = json.load(open(path))
except:
    data = {}
data.update({\"city\": \"北京\", \"level\": \"intermediate\"})
json.dump(data, open(path, 'w'), ensure_ascii=False, indent=2)
print('OK')
"

# 追加记录到数组（records.json / watchlist.json 等）
python3 -c "
import json, os
path = os.path.expanduser('~/.ski-assistant/records.json')
os.makedirs(os.path.dirname(path), exist_ok=True)
try:
    data = json.load(open(path))
except:
    data = []
data.append({\"id\": \"rec_20250115\", \"date\": \"2025-01-15\", \"resort\": \"万龙\"})
json.dump(data, open(path, 'w'), ensure_ascii=False, indent=2)
print('OK')
"
```

### user_profile.json Schema

```json
{
  "city": "北京",
  "level": "intermediate",
  "sport_type": "ski",
  "preferences": ["粉雪", "公园"],
  "budget_per_trip_cny": 5000,
  "available_days": 4,
  "travel_dates": "2026-01-15",
  "companions": "朋友2人",
  "region_preference": "不限",
  "must_have": ["夜滑"],
  "avoid": [],
  "updated_at": "2026-04-10T20:00:00+08:00"
}
```

字段说明：`level` 取值 beginner/intermediate/advanced/expert；`sport_type` 取值 ski/snowboard/both；`region_preference` 为"不限"或具体地区名；其他字段均为可选。

### usage_stats.json Schema

```json
{
  "schema_version": 1,
  "skill_version": "5.1.0",
  "first_used": "2026-01-01T10:00:00+08:00",
  "last_used": "2026-04-10T20:00:00+08:00",
  "total_calls": 42,
  "commands": {
    "trip_planning": {"count": 15, "last": "2026-04-08T..."},
    "pricing": {"count": 10, "last": "2026-04-09T..."},
    "coaching": {"count": 8, "last": "2026-03-20T..."},
    "presale": {"count": 5, "last": "2026-04-10T..."},
    "weather": {"count": 4, "last": "2026-04-07T..."}
  },
  "sessions": {"total": 20, "by_month": {"2026-01": 8, "2026-04": 5}}
}
```

每次执行任意模块功能后，Agent 应读取此文件、递增对应 command 计数和 total_calls、更新 last_used，然后写回。

### custom_resorts.json 合并

推荐雪场时，除了读取 `data/resorts_db.json`，还应检查 `~/.ski-assistant/custom_resorts.json` 是否存在。如果存在，将其内容合并（custom 优先覆盖同名条目），然后再执行推荐算法。

### 主要出发城市坐标参考

推荐算法需要计算用户城市到雪场的距离。以下是常用出发城市坐标（纬度, 经度）：

| 城市 | 坐标 | | 城市 | 坐标 |
|------|------|-|------|------|
| 北京 | 39.90, 116.40 | | 上海 | 31.23, 121.47 |
| 广州 | 23.13, 113.26 | | 深圳 | 22.54, 114.06 |
| 成都 | 30.57, 104.07 | | 杭州 | 30.27, 120.15 |
| 南京 | 32.06, 118.80 | | 武汉 | 30.59, 114.30 |
| 西安 | 34.26, 108.94 | | 重庆 | 29.56, 106.55 |
| 沈阳 | 41.80, 123.43 | | 长春 | 43.88, 125.32 |
| 哈尔滨 | 45.75, 126.65 | | 天津 | 39.13, 117.20 |
| 乌鲁木齐 | 43.83, 87.62 | | 大连 | 38.91, 121.60 |
| 石家庄 | 38.04, 114.51 | | 太原 | 37.87, 112.55 |
| 济南 | 36.65, 116.98 | | 昆明 | 25.04, 102.68 |
| 东京 | 35.68, 139.69 | | 大阪 | 34.69, 135.50 |
| 首尔 | 37.57, 126.98 | | 香港 | 22.32, 114.17 |
| 札幌 | 43.06, 141.35 | | 台北 | 25.03, 121.57 |

距离计算用 Haversine 公式：`d = 2R * arcsin(sqrt(sin²(Δlat/2) + cos(lat1)*cos(lat2)*sin²(Δlon/2)))`，R=6371km。不在表中的城市可用 Agent 自身地理知识估算。

---

## Module 1: Trip Planning / 模块一：行程规划

**触发词 / Triggers**：推荐雪场、去哪滑、帮我规划、去 XX 滑雪、滑雪攻略、行程规划、滑雪要带什么、recommend resort, where to ski, plan my trip, ski itinerary, what to bring, ski budget.

### 流程

1. **收集画像**：水平（初学/中级/高级/发烧友）、出发城市、时间天数、同行人数、预算、偏好（粉雪/公园/夜滑/亲子/温泉等）、运动类型（双板/单板）。缺失项主动提问。

2. **读取数据库**：读取 `data/resorts_db.json`，按以下规则打分（满分 100）：

   **基础分 50 + 偏好匹配（每项+8，封顶+32）+ 距离加分（<300km +15，<800km +8，<2000km +3）+ 时间适配（短途+远距扣10分，长途+远距加3分）+ 预算适配（合预算+12，超30%+4，超更多-8）+ 规模加分（落差/面积/雪道数各有权重）+ 公园加分（最高+12，单板用户额外+4）+ 雪季适配（非雪季室内+15，南半球反季+10，过季-30）- 避免项（每项-12）。**

   取 top 3 输出推荐。

3. **生成攻略**：按 [references/travel-guide.md](references/travel-guide.md) 模板输出完整方案：雪场对比、交通方案、住宿分档、装备清单（参考 [references/gear-guide.md](references/gear-guide.md)）、保险提醒、美食推荐。

4. **预算估算**：参考 [references/budget-templates.md](references/budget-templates.md) 中的参考价，结合数据库中的票价/住宿/交通字段，逐项列出费用明细。

5. **查实时价**（可选）：如用户希望精确价格，按模块二流程获取实时数据。

### 天气查询（关键：必须是山顶海拔天气）

滑雪天气必须查询雪场山顶海拔的天气，而非山脚城镇天气。使用 Open-Meteo API 时 **必须传入 elevation 参数**：

```
https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&elevation={elevation_top}&hourly=temperature_2m,snowfall,snow_depth,windspeed_10m,windgusts_10m,visibility,weathercode&daily=weathercode,temperature_2m_max,temperature_2m_min,apparent_temperature_max,apparent_temperature_min,snowfall_sum,rain_sum,windspeed_10m_max,windgusts_10m_max&timezone=auto&forecast_days=7
```

其中 `lat`、`lon`、`elevation_top` 从 `data/resorts_db.json` 对应雪场获取。

**滑雪条件评分（1-10）规则**：
- 基础 10 分
- 山顶温度 >10°C 扣 4（雪面融化）；>5°C 扣 2；<-25°C 扣 1
- 持续风速 >50km/h 扣 4（缆车可能停运）；>35km/h 扣 2
- 阵风 >70km/h 扣 2；>55km/h 扣 1
- 降雪 >5cm 加 2；小/中雪天气码加 1
- 降雨：>10mm 扣 6，>5mm 扣 5，>2mm 扣 4，其他扣 3
- 阵雨天气码额外扣 1；雷暴扣 2
- 最终裁剪到 1-10

WMO 天气代码映射：0=晴，1=基本晴朗，2=多云，3=阴天，45=雾，48=雾凇，51/53/55=毛毛雨，61/63/65=雨，66/67=冻雨，71/73/75=雪，77=米雪，80/81/82=阵雨，85/86=阵雪，95/96/99=雷暴。

### 推荐输出格式

每个推荐雪场包含：名称、地区、海拔落差、雪道数量统计、特色标签、匹配偏好、费用估算（票价+交通+住宿）、单板友好/公园标记、雪季时间、匹配度评分。如有天气数据，附7天预报表格。

### 国际注意

日本：交通接驳 + JR Pass + 温泉文化。欧洲：申根签 + 联票策略（三峡谷/采尔马特等）。北美：Ikon/Epic Pass + 自驾。南半球：反季 6-10 月。参考 [references/resorts-reference.md](references/resorts-reference.md)。

---

## Module 2: Smart Pricing / 模块二：智能查价

**触发词 / Triggers**：多少钱、查价格、预算、便宜票、残票、转让票、低价票、折扣票、捡漏、雪票比价、外滑套餐、how much, ticket price, budget, cheap tickets, discount, lift ticket deal, resale ticket.

### 三路径查价策略

不同价格信息来源不同，必须分别处理：

**路径 A — 交通 + 住宿（flyai 可查）**：
1. 运行 `python3 tools/price_api.py check` 检测 flyai 是否可用
2. 可用 → `python3 tools/price_api.py search-flight '{"from_city":"上海","to_city":"长春","date":"2026-01-15"}'`
3. 可用 → `python3 tools/price_api.py search-hotel '{"destination":"北大湖","check_in":"2026-01-15","check_out":"2026-01-18"}'`
4. 不可用 → 用 WebSearch 搜索 + 数据库参考价（标注"参考值"）

**路径 B — 雪票价格（flyai 查不到，必须走网络）**：
- WebSearch 搜索组合（2-3 组关键词）：
  - `"{雪场名} 雪票价格 {当前雪季}"` / `"{雪场名} 官方票价"`
  - `"{雪场名} 酷雪 雪票"` / `"{雪场名} 住滑套餐"` — 覆盖微信小程序酷雪、住滑套餐等团购渠道
  - 崇礼雪场专项：`site:chonglihuaxue.cn "{雪场名} 票价"` — 崇礼雪场网提供系统的雪票/季卡/早鸟价格表
- WebFetch 官方网站获取当季票价
- 兜底：使用 `data/resorts_db.json` 中的 `ticket_range_cny` 字段（标注"数据库参考价"）

**路径 C — 残票/转让票/低价票（必须走社交平台）**：
- WebSearch 搜索组合：
  - `"{雪场名} 残票 转让 {年份}"` / `"{雪场名} 低价票 闲鱼"` / `"{雪场名} 雪票转让 小红书"`
  - `"{雪场名} 季卡 转让"` / `"{雪场名} 次卡 转让"` — 季卡/次卡二手交易
- 来源优先级：闲鱼 > 小红书 > 抖音 > 微信群
- 安全提醒：二手票需验证可信度，建议通过正规平台交易

### 国际价格换算

涉及外币时调用：`python3 tools/exchange_rate.py <amount> <from> <to>`

示例：`python3 tools/exchange_rate.py 7800 JPY CNY`

支持币种：CNY, JPY, KRW, CHF, EUR, CAD, USD, NZD, AUD, GBP。联网失败时自动使用备用静态汇率。

### 费用汇总

按 [references/budget-templates.md](references/budget-templates.md) 模板逐项列出：交通、住宿、雪票、装备租赁、餐饮、保险、其他。每项标注来源（实时/参考）。

### 外滑套餐

针对国际场景，提供经济/标准/豪华三档打包方案。国际外滑附加提醒：签证、汇率、保险（含救援）、装备托运。

---

## Module 3: AI Coach / 模块三：AI 电子教练

**触发词 / Triggers**：分析滑雪动作、看看姿态、滑雪打分、电子教练、视频分析、雪季总结、滑雪进步、晒成绩、analyze my form, rate my skiing, ski coach, video analysis, season summary, progress report.

### 分析流程

1. 用户提交滑雪照片/视频
2. Agent 使用自身视觉能力分析，严格按照 [references/coaching-rubric.md](references/coaching-rubric.md) 中的四维度评分标准打分
3. 输出评分结果（亮点/问题/改进建议）
4. 将结果追加到 `~/.ski-assistant/records.json`

### 四维度评分（满分 10 分）

详细评分子项和标准见 [references/coaching-rubric.md](references/coaching-rubric.md)，概要如下：

| 维度 | 子项 | 说明 |
|------|------|------|
| 基础姿态 posture | 重心高度、膝盖弯曲、上半身稳定、手臂位置、视线方向 | 所有水平必评 |
| 转弯技术 turning | 平行站姿、立刃角度、换刃流畅度、速度控制、路线选择 | 所有水平必评 |
| 自由式 freestyle | 空中姿态、落地缓冲、道具技术、创意与风格 | 仅 park/mogul 场景 |
| 综合滑行 overall | 速度控制、路线规划、地形适应、整体协调 | 所有水平必评 |

### 记录保存

分析完成后，构造 JSON 追加写入 `~/.ski-assistant/records.json`：

```json
{
  "id": "rec_{timestamp}",
  "date": "YYYY-MM-DD",
  "resort": "雪场名",
  "run_name": "雪道名",
  "difficulty": "green/blue/black/double_black",
  "scores": {"posture": 8, "turning": 7, "freestyle": 0, "overall": 7.5},
  "highlights": ["亮点1", "亮点2"],
  "issues": ["问题1"],
  "suggestions": ["建议1"],
  "image_path": "/path/to/photo.jpg"
}
```

### 进步报告

读取 `records.json` 全部记录，按时间排序，分析各维度评分趋势。输出：总记录数、各维度平均分变化、最大进步维度、建议下一步练习重点。

### 雪季总结

汇总某雪季（如 2025-2026）内所有记录：去过的雪场、总滑行天数、评分趋势图（文本描述）、个人成长亮点、下赛季目标建议。

### 小红书分享

**触发词 / Triggers**：分享小红书、发小红书、生成分享图、晒成绩、share on XHS, generate share card, share my score.

调用：`python3 tools/card_generator.py score-card '<json>'`

参数示例：
```json
{
  "resort": "万龙滑雪场",
  "date": "2025-01-15",
  "scores": {"posture": 8, "turning": 9, "freestyle": 7, "overall": 8.5},
  "highlights": ["前倾角度标准", "犁式转弯流畅"],
  "style": "casual"
}
```

需要 Pillow 依赖。输出 1080x1440 图片到 `~/.ski-assistant/exports/`。

---

## Module 4: Presale Monitoring / 模块四：早鸟预售

**触发词 / Triggers**：早鸟票、预售、雪季卡、季卡、什么时候买划算、帮我盯着、开售提醒、early bird, season pass, presale, when to buy, watch for deals, price alert.

### 流程

1. 确认雪场、滑雪次数、预算
2. 参考 [references/resorts-reference.md](references/resorts-reference.md) 提供历年早鸟时间线和价格规律
3. WebSearch 搜索当季公告：`"{雪场名} 早鸟票 {年份}"` / `"{雪场名} 季卡 预售"`
4. 给出单次票 vs 次卡 vs 季卡性价比分析

**常见预售时间线**：崇礼 4-6 月、东北 5-7 月、新疆 6-8 月、Ikon/Epic 3-4 月、日本 7-9 月。

### 预售监听

**工作原理**：预售监听是**纯被动记录 + 按需检查**机制，技能脚本不会创建任何后台任务或定时任务。

1. 用户说"帮我盯着XX" → 将目标保存到 `~/.ski-assistant/watchlist.json`：
   ```json
   {"resort": "万龙滑雪场", "product": "早鸟季卡", "added": "2026-04-10", "status": "watching"}
   ```

2. **检查方式**（仅用户主动触发）：
   - 用户说"检查预售状态" → Agent 读取 watchlist.json + WebSearch 查最新公告
   - 用户说"万龙早鸟票开始了吗" → Agent 直接搜索对应雪场的预售信息

3. **关于定时检查的说明**：
   - 本技能脚本**不包含**任何定时调度或自动检查逻辑
   - 如果用户希望实现定期检查，需要依赖 Agent 平台的调度能力（如 cron 任务），且必须经用户明确同意后才能创建
   - 所有通知推送也依赖 Agent 平台的 IM 集成，技能脚本本身不会发送任何通知

**总结**：watchlist.json 仅是一个本地记录清单，所有网络检查和通知都由 Agent 在用户明确要求时执行，技能脚本本身不具备任何自主联网或后台运行能力。

### 价格趋势

用户手动记录价格：追加到 `~/.ski-assistant/price_history.json`。查看趋势时读取历史记录，分析最低/最高/平均/当前价位，给出购买时机建议。

---

## Module 5: Resort Discovery & DB Update / 模块五：雪场发现与数据库更新

### 发现新雪场

调用：`python3 tools/resort_discovery.py discover '{"region":"中国","enrich":true,"merge":false}'`

region 可选值：中国、日本、韩国、欧洲、北美 等，或具体区域如 "中国-崇礼"、"日本-北海道西"。详见脚本内 `_DISCOVERY_REGIONS`（65 个预定义区域，覆盖 27 国）。

- `enrich: true` → 自动通过 Open-Meteo 补充海拔数据
- `merge: true` → 自动合并新发现雪场到本地 `data/resorts_db.json`（标记 `_needs_review: true`）
- 默认 `merge: false`，仅预览

数据源：Overpass API（首选）→ Nominatim（降级）。票价/雪道数/特色等商业信息需人工补充。

### 更新数据库

调用：`python3 tools/resort_discovery.py update-db`

从 GitHub 仓库拉取最新 `resorts_db.json`，自动备份本地文件（.bak），对比版本后覆盖。

---

## 工具脚本参考

所有工具脚本均为独立可执行文件，无相互依赖，无 `utils.py` 依赖。

### tools/price_api.py — flyai 桥接

```bash
python3 tools/price_api.py check                          # 检测 flyai 是否可用
python3 tools/price_api.py search-flight '{"from_city":"北京","to_city":"长春","date":"2026-01-15"}'
python3 tools/price_api.py search-hotel '{"destination":"北大湖","check_in":"2026-01-15","check_out":"2026-01-18"}'
python3 tools/price_api.py search-poi '{"city":"张家口","keyword":"滑雪"}'
```

**重要**：flyai 仅能查询机票和酒店价格，**不能查询雪票价格和残票/转让票**。雪票必须通过 WebSearch 获取。

### tools/exchange_rate.py — 汇率换算

```bash
python3 tools/exchange_rate.py 7800 JPY CNY               # 7800 日元转人民币
python3 tools/exchange_rate.py '{"amount":7800,"from":"JPY","to":"CNY"}'
```

联网获取实时汇率，失败时自动使用备用静态汇率（标注"参考汇率"）。

### tools/card_generator.py — XHS 卡片

```bash
python3 tools/card_generator.py score-card '{"resort":"万龙","date":"2025-01-15","scores":{"posture":8,"turning":9}}'
```

依赖 Pillow，未安装时返回错误提示。

### tools/resort_discovery.py — 雪场发现

```bash
python3 tools/resort_discovery.py discover '{"region":"中国-崇礼","enrich":true,"merge":false}'
python3 tools/resort_discovery.py update-db
```

---

## 数据文件说明

### data/resorts_db.json

304 座全球雪场，覆盖 27 个国家。每个雪场的关键字段：

| 字段 | 说明 |
|------|------|
| `lat`, `lon` | 经纬度坐标 |
| `elevation_base`, `elevation_top` | 基底/山顶海拔（米）|
| `vertical_drop` | 垂直落差（米）|
| `area_km2` | 滑雪面积 |
| `trails` | 雪道数量 `{green, blue, black, double_black}` |
| `ticket_range_cny` | 雪票价格区间（人民币）|
| `hotel_range_cny` | 住宿价格区间 |
| `transport_ref` | 交通参考 `{from, method, hours, cost_cny}` |
| `features` | 特色标签列表 |
| `suited_for` | 适合水平 `[beginner, intermediate, advanced, expert]` |
| `board_friendly` | 单板友好 |
| `park` | 地形公园 |
| `season` | 雪季时间（室内雪场为"全年"）|

### references/ 知识库

| 文件 | 内容 | 使用场景 |
|------|------|---------|
| [travel-guide.md](references/travel-guide.md) | 攻略输出模板 | 生成行程攻略 |
| [resorts-reference.md](references/resorts-reference.md) | 各雪场软信息（早鸟、美食、联票） | 行程规划 + 早鸟预售 |
| [gear-guide.md](references/gear-guide.md) | 装备知识库（必备/服装/护具/分价位） | 装备推荐 |
| [coaching-rubric.md](references/coaching-rubric.md) | AI 教练四维度评分标准 | 动作分析打分 |
| [budget-templates.md](references/budget-templates.md) | 预算参考价模板 | 费用估算 |

---

## MCP 集成（可选，需用户已连接对应服务）

本技能脚本不直接调用任何 MCP 服务，所有 MCP 调用由 Agent 在对话中完成：

- **日历 MCP**（Google Calendar / Outlook）：行程规划后创建出行事件；预售监听触发时创建购票提醒
- **IM MCP**（钉钉 / 飞书 / Slack）：定时检查发现预售状态变化时推送通知
- **文件存储 MCP**（Google Drive / Box）：保存攻略/报告到云端
- **滑雪交易 MCP**（未来扩展）：各雪场官方购票平台及低价渠道三方平台 — 当用户已连接对应服务时，可查询实时票价、住滑套餐、季卡价格并完成购票

未连接 MCP 时，所有输出默认在当前对话展示。

---

## 使用统计

本地统计文件：`~/.ski-assistant/usage_stats.json`。

Agent 在执行各模块功能后，读取该文件追加计数。用户询问"使用情况"时，读取文件以自然语言汇报：总调用次数、各功能使用频次、月度趋势。

统计数据完全本地化，用户可随时查看、清空或删除。

---

## 通用规则

1. 优先中文源（国内雪场），英文源（国际雪场），每次 2-3 组关键词搜索
2. 信息不足主动提问，输出结尾引导后续对话
3. 价格标注币种和时间，国际价格附注原币和换算值
4. 安全提醒：必戴头盔、建议购买滑雪专项险（国际需含救援）、检查天气雪况
5. 所有"参考价"明确标注来源和时效性
6. 天气查询必须使用雪场山顶海拔的 elevation 参数，不可用城市/山脚天气代替

## 常见问题

**Q: 雪票价格不是最新的怎么办？**
A: 内置数据库为参考值。查价时会自动 WebSearch 获取实时价格，失败时用参考价兜底并标注。

**Q: 电子教练怎么用？**
A: 直接发送滑雪照片/视频，Agent 使用自身视觉能力按评分标准分析，无需额外配置。

**Q: 推荐结果不满意？**
A: 检查画像是否准确，或告诉 Agent 具体偏好进行调整。也可要求对比指定的雪场。

**Q: 如何添加新雪场？**
A: 方式 1：手动创建 `~/.ski-assistant/custom_resorts.json`。方式 2：运行 discover 从 OpenStreetMap 发现。

**Q: flyai 不可用怎么办？**
A: 机票酒店改用 WebSearch 查询；雪票本就不通过 flyai，不受影响。
