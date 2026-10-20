# Open-Source Quality Audit — DriveEvidenceLab vs CornerCaseLab

> 日期：2026-10-20 ｜ 对标对象：https://github.com/lin-lab666/CornerCaseLab（v0.3.0 公开版本）
> 性质：**交付品质对标**，不是研究方法、实验规模或宣传文案的复制。
> 方法：实际抓取 CornerCaseLab 公开首页与 Releases 页内容，逐项与本仓库现状对比。
> 纪律：已达标的项保留现状，不重复开发；缺口逐项给出修复动作与验证证据。

---

## 1. 差距矩阵

| # | 维度 | CornerCaseLab v0.3.0 公开版本 | DriveEvidenceLab 改造前 | 缺口 | 修复动作 | 状态 | 验证证据 |
|---|---|---|---|---|---|---|---|
| 1 | 首页定位一句话 | "Budget-aware scenario testing…"，一句话讲清是什么 | 有（"evidence-driven falsification…"）但偏研究叙事 | 表述未对齐工具定位 | 双语 README 顶部改为 "Reproducible Driving Failure Discovery & Evidence Toolkit" | 完成 | README.md L3 |
| 2 | 项目状态（版本/Python/许可证） | 首页含状态声明、固定依赖版本 | 无状态表，散落在正文 | 缺集中状态视图 | 新增 Project status 表（版本/Python/License/测试/后端） | 完成 | README.md "Project status" |
| 3 | CI/覆盖率徽章 | 无虚假徽章（诚实） | 无徽章 | 不需虚假徽章；CI 徽章须等仓库建立 | 状态表明确写 "CI badge pending first public repository"，不伪造 | 完成 | README.md |
| 4 | Why 章节 | Overview 讲清研究问题与权衡 | "What it does" 偏功能列表 | 缺"为什么值得用"的开发者视角 | 新增 "Why DriveEvidenceLab?" 五点价值主张（与实际功能一一对应） | 完成 | README.md |
| 5 | Features 分级 | 未显式分级（正文区分 building blocks vs formal） | 无分级 | 正式/实验/部分/未实现边界不清 | 新增 Features 表（Supported/Experimental/Partial/Not implemented） | 完成 | README.md "Features" |
| 6 | Quick Start 可执行性 | `start.ps1` 一键 + 手动命令，固定依赖版本 | 有 Quickstart 但从源码安装为主 | 缺 wheel 安装路径 | Quick Start 改为 wheel 优先 + 源码备选，6 步安装→搜索→审计→重放→报告 | 完成 | 干净 venv 验证（见验收报告 §3） |
| 7 | Python SDK 示例上首页 | 无 SDK 示例（CLI 为主） | 仅有 `examples/` 指引 | 首页无代码 | 首页嵌入真实可运行 SDK 片段 + 4 demo 索引表 | 完成 | 4 个 demo 全部实际运行通过 |
| 8 | CLI 示例 | CLI 命令含 replay/confirm | Quickstart 内嵌 CLI | 命令清单不直观 | 新增 7 子命令用途表（双语） | 完成 | README.md "CLI" |
| 9 | 真实图表展示 | 多张正式图表（PNG+PDF）+ 图注 | **零图表** | 最大差距 | `scripts/make_figures.py` 从 v2.1 归档产物生成 4 图（轨迹/间距速度/搜索对比/流程示意），README 嵌入 | 完成 | docs/_figures/ + sources.json 溯源清单 |
| 10 | 正式结果表格 | 表格 + CI + 明确"无 p 值"声明 | 已有结果表（原本就有） | 无缺口 | 保留；仅补充 "H2 是未检出非等价" 一句话解读 | 完成（保留） | README.md "Results & Evidence" |
| 11 | 局限披露 | 8 条编号 Limitations | 已有详细 LIMITATIONS.md | 首页缺简版 | 首页加 5 条简版 + 链接完整披露 | 完成 | README.md "Limitations" |
| 12 | 撤回/纠错历史 | 无撤回（未披露于首页） | 已有撤回章节（诚实，超出对标） | 无缺口 | 保留并双语化 | 完成（保留） | README.md "A retraction…" |
| 13 | 仓库布局说明 | Repository layout 代码块 | 已有 Project layout | 无缺口 | 保留 | 完成（保留） | README.md |
| 14 | 文档导航 | docs/ + RESULTS_INTERPRETATION 链接 | 已有文档表 | 少两份新文档入口 | 文档表补 QUALITY_AUDIT / FINAL_ACCEPTANCE | 完成 | README.md "Documentation" |
| 15 | 可复现性声明 | PUBLIC_RELEASE.md 来源披露 | 已有 D024 脱敏方案 | 无缺口 | 保留（验收报告有完整说明） | 完成（保留） | docs/ACCEPTANCE_AND_RELEASE.md |
| 16 | Release Notes 质量 | Highlights + 结果摘要 + 可复现性 + License | 已有 RELEASE_NOTES 草稿 | 需对齐 RC 包结构 | RC 含 wheel/sdist/SHA256SUMS/公开来源说明 | 完成 | 发行候选（验收报告 §7） |
| 17 | 公开可重放案例 | 无公开证据包（runs 不入库，明确说明） | 无 | 两者都无；我们补上 | `examples/case_pack/`：预构建证据 run + README + SHA256SUMS + 再生成脚本 `--check` | 完成 | audit PASS / replay 位级一致 / SHA256SUMS 全 OK / --check MATCH |
| 18 | 开源完整性文件 | LICENSE/Attribution | 有 LICENSE/NOTICE/CONTRIBUTING/CITATION/模板 | 缺 CODE_OF_CONDUCT、SECURITY.md | 新增两文件；NOTICE 补 AI 辅助披露 | 完成 | 仓库根目录 |
| 19 | 图表生成脚本可复现 | render 脚本在 scripts/ | — | —（新交付即有） | `make_figures.py` 确定性可重跑，含 sources.json 溯源 | 完成 | 重跑输出一致 |
| 20 | AI 辅助开发披露 | 无（未披露） | 无 | 任务书要求披露 | NOTICE 增补披露段 | 完成 | NOTICE |

## 2. 结论

- **改造前主要缺口**：零可视化、无状态总览、无 Features 分级、无 SDK 上手路径、无公开可重放案例包、缺 CODE_OF_CONDUCT/SECURITY。
- **对标后**：CornerCaseLab 具备的公开交付要素（定位、状态、结果表、图表、Quick Start、布局、Limitations、Release 结构）DriveEvidenceLab 全部具备或以更严格形式具备（预构建案例包、图表溯源清单、撤回披露、三层结论制度为超出对标的加分项）。
- **刻意不对标的部分**：其实验规模（60,000 episodes）、研究方法（SNY 指标）、文案——保持本项目的独立定位。
- **诚实边界**：CI 徽章、GitHub Release 页、外部复现（T3）在公开仓库建立前均为 NOT VERIFIED，未伪造。
