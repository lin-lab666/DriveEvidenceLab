# DriveEvidenceLab — Open-Source Final Acceptance Report

> 日期：2026-10-20 ｜ 版本：driveevidence 0.2.0（research preview RC）
> 性质：开源品质提升总任务的最终验收。对标对象：CornerCaseLab v0.3.0 公开版本。
> 前置报告：`docs/FINAL_ACCEPTANCE_REPORT.md`（2026-10-20 早间科研验收快照，其中测试数 144 为当时快照值）。

---

## 1. 任务完成情况

| 任务 | 内容 | 状态 |
|---|---|---|
| A 对标差距矩阵 | 抓取 CornerCaseLab 真实公开版本，20 维对比 | **完成** `docs/OPEN_SOURCE_QUALITY_AUDIT.md` |
| B README 升级 | 双语重写（定位/状态/Why/Features/Quick Start/SDK/CLI/图/结果/文档/局限/贡献），12 节结构 | **完成** README.md + README.zh-CN.md |
| C 四个真实 Demo | SDK 最小案例、Failure Discovery、Replay & Evidence、Programmatic Integration，全部真实执行 | **完成** examples/（4 个文件全部 exit 0） |
| D 真实可视化 | 4 图全部从归档 v2.1 产物生成，附生成脚本 + sources.json 溯源清单 | **完成** docs/_figures/ + scripts/make_figures.py |
| E 开发者体验 | Quick Start 逐条验证、CLI 参数与 README 核对、demo 自包含、示例提示补全 | **完成**（Red Team 逐项核对） |
| F 公开案例包 | examples/case_pack/：预构建证据 run + README + SHA256SUMS + 再生成脚本 `--check` | **完成**（audit/replay/校验和全过） |
| G 科研证据完整 | v1 撤回/v2.0 偏差/v2.1 主结果/证据束哈希/冻结数据全部保留，关键数字有自动一致性测试 | **完成**（156 项测试含 13 项数字锁定） |
| H 开源完整性 | 新增 SECURITY.md、CODE_OF_CONDUCT.md、NOTICE AI 披露、CITATION.cff 补 version | **完成** |
| I Red Team 终审 | 独立子智能体五面审查（技术/文档/可视化/安全/发布） | **完成**（0 blocker / 0 major / 5 minor 全修复） |

## 2. 实际运行命令与结果（本报告全部数字的来源）

| 验证 | 命令 | 结果 |
|---|---|---|
| 全量测试 | `python -m unittest discover -s tests -p "test_*.py"` | **Ran 156 tests — OK**（新增 test_open_source_quality.py 12 项） |
| Demo 1 | `python examples/minimal_sdk_example.py` | exit 0，Wilson CI 输出 |
| Demo 2 | `python examples/failure_discovery_demo.py` | exit 0，22 candidates / 32 episodes，yield 0.6875 [0.5143, 0.8205] |
| Demo 3 | `python examples/replay_evidence_demo.py` | exit 0，ledger PASS、manifest PASS、bit-exact replay True |
| Demo 4 | `python examples/programmatic_integration_demo.py` | exit 0，类型化结果 → 平铺字典 |
| 案例包审计 | `driveevidence audit --run examples/case_pack/run` | Ledger PASS / Manifest PASS |
| 案例包重放 | `driveevidence replay --run examples/case_pack/run --seq 1 --adapter builtin` | category match，metric diffs 全 0 |
| 案例包校验和 | `sha256sum -c examples/case_pack/SHA256SUMS` | 15/15 OK |
| 案例包再生成 | `python scripts/build_case_pack.py --check` | 13 episodes，mismatches 0 → **MATCH** |
| 证据束 | `python scripts/verify_evidence_bundle.py` | T1 全 PASS（260 ledger / 773 files / 统计重算一致） |
| 证据束确定性 | `python scripts/build_evidence_bundle.py --check` | **MATCH** |
| 图表再生成 | `python scripts/make_figures.py --out docs/_figures` | 4 图重生成，数字直接读自 summary.json |
| 隐私扫描 | `python scripts/privacy_scan.py --root <公开副本> --git` | CLEAN（0 findings） |
| CLI 冒烟 | 7 个子命令（doctor/sample/run/search/audit/replay/report） | 全部 exit 0 |
| wheel 构建 | `python -m build` | wheel + sdist 成功（version 0.2.0） |
| 干净 venv 安装 | 全新 venv + `pip install <wheel>` | version 0.2.0，SDK/CLI/示例可运行 |

## 3. 图表来源（全部可追溯）

| 图 | 数据来源 | 生成方式 |
|---|---|---|
| `trajectory_collision.png` | `runs/formal_experiment_v2p1/episodes/0001.json`（归档轨迹，scenario `rand_0003`） | `make_figures.py` 直接读取 |
| `gap_and_speed.png` | 同上 | 同上 |
| `search_comparison.png` | `runs/formal_experiment_v2p1/summary.json`（statistics.random/mutation，182/4096、1685/4096、57/64、61/64） | `make_figures.py` 直接读取（Red Team 审查后由硬编码常量改为真实读取） |
| `evidence_pipeline.png` | 示意图 | 明确标注 "Schematic diagram — not a measurement" |

`docs/_figures/sources.json` 记录逐图溯源（含归档文件名），`tests/test_open_source_quality.py` 强制图表存在且溯源指向 v2.1 run。

## 4. 干净环境验证

- 全新 venv 安装 wheel → `import driveevidence; __version__ == "0.2.0"`（importlib.metadata 单一来源）。
- 4 个 demo 在干净 venv 全部可运行（不依赖源码 checkout、私有路径或 `.workbuddy`）。
- 案例包的三种用法（audit / replay / `--check` 再生成）只依赖公开文件。

## 5. 隐私与安全检查

- `privacy_scan.py` 三面扫描（内容/路径名/git 历史 blob+元数据）+ 归档扫描：公开副本 **CLEAN**。
- git 提交元数据：全部 `DriveEvidenceLab Team <team@driveevidencelab.invalid>`（不可投递域）。
- 案例包内容无私有路径；`.workbuddy/`、`runs/` 被发布构建硬排除。
- 本轮修复的真实安全相关缺陷：案例包 CRLF/LF 行尾哈希不一致（新克隆会校验失败）——已在发布前修复（见 §7）。

## 6. 独立审查发现与修复记录

Red Team（独立 Explore 子智能体，只读）五面审查，判定 **0 blocker / 0 major / 5 minor / 4 nit**。全部 minor 与可行动 nit 已修复：

| # | 严重度 | 发现 | 修复 |
|---|---|---|---|
| 1 | MINOR | 两 README 链接 `docs/OPEN_SOURCE_FINAL_ACCEPTANCE.md` 不存在 | 创建本文件（任务 F 本就要求交付该文档） |
| 2 | MINOR | `make_figures.py` 的搜索对比图使用硬编码常量（数字当时正确但会漂移） | 改为直接读 `summary.json`，并重生成图表（数字逐位一致） |
| 3 | MINOR | 发布文档测试计数混乱（112/144/156 并存） | 面向前瞻的文档更新为 156；历史条目保留原值（历史记录不篡改），FINAL_ACCEPTANCE_REPORT 标注"时点快照" |
| 4 | MINOR | CITATION.cff 缺 `version` 且标题与 pyproject/README 不一致 | 补 `version: 0.2.0`，标题统一为 README 定位句 |
| 5 | MINOR | 轨迹图碰撞注释渲染在坐标轴外 | 修正注释坐标并重生成（已视觉确认） |
| 6 | NIT | `minimal_sdk_example.py` 文档串未说明需先安装包 | 补充说明 |
| 7 | NIT | `sources.json` 只记 scenario_id 不记归档文件名 | 补 `archive_file` 字段 |
| 8 | NIT | 间距公式隐含等车长假设无守卫 | 加显式断言 |
| （本轮自查发现） | MAJOR | 案例包 CRLF/LF 行尾与 `.gitattributes` 冲突：SHA256SUMS 记录 CRLF 哈希，新克隆（LF）校验必失败；manifest.json 亦为 CRLF | `build_case_pack.py` 发布前统一 LF + 重建 manifest；`manifest.py` 写文件固定 LF。修复后 audit/replay/校验和全 PASS |

## 7. 已知限制与未完成项

| 项 | 状态 |
|---|---|
| T3 外部独立复现 | 不具备（同作者/代码/机器），`verify_evidence_bundle.py` 输出如实标注 |
| Gate D（第二仿真系统） | PARTIAL（CommonRoad 交换验证通过，动力学仍为本项目） |
| CARLA | NOT VERIFIED |
| CI 徽章 / GitHub Release 页 | NOT VERIFIED（需真实仓库建立后确认；本地 CI 配置已核对） |
| `pyproject.toml` 仓库 URL | PLACEHOLDER（唯一发布阻塞，需用户提供真实地址） |
| license classifier 弃用警告 | 非阻塞，建议后续改 SPDX 表达式 |

## 8. 与 CornerCaseLab 对标后的水平判断

- 其公开交付要素（定位、状态、结果表、真实图表、Quick Start、布局说明、Limitations、Release 结构）本仓库全部具备。
- 本仓库超出对标的项：预构建可重放案例包（CornerCaseLab 不含 runs，我们提供 audit/replay/再生成三重验证）、图表逐图溯源清单 + 自动一致性测试、撤回披露与三层结论制度、双语 README 全节平行。
- 不对标项（刻意保持独立）：其研究方法（SNY）、实验规模、文案。

## 9. 结论

**本地可验证的全部发布标准已满足（任务书验收标准 1–16、19、20 项 PASS；17 项 RC 资源就绪；18 项 Red Team 发现全部修复）**。第 19 项的远程 CI 结果与 Release 页属 NOT VERIFIED，需仓库建立后确认。唯一阻塞公开发布的动作：用户提供真实 GitHub 仓库地址并授权创建远程仓库。
