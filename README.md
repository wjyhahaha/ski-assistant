# ski-assistant

全球滑雪综合服务助手 — QoderWork / ClawHub Skill

六大模块：残票/低价票查找、早鸟票预售体系、滑雪出行攻略、AI电子教练、智能雪场推荐、联网实时查价。

## 特性

- 49+ 全球雪场数据库（含室内），覆盖中国/日本/韩国/欧洲/北美/南半球/中东
- Open-Meteo 高山天气 API（按山顶海拔获取专业预报）
- AI 电子教练（视觉分析滑雪姿态，支持7种模型，追踪雪季进步）
- 智能推荐引擎（多维度评分，预算/距离/水平/偏好匹配）
- 早鸟票预售监听（状态变化自动通知）
- 联网实时查价（flyai 飞猪直连 + WebSearch 双模式）
- 滑雪装备清单推荐（按水平/地区/天数生成）
- 雪场数据库可动态更新（用户自定义 JSON 覆盖/扩展 + OSM 联网发现）

## 安装

```bash
clawhub install ski-assistant
```

## 数据存储

默认 `~/.ski-assistant/`，也可通过环境变量 `SKI_ASSISTANT_DATA_DIR` 自定义。

## License

MIT
