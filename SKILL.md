---
name: ski-assistant
description: 滑雪综合服务助手，提供残票/低价票查找、早鸟票预售体系分析、全球滑雪出行攻略推荐、AI电子教练姿态分析与雪季进步追踪、智能雪场推荐（含专业高山天气/费用估算）、联网实时查价（机票/酒店/雪票）。当用户提到滑雪、雪票、雪场、购票、滑雪旅行、外滑、早鸟票、残票、低价票、滑雪攻略、雪季规划、滑雪动作分析、姿态打分、滑雪教练、滑雪进步、雪季总结、推荐雪场、雪场对比、雪场天气、滑雪预算、实时价格、机票价格、酒店价格、查价时使用。
---

# Ski Assistant - 全球滑雪综合服务助手 v2.4.0

六大模块：残票/低价票查找、早鸟票预售体系、滑雪出行攻略、AI电子教练、智能雪场推荐、联网实时查价。数据策略：内置知识库 + 联网搜索 + Open-Meteo 高山天气 API + OpenStreetMap 全球雪场发现 + flyai 飞猪直连查价（机票/酒店/景点）。电子教练支持用户自选视觉模型。智能推荐引擎根据用户画像自动匹配最优雪场。联网查价支持 flyai 直连（首选）和 WebSearch（备选）两种模式，自动生成结构化预算。联网发现通过 OSM Overpass API 自动搜索新雪场并补充海拔数据。覆盖：中国（崇礼/东北/新疆/北京周边）、日本、韩国、欧洲、北美、南半球、室内雪场。

## 架构概述

### 数据存储（通用化）


存储路径优先级：
1. 环境变量 `SKI_ASSISTANT_DATA_DIR`（用户自定义）
2. `~/.qoderwork/ski-coach/`（旧版兼容）
3. `~/.ski-assistant/`（通用默认路径）

文件清单：
- `user_profile.json` — 用户画像（跨会话持久化）
- `records.json` — 电子教练滑雪记录
- `config.json` — 电子教练配置
- `watchlist.json` — 预售监听列表
- `custom_resorts.json` — 用户自定义雪场数据（可覆盖/扩展内置数据库）

### 雪场数据库（可动态更新）

- 内置数据：`scripts/resorts_db.json`（49+ 全球雪场，含室内）
- 用户扩展：`~/.ski-assistant/custom_resorts.json`（自定义新增或覆盖内置数据）
- 加载策略：内置 + 用户自定义合并，用户数据优先

### 共享工具（scripts/utils.py）

统一路径常量、JSON 读写、`level_label()`、`sport_label()`、`haversine()`、`load_resorts_db()`、`CITY_COORDS`（35+ 城市坐标）。所有脚本均从此导入，不再各自定义。

---

## 模块一：残票 / 低价票查找

**触发**：找便宜雪票、残票、转让票、低价票、折扣票、捡漏、雪票比价。

**流程**：
1. 确认目标雪场、日期、人数、预算
2. 基于 [resorts-reference.md](resorts-reference.md) 提供常规票价基准线
3. WebSearch 搜索：`"{雪场名} 雪票 转让"` / `"{雪场名} 残票"` / `"{雪场名} 特价票 {年份}"`。国内优先：闲鱼、小红书、飞猪、雪场官网；国际：Liftopia、Ikon/Epic Pass
4. 按价格排列输出，标注来源、可信度。可调用 [scripts/ticket_comparator.py](scripts/ticket_comparator.py) 生成比价表

**注意**：提醒二手票风险；可信度不明标注"需自行验证"；国际价格用 [scripts/currency_converter.py](scripts/currency_converter.py) 换算

---

## 模块二：早鸟票预售体系

**触发**：早鸟票、预售、雪季卡、季卡、什么时候买划算、雪季规划。

**流程**：
1. 确认雪场、滑雪次数、预算
2. 基于 [resorts-reference.md](resorts-reference.md) 提供历年早鸟时间线和价格规律
3. WebSearch 搜索当季公告：`"{雪场名} 早鸟票 {年份}"`
4. 给出单次票 vs 次卡 vs 季卡性价比分析

**规律**：崇礼4-6月开售；东北5-7月；新疆6-8月；Ikon/Epic 3-4月；日本7-9月。

### 预售监听

**触发**：帮我盯着、监听预售、自动通知、开售提醒。

**流程**：
1. 确认监听雪场、产品类型、通知渠道
2. 调用 `python scripts/presale_monitor.py watch '<json>'` 注册监听
3. 通过定时任务（cron / 系统调度器 / Agent 定时能力）创建每日检查（建议每天9:00），任务需包含：读取 watchlist → 联网搜索关键词 → 判断预售状态 → 调用 `presale_monitor.py check` → 如有变化发送通知
4. 管理：`list` 查看、`status` 摘要、`remove` 移除

监听数据存储在数据目录下的 `watchlist.json`，仅状态变化时通知。默认通知渠道：`im`（Agent 平台 IM 会话）、`console`（控制台输出）。可选渠道还包括 `email`、`webhook` 等，具体支持取决于 Agent 平台能力。用户可在 watch 时通过 `notify_channels` 字段自定义。

---

## 模块三：滑雪出行攻略

**触发**：外滑、滑雪旅行、去XX滑雪、滑雪攻略、行程规划。

**流程**：
1. 建立画像：水平、出发城市、时间天数、同行人数、预算、偏好
2. 从 [resorts-reference.md](resorts-reference.md) 匹配2-3个雪场
3. WebSearch 补充交通、住宿、天气信息
4. 按 [travel-guide.md](travel-guide.md) 模板输出攻略，预算用 `python scripts/resort_recommender.py costs`

**攻略维度**：雪场对比、交通方案（含费用）、住宿分档、装备清单、保险建议、美食推荐、签证（国际）、预算拆分、行程模板。

**国际注意**：日本关注交通接驳+温泉；欧洲关注申根签+联票策略；北美关注Ikon/Epic+自驾；南半球关注反季(6-10月)。

---

## 模块四：AI 电子教练

**触发**：分析滑雪动作、看看姿态、滑雪打分、电子教练、视频分析、雪季总结、滑雪进步。

### 模型配置

支持自选视觉模型，默认用 Agent 自身视觉能力。`python scripts/ski_coach.py show-config` 查看，`config` 切换。可选：auto（推荐）、openai(gpt-4o)、anthropic(claude-sonnet-4-20250514)、google(gemini-2.0-flash)、qwen(qwen-vl-max)、doubao、stepfun、zhipu。

### 单次分析流程

统一入口：`python scripts/ski_coach.py analyze '{"image":"/path/to/photo.jpg","resort":"万龙滑雪场","run":"银龙道","difficulty":"blue"}'`

**自动降级策略**：
1. 如果用户配置了外部视觉模型 API Key（如 OPENAI_API_KEY），脚本直接调用对应 API 分析并自动记录
2. 如果未配置任何 API Key（默认情况），脚本返回 `agent_vision` 模式的 JSON 输出，包含分析提示词和记录模板。Agent 应按照输出中的 `instruction` 指引完成：
   - 用自身视觉能力查看并分析图片
   - 按 `analysis_prompt` 中的格式生成评分 JSON
   - 将 `scores`/`highlights`/`issues`/`advice`/`coach_note` 合并到 `record_template`
   - 调用 `python scripts/ski_coach.py record '<合并后的JSON>'` 完成记录

可选配置外部 API Key：`export OPENAI_API_KEY=sk-xxx`（或其他提供商对应的环境变量）

### 评分体系（满分10分）

四维度：**基础姿态**(posture)：重心、膝盖弯曲、上半身、手臂、髋部、踝关节；**转弯技术**(turning)：平行站姿、立刃、换刃、卡宾、弯型、点杖；**自由式**(freestyle，仅park/mogul)：起跳、空中、落地、技巧、风格；**综合**(overall)：速控、路线、地形适应、节奏、自信度、安全意识。

分析输出 JSON：`{"scores":{...}, "highlights":[...], "issues":[...], "advice":[...], "coach_note":"..."}`

### 进步报告 & 雪季总结

- `python scripts/ski_coach.py progress` → AI 解读进步趋势
- `python scripts/ski_coach.py season` → AI 撰写雪季回顾

### 命令参考

```bash
python scripts/ski_coach.py analyze '{"image":"/path/to/photo.jpg","resort":"万龙","run":"银龙道","difficulty":"blue"}'  # 视觉分析
python scripts/ski_coach.py history                    # 全部记录
python scripts/ski_coach.py progress                   # 进步报告
python scripts/ski_coach.py season                     # 雪季总结
python scripts/ski_coach.py stats                      # 统计摘要
python scripts/ski_coach.py show-config                # 查看配置
python scripts/ski_coach.py config '<json>'            # 修改配置
python scripts/ski_coach.py export /path/to/file.json  # 导出
```

**注意**：照片适合静态姿态，视频适合动态技术（建议15-60秒侧面）；评分标准随用户水平调整。

---

## 模块五：智能雪场推荐引擎

**触发**：推荐雪场、帮我选雪场、去哪滑雪好、雪场对比、雪场天气、滑雪预算。

### 核心能力

用户画像管理（跨会话持久化）→ 多维度评分推荐（满分100，封顶归一化）→ Open-Meteo 高山天气（按山顶海拔）→ 费用估算（雪票/交通/住宿/餐饮/保险/装备租赁）→ 多雪场对比。

### 雪场数据库

内置 49+ 全球雪场（含室内），外置 JSON 可动态更新：

- **中国·崇礼**：万龙、太舞、云顶、富龙
- **中国·东北**：北大湖、松花湖、亚布力、长白山
- **中国·新疆**：将军山、可可托海、丝绸之路
- **中国·北京周边**：南山、军都山、石京龙
- **中国·其他**：西岭雪山
- **日本**：二世谷、白马、志贺高原、妙高、安比、留寿都、富良野
- **韩国**：龙平、凤凰平昌、High1
- **欧洲**：三峡谷、采尔马特、圣安东、夏蒙尼、多洛米蒂、基茨比尔
- **北美**：惠斯勒、范尔、帕克城、杰克逊霍尔、大天空、阿斯本
- **南半球**：Cardrona、Treble Cone、Remarkables、Coronet Peak、Thredbo、Perisher
- **室内**：融创广州/哈尔滨/成都、热雪奇迹深圳、耀雪上海、Ski Dubai

室内雪场标记 `indoor: true`，全年可滑，推荐算法在非雪季（4-10月）自动加权室内雪场。

**联网更新**：运行 `python scripts/resort_recommender.py update-db` 从 GitHub 拉取最新雪场数据，自动备份旧版本并比对版本号。

**联网发现新雪场**：运行 `python scripts/resort_recommender.py discover '<json>'` 从 OpenStreetMap 全球开放地图数据库自动搜索新雪场。支持按区域搜索（中国/日本/欧洲/北美等），自动与本地数据库对比去重，可选海拔数据补充和自动合并入库。新发现的雪场标记 `_needs_review: true`，建议人工校验票价和雪道信息后再使用。

**用户可自定义**：将 `custom_resorts.json` 放入数据目录，格式与 `resorts_db.json` 相同，会自动合并并覆盖同名条目。

### 交通费用说明

雪场数据中的 `transport_ref` 字段标注了参考出发城市和费用。推荐结果中会明确标注"参考自XX"，Agent 应根据用户实际出发城市提醒调整。距离计算使用 haversine 公式基于用户城市坐标自动完成。

### 命令参考

```bash
# 用户画像
python scripts/resort_recommender.py profile '{"city":"北京","level":"intermediate","sport_type":"snowboard","preferences":["粉雪","夜滑"],"budget_per_trip_cny":5000,"available_days":4}'
python scripts/resort_recommender.py show-profile

# 推荐（Agent应先确认画像再推荐）
python scripts/resort_recommender.py recommend
python scripts/resort_recommender.py recommend '{"include_weather":true,"top_n":5}'
python scripts/resort_recommender.py recommend '{"indoor_only":true}'  # 仅室内雪场

# 高山天气（按山顶海拔，最长16天）
python scripts/resort_recommender.py weather '{"resort":"万龙滑雪场","days":7}'

# 多雪场对比
python scripts/resort_recommender.py compare '{"resorts":["万龙滑雪场","北大湖滑雪场"],"include_weather":true}'

# 费用估算（已合并 budget_calculator 功能）
python scripts/resort_recommender.py costs '{"resort":"北大湖滑雪场","days":4,"people":2,"from_city":"上海","rental_per_day":200}'

# 更新雪场数据库（从 GitHub 拉取最新版本）
python scripts/resort_recommender.py update-db

# 联网发现新雪场（基于 OpenStreetMap）
python scripts/resort_recommender.py discover '{"region":"中国"}'              # 搜索中国所有子区域
python scripts/resort_recommender.py discover '{"region":"中国-崇礼"}'         # 搜索崇礼区域
python scripts/resort_recommender.py discover '{"region":"日本","enrich":true}' # 搜索日本并补充海拔
python scripts/resort_recommender.py discover '{"region":"全部","merge":true}'  # 搜索全球并自动合并入库
```

画像字段：city、level(beginner/intermediate/advanced/expert)、sport_type(ski/snowboard/both)、preferences(偏好标签数组)、budget_per_trip_cny、available_days、travel_dates、must_have、avoid、region_preference(中国/日本/韩国/欧洲/北美/南半球/不限)。

天气特色：按雪场山顶海拔获取、滑雪条件评分1-10（新雪+2/降雨-3/强风-3/过暖-2）、全球覆盖、免费无限调用。

discover参数：region（搜索区域，支持"中国"/"日本"/"欧洲"/"北美"/"全部"，或具体子区域名如"中国-崇礼"/"奥地利-蒂罗尔"）、enrich（是否联网获取海拔数据，默认true）、merge（是否自动合并到本地数据库，默认false仅预览）、limit（单区域最大返回数量，默认50）。数据源：Overpass API（OpenStreetMap，首选），查询 `landuse=winter_sports` 和 `site=piste` 标签。

---

## 模块六：联网实时查价

**触发**：查一下去XX滑雪多少钱、实时价格、机票多少钱、酒店价格、帮我估算费用（实时）。

### 设计理念

脚本负责"搜什么 + 怎么算"，Agent 负责"怎么搜"。不依赖任何第三方 API Key，所有 Agent 平台均可使用。接入 flyai（飞猪 MCP CLI）后，可直接获取机票/酒店/景点的真实报价，无需 Agent 手动搜索。

### 预算功能分工

| 功能 | 命令 | 适用场景 | 数据来源 |
|------|------|---------|---------|
| 自动费用估算 | `resort_recommender.py costs` | 用户只说雪场名和天数，自动算总费用 | 雪场数据库 |
| 手动预算计算 | `budget_calculator.py` | 用户已知每项费用的精确金额，需要汇总 | 用户输入 |
| 实时联网查价 | `price_fetcher.py flyai-live` | 需要实时机票/酒店价格 | flyai 飞猪直连 |

**使用建议**：用户说"帮我查去北大湖滑雪要花多少钱"用 costs 或 flyai-live；用户提供具体费用明细时用 budget_calculator。

### 工作流

**首选方案（flyai 直连）**：
1. Agent 调用 `price_fetcher.py flyai-live` → 脚本自动调用 flyai CLI 查询飞猪实时机票、酒店、景点报价
2. 自动生成包含航班表格、酒店列表、雪票价格、预算汇总的完整报告
3. 附带飞猪预订链接，用户可直接跳转购买
4. 如 flyai 某项查询无结果，自动用数据库参考价兜底

**备选方案（WebSearch）**：
1. Agent 调用 `price_fetcher.py live-costs` → 获取搜索策略（含关键词、OTA 链接、数据库参考价）
2. Agent 用自身 WebSearch 能力依次搜索交通、住宿、雪票价格
3. Agent 将搜索到的价格填入模板，调用 `price_fetcher.py parse-results` → 生成结构化预算报告
4. 如某项搜索无结果，脚本自动使用数据库参考价作为备选

### flyai 集成说明

flyai 是飞猪 MCP CLI 工具，提供机票、酒店、景点门票的实时搜索能力。

**安装**：`npm install -g @fly-ai/flyai-cli`

**可用查询**：
- 国内机票搜索（自动按价格排序，返回航班号、航司、时刻、价格、预订链接）
- 酒店搜索（按目的地/景点搜索，返回价格、评分、星级、预订链接）
- 景点/雪场门票（按城市+类别搜索，返回门票价格、预订链接）

**限制**：
- 暂不支持火车票查询（使用数据库参考价）
- 国际航线/酒店覆盖有限（建议备选 WebSearch）
- 酒店搜索范围基于城市级别，部分偏远雪场附近结果较少

**降级策略**：flyai 未安装时自动提示使用 `live-costs` 命令走 WebSearch 方案。

### 智能特性

- **交通方式自动判断**：根据出发城市和雪场距离/位置自动选择搜索 机票/高铁/自驾 关键词（如北京→崇礼自动推荐高铁，上海→北大湖自动推荐机票）
- **雪场名称模糊匹配**：支持简称（如"二世谷"匹配"二世谷（Niseko）"）、中英文混合
- **到达接驳信息**：内置全球 40+ 雪场的到达城市、机场/车站、接驳方式和时间
- **OTA 平台推荐**：根据国内/国际自动推荐对应 OTA（国内：携程/飞猪/美团/12306；日本：WAmazing/KLOOK；国际：Skyscanner/Booking/Liftopia）
- **数据库价格对比**：实时查到的价格自动与数据库参考价比较，标注偏差百分比
- **结果缓存**：24 小时缓存，避免重复搜索
- **省钱建议**：自动根据费用结构生成针对性省钱建议

### 命令参考

```bash
# 首选：flyai 直连查价（自动调用飞猪搜索机票+酒店+雪票）
python scripts/price_fetcher.py flyai-live '{"resort":"北大湖滑雪场","from_city":"上海","date_start":"2026-01-15","date_end":"2026-01-18","people":2}'

# 备选第一步：获取搜索策略（供 Agent WebSearch）
python scripts/price_fetcher.py live-costs '{"resort":"北大湖滑雪场","from_city":"上海","date_start":"2026-01-15","date_end":"2026-01-18","people":2}'

# 也可仅获取搜索关键词（JSON格式，供程序使用）
python scripts/price_fetcher.py search-queries '{"resort":"北大湖滑雪场","from_city":"上海","date_start":"2026-01-15","date_end":"2026-01-18","people":2}'

# 备选第二步：Agent 搜索后，传入实际价格生成报告
python scripts/price_fetcher.py parse-results '{"resort":"北大湖滑雪场","from_city":"上海","dates":{"start":"2026-01-15","end":"2026-01-18","days":3},"people":2,"prices":{"flight_per_person":1180,"hotel_per_night":480,"ticket_per_day":580,"rental_per_day":200,"local_transport_per_person":120,"sources":{"flight_source":"携程","hotel_source":"美团","ticket_source":"去哪儿"}}}'
```

参数说明：`resort`（雪场名，支持模糊匹配）、`from_city`（出发城市）、`date_start/date_end`（日期）、`people`（人数）、`hotel_type`（经济型/中档/高档，可选）。prices 中所有字段均可选，未提供的自动使用数据库参考值。

---

## 通用规则

- 优先中文源（国内雪场），英文源（国际雪场），每次2-3组关键词
- 信息不足主动提问，输出结尾引导后续问题
- 价格标注币种和时间，国际价格附注原币
- **安全提醒**：建议购买滑雪专项险（国际需含救援）；检查天气雪况；必戴头盔

---

## 附加资源

- **共享工具层**：[scripts/utils.py](scripts/utils.py) — 统一路径/IO/工具函数
- **雪场数据库**：[scripts/resorts_db.json](scripts/resorts_db.json) — 49+ 全球雪场 JSON
- **雪场参考**：[resorts-reference.md](resorts-reference.md) — 详细雪场信息（攻略/早鸟规律/联票）
- **攻略模板**：[travel-guide.md](travel-guide.md)
- **汇率换算**：[scripts/currency_converter.py](scripts/currency_converter.py)
- **票价比价**：[scripts/ticket_comparator.py](scripts/ticket_comparator.py)
- **预售监听**：[scripts/presale_monitor.py](scripts/presale_monitor.py)
- **电子教练**：[scripts/ski_coach.py](scripts/ski_coach.py)
- **智能推荐**：[scripts/resort_recommender.py](scripts/resort_recommender.py) — 推荐/天气/对比/费用估算/联网发现新雪场
- **联网查价**：[scripts/price_fetcher.py](scripts/price_fetcher.py) — 实时机票/酒店/雪票查价（支持 flyai 飞猪直连 + WebSearch 双模式）
- **手动预算**（仅用于用户提供具体费用明细时）：[scripts/budget_calculator.py](scripts/budget_calculator.py)

---

## Changelog

### v2.4.0（2026-04-08）

**推荐引擎增强**：
- 雪场规模权重升级：垂直落差 8 分、面积 6 分、新增雪道总数 4 分（原为 6+5 分）
- 地形公园/单板公园权重细化：基础 6 分 + 地形公园 4 分 + U型池 2 分，单板用户额外 +4 分（最高 12 分）
- 推荐输出增加「适合人群」说明（初学者/中级/高级/发烧友）
- 推荐输出增加详细出行建议（距离提示、交通方式、根据水平给出建议）
- 非雪季/反季雪场自动提示最佳出行时机

**票价比较增强**：
- 新增 `search` 命令：生成多平台搜索关键词列表（飞猪/美团/抖音/闲鱼/小红书）
- 票价统计分析：最低价/最高价/平均价/价差
- 推荐系统升级：区分「最佳价格」和「性价比之选」
- 增加购票建议指南（退改优先、二手票核实、早鸟/季卡建议）

**新增模块**：
- 滑雪装备清单推荐模块 `gear_guide.py`：20+ 装备项、按地区/水平区分、租 vs 买建议

**数据完整性**：
- AI 电子教练新增 `import` 命令：支持从导出文件恢复数据，含去重和配置合并
- 清理数据库备份文件，优化存储空间

### v2.3.0（2026-04-08）

**新增功能**：
- AI 电子教练新增 `analyze-batch` 批量分析命令，支持传入图片列表或扫描目录
- 早鸟票监听新增 `check-all` 手动触发命令，无需外部定时任务即可检查所有监听项
- 推荐引擎在用户未设置画像时自动输出引导信息（出发城市/水平/预算等 6 项）

**修复问题**：
- 当日往返行程天数显示为 0 → 修复为至少 1 天
- 预算计算器不支持嵌套 dict 格式 → 新增 transport/hotel/ticket 等键自动识别
- 雪票价格未明确标注来源 → 现在明确标注"数据库参考价（非实时价格）"

**体验优化**：
- 所有脚本入口增加 try/except 错误处理，JSON 格式错误时输出友好提示和示例
- 城市坐标补充 12 个城市（烟台、威海、淄博、潍坊、南通、无锡、苏州、宁波、温州、南昌、桂林、南宁、札幌、新千岁）
- SKILL.md 增加预算功能分工表格，明确 costs vs budget_calculator vs flyai-live 的区别

### v2.2.1（2026-04-07）

- 修复 flyai 机票价格字段解析错误（adultPrice → ticketPrice）
- 优化酒店搜索多关键词回退策略
- 发布到 ClawHub

### v2.2.0（2026-04-07）

- 集成 flyai 飞猪直连查价（机票/酒店/雪票）
- 新增数据源统计功能
- 预算计算器支持嵌套 dict 格式

### v2.0.1（2026-04-06）

- 新增联网查价模块
- AI 视觉分析支持 7 种模型
- 数据库自动更新 + OSM 新雪场发现
- 修复多项 bug
