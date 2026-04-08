---
name: ski-assistant
description: |
  全球滑雪综合服务助手，提供残票/低价票查找、早鸟预售、出行攻略、AI电子教练、智能雪场推荐、联网实时查价。
  当用户提到滑雪、雪票、雪场、外滑、早鸟票、残票、低价票、滑雪攻略、滑雪动作分析、推荐雪场、雪场天气、查价、滑雪预算时使用。
license: MIT
metadata:
  author: wjyhahaha
  version: 2.4.0
  category: travel-lifestyle
  tags: [skiing, travel, budget, weather, recommendation]
---

# Ski Assistant - 全球滑雪综合服务助手 v2.4.0

## 目标

一站式解决滑雪出行全链路需求：找低价票、盯早鸟预售、规划行程攻略、AI 分析滑雪姿态、智能推荐雪场、联网实时查价。覆盖中国（崇礼/东北/新疆/北京周边）、日本、韩国、欧洲、北美、南半球、室内雪场。

## 数据存储

用户数据存储在 `~/.ski-assistant/`（可通过 `SKI_ASSISTANT_DATA_DIR` 自定义），包括：
- `user_profile.json` — 用户画像（跨会话持久化）
- `records.json` — 电子教练滑雪记录
- `config.json` — 电子教练配置
- `watchlist.json` — 预售监听列表
- `custom_resorts.json` — 用户自定义雪场数据

内置雪场数据库：[scripts/resorts_db.json](scripts/resorts_db.json)（49+ 全球雪场），支持用户自定义扩展和 OSM 联网发现。

---

## 模块一：残票 / 低价票查找

**触发**：找便宜雪票、残票、转让票、低价票、折扣票、捡漏、雪票比价。

**流程**：
1. 确认目标雪场、日期、人数、预算
2. 基于 [references/resorts-reference.md](references/resorts-reference.md) 提供常规票价基准线
3. WebSearch 搜索：`"{雪场名} 雪票 转让"` / `"{雪场名} 残票"` / `"{雪场名} 特价票 {年份}"`
4. 按价格排列输出，标注来源和可信度，调用 [scripts/ticket_comparator.py](scripts/ticket_comparator.py) 生成比价表

**示例**：
> 用户："帮我找万龙的便宜雪票，1月15号去"
> AI 执行：确认人数和预算 → 查询万龙常规票价（约 ¥550-650/天）→ 搜索闲鱼/飞猪/小红书转让票 → 生成比价表 → 提醒二手票风险

**错误处理**：
- **搜索无结果**：说明该雪场/日期无转让票，建议关注官方促销或调整日期
- **价格信息冲突**：以官网价格为准，二手票标注"需自行验证"
- **国际汇率波动**：使用 [scripts/currency_converter.py](scripts/currency_converter.py) 获取实时汇率

**注意**：
- 提醒二手票风险，可信度不明标注"需自行验证"
- 国际价格用 [scripts/currency_converter.py](scripts/currency_converter.py) 换算为人民币

---

## 模块二：早鸟票预售体系

**触发**：早鸟票、预售、雪季卡、季卡、什么时候买划算、雪季规划。

**流程**：
1. 确认雪场、滑雪次数、预算
2. 基于 [references/resorts-reference.md](references/resorts-reference.md) 提供历年早鸟时间线和价格规律
3. WebSearch 搜索当季公告：`"{雪场名} 早鸟票 {年份}"`
4. 给出单次票 vs 次卡 vs 季卡性价比分析

**规律**：崇礼 4-6 月开售；东北 5-7 月；新疆 6-8 月；Ikon/Epic 3-4 月；日本 7-9 月。

### 预售监听

**触发**：帮我盯着、监听预售、自动通知、开售提醒。

**流程**：
1. 确认监听雪场、产品类型、通知渠道
2. 调用 `python scripts/presale_monitor.py watch '<json>'` 注册监听
3. 通过定时任务创建每日检查，调用 `presale_monitor.py check` 判断状态变化
4. 管理：`list` 查看、`status` 摘要、`remove` 移除、`check-all` 手动全量检查

**示例**：
> 用户："帮我盯着二世谷的早鸟票，开售了告诉我"
> AI 执行：调用 watch 注册监听 → 创建每日检查任务 → 状态变化时通过 IM 通知

**错误处理**：
- **监听列表为空**：提示用户先添加监听目标，或推荐当季热门早鸟票
- **公告页面结构变化**：自动降级为关键词搜索，并提示用户手动确认
- **通知渠道未配置**：输出到对话，建议配置 Webhook 实现自动推送

---

## 模块三：滑雪出行攻略

**触发**：外滑、滑雪旅行、去XX滑雪、滑雪攻略、行程规划。

**流程**：
1. 建立画像：水平、出发城市、时间天数、同行人数、预算、偏好
2. 调用 `python scripts/resort_recommender.py recommend` 获取推荐
3. WebSearch 补充交通、住宿、天气信息
4. 按 [references/travel-guide.md](references/travel-guide.md) 模板输出攻略

**示例**：
> 用户："周末想去崇礼滑雪，初学者，从北京出发"
> AI 执行：确认水平 → 推荐太舞/富龙 → 对比交通（高铁约 3h）→ 估算费用（¥1500-2500/人）→ 输出完整攻略

**错误处理**：
- **用户画像不完整**：引导式提问补充关键信息（城市/水平/预算），或使用默认值
- **推荐结果不符合预期**：调整权重参数重新推荐，或改用 `compare` 手动对比
- **国际信息缺失**：标注"需自行核实"，建议查阅目的地官网或旅行社

**攻略维度**：雪场对比、交通方案、住宿分档、装备清单、保险建议、美食推荐、签证（国际）、预算拆分。

**国际注意**：日本关注交通接驳+温泉；欧洲关注申根签+联票策略；北美关注 Ikon/Epic+自驾；南半球关注反季（6-10 月）。

---

## 模块四：AI 电子教练

**触发**：分析滑雪动作、看看姿态、滑雪打分、电子教练、视频分析、雪季总结、滑雪进步。

**流程**：
1. 用户提交滑雪照片/视频
2. 调用 `ski_coach.py analyze` 进行四维度评分
3. 输出评分结果（亮点/问题/改进建议）
4. 调用 `record` 保存记录，建立个人滑雪档案

### 单次分析

统一入口：`python scripts/ski_coach.py analyze '{"image":"/path/to/photo.jpg","resort":"万龙滑雪场","run":"银龙道","difficulty":"blue"}'`

**自动降级策略**：
1. 配置了外部 API Key → 脚本直接调用 API 分析并自动记录
2. 未配置 API Key（默认）→ 脚本返回 `agent_vision` 模式 JSON，Agent 按 `instruction` 指引完成分析并调用 `record` 保存

### 批量分析

`python scripts/ski_coach.py analyze-batch '{"images":["/1.jpg","/2.jpg"]}'` 或 `"dir":"/path/to/photos"` 扫描目录。

### 进步报告 & 雪季总结

- `progress` → 进步趋势，`season` → 雪季回顾，`stats` → 统计摘要

**示例**：
> 用户："帮我看看这张万龙银龙道的照片，姿态怎么样"
> AI 执行：调用 analyze → 四维度评分（基础姿态/转弯技术/自由式/综合）→ 给出亮点、问题和建议

### 评分体系（满分10分）

四维度：**基础姿态**（重心、膝盖、上半身）、**转弯技术**（平行站姿、立刃、换刃）、**自由式**（仅 park/mogul）、**综合**（速控、路线、地形适应）。

### 错误处理

- **照片模糊/角度不佳**：建议侧面 15-60 秒视频或清晰静态照片
- **未配置 API Key**：使用 Agent 自身视觉能力，按脚本输出的 instruction 指引完成
- **记录失败**：检查数据目录权限，或调用 `export` 备份后重新导入

### 命令参考

```bash
python scripts/ski_coach.py analyze  '<json>'  # 视觉分析
python scripts/ski_coach.py analyze-batch '<json>'  # 批量分析
python scripts/ski_coach.py record   '<json>'  # 记录结果
python scripts/ski_coach.py history  [json]    # 历史记录
python scripts/ski_coach.py progress [json]    # 进步报告
python scripts/ski_coach.py season   [json]    # 雪季总结
python scripts/ski_coach.py stats               # 统计摘要
python scripts/ski_coach.py show-config         # 查看配置
python scripts/ski_coach.py export   [path]    # 导出数据
python scripts/ski_coach.py import   <path>    # 导入数据
```

---

## 模块五：智能雪场推荐引擎

**触发**：推荐雪场、帮我选雪场、去哪滑雪好、雪场对比、雪场天气、滑雪预算。

### 核心流程

1. 确认/建立用户画像（城市、水平、运动类型、偏好、预算）
2. 调用 `python scripts/resort_recommender.py recommend` 获取推荐
3. 可选：查询天气 `weather`、估算费用 `costs`、多雪场对比 `compare`

**示例**：
> 用户："推荐几个适合中级单板的雪场，预算 5000"
> AI 执行：设置画像 → 多维度评分推荐 → 输出 Top 3（含费用、天气、交通提示）

### 关键命令

```bash
python scripts/resort_recommender.py profile '<json>'  # 设置画像
python scripts/resort_recommender.py show-profile       # 查看画像
python scripts/resort_recommender.py recommend [json]   # 推荐（top_n/include_weather/indoor_only）
python scripts/resort_recommender.py weather '<json>'   # 高山天气
python scripts/resort_recommender.py compare '<json>'   # 多雪场对比
python scripts/resort_recommender.py costs   '<json>'   # 费用估算
python scripts/resort_recommender.py update-db          # 更新数据库
python scripts/resort_recommender.py discover '<json>'   # 联网发现新雪场（OSM）
```

画像字段：city、level、sport_type、preferences、budget_per_trip_cny、available_days、region_preference。

### 错误处理

- **未设置画像**：自动输出引导信息（出发城市/水平/预算等 6 项）
- **非雪季**：自动推荐室内雪场，提示最佳出行时机
- **discover 无结果**：区域可能无未收录雪场，或网络问题

---

## 模块六：联网实时查价

**触发**：查一下去XX滑雪多少钱、实时价格、机票多少钱、酒店价格、帮我估算费用（实时）。

**流程**：
1. 确认出发地、目的地、日期、人数
2. 优先使用 `flyai-live` 联网查价（机票/酒店/雪票）
3. 无结果时自动降级为数据库参考价
4. 生成完整预算报告（含币种、时间、预订建议）

### 预算功能分工

| 功能 | 命令 | 适用场景 |
|------|------|---------|
| 自动费用估算 | `resort_recommender.py costs` | 只说雪场名和天数 |
| 手动预算计算 | `budget_calculator.py` | 已知每项费用明细 |
| 实时联网查价 | `price_fetcher.py flyai-live` | 需要实时机票/酒店 |

### 工作流

**首选（flyai 直连）**：
1. 调用 `python scripts/price_fetcher.py flyai-live '<json>'`
2. 自动生成报告（航班/酒店/雪票/预算汇总/预订链接）
3. 无结果时自动用数据库参考价兜底

**备选（WebSearch）**：
1. 调用 `python scripts/price_fetcher.py live-costs '<json>'` 获取搜索策略
2. Agent WebSearch 搜索交通、住宿、雪票
3. 调用 `python scripts/price_fetcher.py parse-results '<json>'` 生成预算报告

**示例**：
> 用户："帮我查下去北大湖滑雪要花多少钱，上海出发，1月15-18号，2个人"
> AI 执行：调用 flyai-live → 查询机票+酒店+雪票 → 生成完整预算报告

### 关键命令

```bash
python scripts/price_fetcher.py flyai-live '<json>'     # flyai 直连
python scripts/price_fetcher.py live-costs '<json>'     # WebSearch 策略
python scripts/price_fetcher.py search-queries '<json>' # 搜索关键词
python scripts/price_fetcher.py parse-results '<json>'  # 生成预算报告
```

参数：`resort`、`from_city`、`date_start`/`date_end`、`people`、`hotel_type`（可选）。

### 错误处理

- **flyai 未安装**：提示安装 `npm install -g @fly-ai/flyai-cli`，或改用 live-costs
- **某项查询无结果**：自动用数据库参考价兜底，标注"参考值（非实时）"
- **网络超时**：重试后仍失败，输出搜索策略让用户自行搜索

---

## 通用规则

- 优先中文源（国内雪场），英文源（国际雪场），每次 2-3 组关键词
- 信息不足主动提问，输出结尾引导后续问题
- 价格标注币种和时间，国际价格附注原币
- **安全提醒**：建议购买滑雪专项险（国际需含救援）；检查天气雪况；必戴头盔

## 常见问题

**Q: 雪票价格不是最新的怎么办？**
A: 内置数据库为参考值。使用 `flyai-live` 或 `live-costs` 获取实时价格，或手动搜索后传给 `parse-results`。

**Q: 电子教练没有配置 API Key 能用吗？**
A: 可以。默认使用 Agent 自身视觉能力，脚本输出分析指引，Agent 按指引完成分析后调用 `record` 保存。

**Q: 推荐结果不满意怎么办？**
A: 检查用户画像是否准确，调整后可重新推荐。也可用 `compare` 手动对比感兴趣的雪场。

**Q: 如何添加新雪场？**
A: 方式1：将 `custom_resorts.json` 放入 `~/.ski-assistant/`。方式2：运行 `discover` 从 OSM 发现新雪场。

## 附加资源

- **共享工具层**：[scripts/utils.py](scripts/utils.py)
- **雪场数据库**：[scripts/resorts_db.json](scripts/resorts_db.json)
- **雪场参考**：[references/resorts-reference.md](references/resorts-reference.md)
- **攻略模板**：[references/travel-guide.md](references/travel-guide.md)
- **装备清单**：[scripts/gear_guide.py](scripts/gear_guide.py)
- **汇率换算**：[scripts/currency_converter.py](scripts/currency_converter.py)
- **票价比价**：[scripts/ticket_comparator.py](scripts/ticket_comparator.py)
- **预售监听**：[scripts/presale_monitor.py](scripts/presale_monitor.py)
- **电子教练**：[scripts/ski_coach.py](scripts/ski_coach.py)
- **智能推荐**：[scripts/resort_recommender.py](scripts/resort_recommender.py)
- **联网查价**：[scripts/price_fetcher.py](scripts/price_fetcher.py)
- **手动预算**：[scripts/budget_calculator.py](scripts/budget_calculator.py)
