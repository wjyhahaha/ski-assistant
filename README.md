# ski-assistant

全球滑雪综合服务助手 — QoderWork / ClawHub Skill

## v5.0.0 — 知识中枢架构

从 10 个 Python 脚本（6,751 行）重构为「知识中枢 + 4 个轻量工具」架构（924 行），代码量减少 86%。通过 ClawHub 安全审查。

## 特性

- 155 座全球雪场数据库，覆盖 19 个国家（含室内雪场）
- Open-Meteo 高山天气 API（按山顶海拔获取专业预报）
- AI 电子教练（Agent 原生视觉分析，四维度评分）
- 三路径智能查价（flyai 机票酒店 + WebSearch 雪票 + 社交平台残票）
- 早鸟票预售监听（WebSearch + 定时检查）
- OpenStreetMap 雪场发现（Overpass API）
- 装备/预算/攻略知识库（Markdown 参考文档）

## 架构

```
SKILL.md              ← 知识中枢（业务逻辑 + 调度规则）
data/resorts_db.json  ← 155 座雪场结构化数据
references/           ← 5 个知识库文档
tools/                ← 4 个轻量 Python 工具（共 924 行）
```

## 安装

```bash
clawhub install ski-assistant
```

## 数据存储

默认 `~/.ski-assistant/`，可通过 `SKI_ASSISTANT_DATA_DIR` 环境变量自定义。所有数据仅存储在用户本机。

## License

MIT
