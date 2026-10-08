# 选品分析师

> **给结论不给仪表盘，把生意参谋/蝉妈妈翻译成决策**

![选品分析师 · 动态演示](docs/assets/hero.gif)

*▲ 实时演示（自动循环）· [▶ 观看完整版合集视频](docs/demo.mp4)*


[![Stage](https://img.shields.io/badge/stage-P1-orange)](https://github.com/bangwozuo)
[![Asset](https://img.shields.io/badge/asset-prompt--only-blueviolet)](#资产形态)
[![NoKey](https://img.shields.io/badge/API%20Key-not%20required-success)](#资产形态)
[![License](https://img.shields.io/badge/license-Apache--2.0-green)](LICENSE)

---

## 它是谁

面向 **电商小卖家** 的数字员工资产包。

| 项目 | 内容 |
|------|------|
| 目标用户 | 有数据意识的腰部卖家（约占 20-30%，据R3调研） |
| 交付物 | 周报采纳率 ≥60%；选中款 30 天动销率 ≥50%；竞品异动推送 ≤2 小时 |
| 技能数 | 5 |
| 工作流数 | 5 |
| 旧名存档 | `选品分析师·小察` |

---

## 资产形态

**纯提示词资产** —— 这是理解本仓库的关键：

| 特性 | 说明 |
|------|------|
| ✅ 无需 API Key | 一个 Key 都不需要 |
| ✅ 无需部署 | 没有服务端，没有脚本 |
| ✅ 无需依赖 | 克隆后用文本编辑器就能看 |
| ✅ 平台无关 | 粘贴到任何 AI 工具即可使用 |
| ✅ 用户自备算力 | 模型来自你自己的订阅 |

---

## 快速开始

```text
1. 打开 skills/category-trend-collect/prompt.txt
2. 全文复制
3. 粘贴到你常用的 AI 工具（Coze / WorkBuddy / Dify / Claude / ChatGPT）
4. 按 SKILL.md 的输入规格提供数据
```

就这四步。完整指引见 [使用手册](docs/04-usage.md)。

---

## 仓库结构

```text
product-research-zh/
├── README.md / employee.md / package.yaml     # 入口与 12 字段定义卡
├── docs/01~07                                 # 员工级文档（架构/流程/场景/手册/示例/录像/测试）
├── skills/                                    # 5 个原子技能
│   └── <skill>/
│       ├── README.md  SKILL.md  prompt.txt  schema.json  examples/
│       └── docs/                              # 该技能自己的 10 项文档 + 配图
├── workflows/                                 # 5 条工作流（复合技能）
│   └── <workflow>/
│       ├── README.md  SKILL.md  prompt.txt  schema.json  examples/
│       └── docs/                              # 该工作流自己的 10 项文档 + 配图
├── knowledge/                                 # RAG wiki 知识库
│   ├── README.md  RAG-接入指南.md  template.md
│   └── wiki/(index.md, _template.md, entries/)
├── connectors/                                # 连接器说明 + 合规红线
├── quality/                                   # 效果基线与追踪日志
└── tests/                                     # 资产校验测试（离线，无需密钥）
```

### 每个技能 / 工作流自带的 docs

| 文档 | 内容 |
|------|------|
| `README.md` | 资产速览与快速开始 |
| `docs/01-usage-manual.md` | 安装使用手册 |
| `docs/02-architecture.md` | 业务架构图 |
| `docs/03-flow.md` | 流程图（Mermaid + 配图） |
| `docs/04-examples.md` | 使用示例 |
| `docs/05-media.md` | 截图和录屏（清单 + 分镜脚本） |
| `docs/06-scenarios.md` | 使用场景（适用 / 不适用） |
| `docs/07-audience.md` | 用户群体 |
| `docs/08-value.md` | 解决问题与价值 |
| `docs/09-test-report.md` | 测试报告 |
| `docs/assets/overview.svg` | 自动生成的流程示意图 |

---

## 交付物导航

| 文档 | 内容 |
|------|------|
| [业务架构](docs/01-architecture.md) | 四层架构 + 数据流 + 能力边界 |
| [工作流流程](docs/02-workflow.md) | 5 条工作流的 DAG 可视化 |
| [使用场景](docs/03-scenarios.md) | 3 个真实场景（含前后对比） |
| [使用手册](docs/04-usage.md) | 各平台导入指引 + 常见问题 |
| [示例库](docs/05-examples.md) | 5 组输入输出示例 |
| [录像脚本](docs/06-recording-script.md) | 7 镜头分镜 + 旁白稿 |
| [校验报告](docs/07-test-report.md) | 资产质量校验结果 |

---

## 技能清单（5 个）

| # | 技能 | 能力族 | 复杂度 | 提示词 | 文档 |
|---|------|--------|--------|--------|------|
| 1 | 类目趋势采集 | 数据采集 | `M` | [prompt.txt](skills/category-trend-collect/prompt.txt) | [docs](skills/category-trend-collect/docs/) |
| 2 | 竞品动态摘要 | 摘要提炼 | `M` | [prompt.txt](skills/competitor-digest/prompt.txt) | [docs](skills/competitor-digest/docs/) |
| 3 | 关键词机会评分 | — | `S` | [prompt.txt](skills/keyword-opportunity-score/prompt.txt) | [docs](skills/keyword-opportunity-score/docs/) |
| 4 | 利润测算 | 测算评估 | `S` | [prompt.txt](skills/profit-calculate/prompt.txt) | [docs](skills/profit-calculate/docs/) |
| 5 | 机会简报生成 | 报告简报 | `S` | [prompt.txt](skills/opportunity-brief-generate/prompt.txt) | [docs](skills/opportunity-brief-generate/docs/) |

## 工作流清单（5 条）

| # | 工作流 | 阶段 | 复杂度 | 触发 | 定义 | 文档 |
|---|--------|------|--------|------|------|------|
| 1 | 类目热词与趋势采集 | `P1` | `M` | 定时（每日） | [SKILL.md](workflows/category-hotword-trend-flow/SKILL.md) | [docs](workflows/category-hotword-trend-flow/docs/) |
| 2 | 竞品上架与价格监控 | `P1` | `M` | 定时（每 2 小时） | [SKILL.md](workflows/competitor-price-monitor-flow/SKILL.md) | [docs](workflows/competitor-price-monitor-flow/docs/) |
| 3 | 蓝海关键词挖掘 | `P1` | `S` | 定时（每周） | [SKILL.md](workflows/blueocean-keyword-mine-flow/SKILL.md) | [docs](workflows/blueocean-keyword-mine-flow/docs/) |
| 4 | 选品打分卡 | `P1` | `S` | 人工 | [SKILL.md](workflows/product-scoring-card-flow/SKILL.md) | [docs](workflows/product-scoring-card-flow/docs/) |
| 5 | 周度机会简报 | `P1` | `S` | 定时（周一） | [SKILL.md](workflows/weekly-opportunity-brief-flow/SKILL.md) | [docs](workflows/weekly-opportunity-brief-flow/docs/) |

---

## 知识库与连接器

| 目录 | 说明 |
|------|------|
| [`knowledge/`](knowledge/README.md) | RAG wiki 知识库：填入业务信息可显著提升输出质量 |
| [`connectors/`](connectors/README.md) | 连接器说明：数据从哪来、怎么合规地来 |

---

## 资产校验

```bash
pip install -r requirements.txt
pytest tests/ -v
```

校验技能完整性、提示词结构、契约一致性、工作流 DAG、技能级与工作流级 docs 完整性、知识库 wiki 与连接器结构。
**不需要任何 API Key。**

---

## 合规声明

- ✅ 所有输出为 **AI 辅助生成**，交付前须人工审核
- ✅ 提示词内置**违禁词禁止清单**，符合《广告法》要求
- ✅ 遵循《人工智能生成合成内容标识办法》
- ✅ 连接器只走**官方 API** 或**用户导出数据**
- ✅ 所有对外发布动作**保留人工确认环节**

---

## 许可

[Apache-2.0](LICENSE) — 可自由使用、修改、商用

---

*由 bangwozuo 业务库自动生成 · 2026-09-29*
