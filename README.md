# ski-assistant

Global ski resort assistant for trip planning, pricing, coaching & presale monitoring.
全球滑雪综合服务助手 — 行程规划、智能查价、AI 电子教练、早鸟预售。

## v5.1.0 — 300+ Resorts

304 ski resorts across 27 countries. Knowledge-hub architecture, security-audited.
304 座雪场，覆盖 27 国。知识中枢架构，通过安全审查。

## Use Cases / 使用场景

Ski enthusiasts need a knowledgeable assistant for trip planning, price comparison, skill improvement, and finding deals. Here's what ski-assistant can do for you:

滑雪爱好者在规划行程、对比价格、提升技术、寻找优惠时，需要一个懂滑雪的助手：

### 1. Where to ski this weekend? / 周末不知道去哪滑？

**Smart recommendation + trip planning — 智能推荐 + 行程规划**

You might ask:
- "周末从北京出发，中级水平，推荐个雪场"
- "Recommend a ski resort near Beijing for beginners this weekend"
- "How much for a 5-day trip to Niseko for 2 people?"
- "去二世谷滑雪要花多少钱？2人5天"

What I'll do: Understand your skill level, budget, and schedule, then match from 300+ global resorts. You'll get a complete plan with transport, accommodation, gear checklist, and mountaintop weather forecast.

了解你的水平、预算、时间后，从 300+ 座全球雪场中智能匹配，输出包含交通、住宿、装备清单的完整方案，并附带山顶天气预报。

### 2. Lift tickets too expensive? / 雪票太贵？

**Multi-channel pricing + deal hunting — 三路径查价 + 低价捡漏**

You might ask:
- "万龙现在什么价？有没有残票转让"
- "Find discounted lift tickets for Wanlong"

What I'll do: Check three channels simultaneously — flyai for real-time flights/hotels, WebSearch for official ticket prices, social platforms for resale tickets. Automatic currency conversion for international trips.

同时查三个渠道 — flyai 实时机票酒店、WebSearch 官网雪票、社交平台转让票，帮你找到最优价格。涉及外币时自动换算。

### 3. Want to improve your technique? / 想提升滑雪技术？

**AI electronic coach — AI 电子教练**

You might ask:
- "帮我看看这张滑雪照片，姿态打个分"
- "Rate my skiing form from this photo"

What I'll do: Analyze your photos/videos across four dimensions (posture, turning, freestyle, overall), highlight strengths and areas for improvement, and track your progress over time.

分析你的照片/视频，按四维度（基础姿态、转弯技术、自由式、综合滑行）打分，指出亮点和改进建议，并记录进步轨迹。

### 4. When's the best time to buy? / 早鸟票什么时候买最划算？

**Presale monitoring — 预售监听**

You might ask:
- "万龙的早鸟票什么时候开售？帮我盯着"
- "When do early-bird passes go on sale?"

What I'll do: Share historical sale timelines, search for the latest season announcements, and compare single-trip vs multi-day vs season pass value. Add to watchlist for periodic checks and notifications.

告诉你历年开售时间规律，搜索当季最新公告，对比单次票/次卡/季卡的性价比。添加监听后，定期检查并通知你。

### 5. What to pack for an international trip? / 第一次外滑要准备什么？

**Gear guide + travel tips — 装备 + 攻略**

You might ask:
- "去北海道滑雪要带什么装备？"
- "What gear should I bring for a Japan ski trip?"

What I'll do: Based on your level and destination, list essential gear, clothing tips, visa/insurance reminders, local transport options, and cultural notes like onsen etiquette.

根据你的水平和目的地，列出必备装备、穿衣建议、签证/保险提醒、当地交通方式，以及温泉文化等本地贴士。

### 6. Mountain weather check / 查雪场天气

**Summit-level forecasts, not valley-town weather — 必须是山顶的**

You might ask:
- "查一下万龙未来7天的山顶天气"
- "Check the mountaintop weather at Wanlong for the next 7 days"

What I'll do: Query professional weather forecasts at the resort's summit elevation (not the town below), including snowfall, wind speed, visibility, and a ski condition rating.

查询雪场山顶海拔（而非山脚城镇）的专业天气预报，包括降雪量、风速、能见度，并给出滑雪条件评分。

## Quick Start / 快速开始

```bash
clawhub install ski-assistant
```

安装后直接对话即可开始，无需额外配置。Just start chatting — no configuration needed.

## Coverage / 覆盖范围

| Region / 区域 | Resorts / 雪场数 | Countries / 代表国家 |
|---------------|-----------------|---------------------|
| China / 中国 | 105 | 崇礼、北京、东北、新疆、四川 |
| Europe / 欧洲 | 99 | 法国、瑞士、奥地利、意大利、德国等 17 国 |
| Japan / 日本 | 44 | 北海道、长野、新潟、东北 |
| North America / 北美 | 33 | 科罗拉多、犹他、惠斯勒、佛蒙特 |
| Korea / 韩国 | 11 | 江原道平昌、旌善 |
| Southern Hemisphere / 南半球 | 11 | 新西兰、澳大利亚、智利、阿根廷 |
| Other / 其他 | 2 | 阿联酋（室内） |

## Data Storage / 数据存储

Default: `~/.ski-assistant/` (customizable via `SKI_ASSISTANT_DATA_DIR`). All data stored locally only, never uploaded.
默认 `~/.ski-assistant/`，可通过环境变量自定义。所有数据仅存储在用户本机。

## Support / 支持

If you like this project, please give it a star!
[![GitHub Stars](https://img.shields.io/github/stars/wjyhahaha/ski-assistant?style=social)](https://github.com/wjyhahaha/ski-assistant/stargazers)

如果你喜欢这个项目，请给它一个 Star！你的支持是我持续更新的动力。

## Changelog

- **v5.1.0** (2026-04-11): Bilingual frontmatter, 304-resort database (27 countries), expanded discovery regions, tightened allowed-tools
- **v5.0.1**: Restricted allowed-tools to specific scripts only
- **v5.0.0**: Knowledge-hub architecture refactor (10 scripts → 4 tools, 86% reduction)
- **v4.4.0**: Fixed ClawHub security review transparency issues
- **v4.3.0**: Local usage statistics
- **v4.2.0**: XHS sharing + international packages + price trends
- **v4.0.0**: 155-resort database + OSM discovery + mountain weather

## License

MIT
