---
name: ski-assistant
description: 全球滑雪综合服务助手，提供残票/低价票查找、早鸟票预售体系分析、全球滑雪出行攻略推荐、AI电子教练姿态分析与雪季进步追踪、智能雪场推荐（含专业高山天气/费用估算）。当用户提到滑雪、雪票、雪场、购票、滑雪旅行、外滑、早鸟票、残票、低价票、滑雪攻略、雪季规划、滑雪动作分析、姿态打分、滑雪教练、滑雪进步、雪季总结、推荐雪场、雪场对比、雪场天气、滑雪预算时使用。
---

# Ski Assistant - 全球滑雪综合服务助手 v2.0

五大模块：残票/低价票查找、早鸟票预售体系、滑雪出行攻略、AI电子教练、智能雪场推荐。数据策略：内置知识库 + 联网搜索 + Open-Meteo 高山天气 API。电子教练支持用户自选视觉模型。智能推荐引擎根据用户画像自动匹配最优雪场。覆盖：中国（崇礼/东北/新疆/北京周边）、日本、韩国、欧洲、北美、南半球、室内雪场。

## 架构概述

### 数据存储（通用化）

所有用户数据统一由 `scripts/utils.py` 管理，**不绑定 QoderWork**，任何平台都能用。

存储路径优先级：
1. 环境变量 `SKI_ASSISTANT_DATA_DIR`（用户自定义）
2. `~/.qoderwork/ski-coach/`（QoderWork 向后兼容）
3. `~/.ski-assistant/`（通用默认路径）

文件清单：
- `user_profile.json` — 用户画像（跨会话持久化）
- `records.json` — 电子教练滑雪记录
- `config.json` — 电子教练配置
- `watchlist.json` — 预售监听列表
- `custom_resorts.json` — 用户自定义雪场数据（可覆盖/扩展内置数据库）

### 雪场数据库（可动态更新）

- 内置数据：`scripts/resorts_db.json`（42+ 全球雪场，含室内）
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
3. 通过 QoderWork 定时任务创建每日检查（每天9:00），定时任务 payload 需包含：读取 watchlist → WebSearch 搜索关键词 → 判断预售状态 → 调用 `presale_monitor.py check` → 如有变化通过 IM 发送通知
4. 管理：`list` 查看、`status` 摘要、`remove` 移除

监听数据存储在数据目录下的 `watchlist.json`，仅状态变化时通知。通知渠道：qoderwork（IM会话）、dingtalk、feishu，通过 `qoder_list_channel_conversations` + `qoder_delegate_to_im` 发送。

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

1. 用户上传照片/视频 → 2. `show-config` 读取模型配置 → 3. 视觉分析打分 → 4. `history '{"last_n":3}'` 获取近期记录对比 → 5. `record '<json>'` 记录结果

### 评分体系（满分10分）

四维度：**基础姿态**(posture)：重心、膝盖弯曲、上半身、手臂、髋部、踝关节；**转弯技术**(turning)：平行站姿、立刃、换刃、卡宾、弯型、点杖；**自由式**(freestyle，仅park/mogul)：起跳、空中、落地、技巧、风格；**综合**(overall)：速控、路线、地形适应、节奏、自信度、安全意识。

分析输出 JSON：`{"scores":{...}, "highlights":[...], "issues":[...], "advice":[...], "coach_note":"..."}`

### 进步报告 & 雪季总结

- `python scripts/ski_coach.py progress` → AI 解读进步趋势
- `python scripts/ski_coach.py season` → AI 撰写雪季回顾

### 命令参考

```bash
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

内置 42+ 全球雪场（含室内），外置 JSON 可动态更新：

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
```

画像字段：city、level(beginner/intermediate/advanced/expert)、sport_type(ski/snowboard/both)、preferences(偏好标签数组)、budget_per_trip_cny、available_days、travel_dates、must_have、avoid、region_preference(中国/日本/韩国/欧洲/北美/南半球/不限)。

天气特色：按雪场山顶海拔获取、滑雪条件评分1-10（新雪+2/降雨-3/强风-3/过暖-2）、全球覆盖、免费无限调用。

---

## 通用规则

- 优先中文源（国内雪场），英文源（国际雪场），每次2-3组关键词
- 信息不足主动提问，输出结尾引导后续问题
- 价格标注币种和时间，国际价格附注原币
- **安全提醒**：建议购买滑雪专项险（国际需含救援）；检查天气雪况；必戴头盔

---

## 附加资源

- **共享工具层**：[scripts/utils.py](scripts/utils.py) — 统一路径/IO/工具函数
- **雪场数据库**：[scripts/resorts_db.json](scripts/resorts_db.json) — 42+ 全球雪场 JSON
- **雪场参考**：[resorts-reference.md](resorts-reference.md) — 详细雪场信息（攻略/早鸟规律/联票）
- **攻略模板**：[travel-guide.md](travel-guide.md)
- **汇率换算**：[scripts/currency_converter.py](scripts/currency_converter.py)
- **票价比价**：[scripts/ticket_comparator.py](scripts/ticket_comparator.py)
- **预售监听**：[scripts/presale_monitor.py](scripts/presale_monitor.py)
- **电子教练**：[scripts/ski_coach.py](scripts/ski_coach.py)
- **智能推荐**：[scripts/resort_recommender.py](scripts/resort_recommender.py) — 推荐/天气/对比/费用估算
- **手动预算**（仅用于用户提供具体费用明细时）：[scripts/budget_calculator.py](scripts/budget_calculator.py)
