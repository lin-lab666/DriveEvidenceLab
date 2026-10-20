# DriveEvidenceLab

**可复现的驾驶失效发现与证据工具包（Reproducible Driving Failure Discovery & Evidence Toolkit）**

*仅限仿真研究的工具包——不是安全认证系统，不做任何真实道路安全性声明。*

DriveEvidenceLab 在驾驶仿真中发现失效场景，将其归档为**防篡改证据**，并回答大多数
基准测试跳过的问题：**发现的失效真的可复现吗，还是某个精确配置下的"刀锋"假象？**

[English](README.md) · [API](docs/API.md) · [架构](docs/ARCHITECTURE.md) · [局限](docs/LIMITATIONS.md) · [质量对标](docs/OPEN_SOURCE_QUALITY_AUDIT.md)

**项目状态**

| | |
|---|---|
| 版本 | `0.2.0`（research preview） |
| Python | 3.10 – 3.13 |
| 许可证 | Apache-2.0 |
| 测试 | 本地 156 项通过（`python -m unittest discover -s tests`）——CI 徽章待首个公开仓库建立后添加 |
| 仿真后端 | builtin 运动学（`builtin/1.1`）；CommonRoad 交换已验证；CARLA 未实现 |

---

## 为什么需要 DriveEvidenceLab？

自动驾驶仿真研究"跑起来容易，信起来难"。搜索脚本产出的一个"碰撞"，只有当别人能
重跑完全相同的场景、检查证据、确认没有事后篡改时才有意义。DriveEvidenceLab
围绕这条信任链构建：

- **系统化失效发现**——两种预算对齐的搜索策略（随机先验 vs 归档变异）在共享记账
  规则下探索场景空间并提名失效。
- **严格重放**——每个归档失效都可逐位重跑：同场景哈希、同种子、同规划器、同结果。
- **可核验证据**——只追加的 SHA-256 哈希链账本 + 全量清单，让篡改**可被检测**，
  而不只是被劝阻。
- **Python SDK 集成**——类型化结果对象（`EpisodeResult`、`SearchReport`）可直接
  进入 pandas、pytest 或你自己的流水线。
- **适配器接口**——一份场景 IR（`ir/v1`）+ 一套适配器协议；今天是 builtin 运动学
  后端，明天接入更多后端不需要重写你的分析代码。

## 功能矩阵

| 能力 | 状态 |
|---|---|
| 规范场景 IR（`ir/v1`）+ 确定性哈希 | **正式支持** |
| RandomSearch / MutationSearch（共享预算记账） | **正式支持** |
| ε-扰动稳定性留出验证 | **正式支持** |
| 哈希链账本 + 清单 + 逐位重放 | **正式支持** |
| Markdown / HTML 运行报告 | **正式支持** |
| CLI（7 个子命令）+ Python SDK | **正式支持** |
| HighwayEnv 适配器 | **实验性**——可运行，不与 builtin 结果合并 |
| CommonRoad XML 交换 | **部分**——仅判定层，无第三方动力学 |
| CARLA 适配器 | **未实现** |
| Web UI / GUI | **未实现** |

## 快速开始

```bash
# 1. 安装（Python 3.10–3.13）
python -m venv .venv && .venv\Scripts\activate        # Windows；Linux/macOS: source .venv/bin/activate
pip install driveevidence                             # 从发布 wheel 安装；或：
# pip install -e ".[sim,dev]"                         # 从源码检出安装

# 2. 环境自检
driveevidence doctor

# 3. 运行一次真实的失效发现搜索（含证据归档）
#    （种子 2101 确定性地产生失效；2100 是已知的零候选种子）
driveevidence search --method mutation --adapter builtin --budget 64 --seed 2101 \
                     --run-id my_search --out runs

# 4. 审计证据（账本哈希链 + 清单）
driveevidence audit --run runs/my_search

# 5. 逐位重放一个归档失效
driveevidence replay --run runs/my_search --seq 1 --adapter builtin

# 6. 生成报告
driveevidence report --run runs/my_search --format html --out runs/my_search/report.html
```

更省事的方式：仓库自带一个预构建的证据案例包。

```bash
driveevidence audit  --run examples/case_pack/run          # 核验随仓库分发的证据
driveevidence replay --run examples/case_pack/run --seq 1 --adapter builtin
python scripts/build_case_pack.py --check                   # 重新生成并比对
```

## Python SDK

一段真实可运行的端到端会话——加载场景、执行回合、搜索失效、计算置信区间
（来自 [`examples/minimal_sdk_example.py`](examples/minimal_sdk_example.py)）：

```python
from driveevidence.scenario import ScenarioIR
from driveevidence.search import Budget, RandomSearch
from driveevidence.sim import create_adapter, list_adapters
from driveevidence.stats import wilson_ci

scenario = ScenarioIR.from_dict({...})          # 规范 ir/v1 JSON
adapter  = create_adapter("builtin")            # 或 "highwayenv" / "commonroad"

result = adapter.run_episode(scenario, seed=123, planner_name="safe_follow")
print(result.failure_category, result.metrics)  # 类型化、带哈希的结果

report  = RandomSearch().search(adapter=adapter, budget=Budget(max_episodes=32),
                                master_seed=42)
lo, hi  = wilson_ci(len(report.candidates), report.budget_snapshot["launched"])
```

更多可运行的示例：

| 示例 | 文件 | 展示内容 |
|---|---|---|
| SDK 最小案例 | [`examples/minimal_sdk_example.py`](examples/minimal_sdk_example.py) | 场景 → 回合 → 搜索 → Wilson CI |
| 失效发现 | [`examples/failure_discovery_demo.py`](examples/failure_discovery_demo.py) | 固定种子搜索、类别汇总、零候选处理 |
| 重放与证据 | [`examples/replay_evidence_demo.py`](examples/replay_evidence_demo.py) | 归档 → 审计 → 逐位重放 → 清单校验 |
| 编程集成 | [`examples/programmatic_integration_demo.py`](examples/programmatic_integration_demo.py) | 类型化结果 → 平铺字典 → 你的分析栈 |

## CLI

七个子命令，一种证据格式：

```text
driveevidence doctor    环境诊断（安装方式、适配器、可选依赖）
driveevidence sample    生成示例场景 JSON
driveevidence run       执行单回合并归档证据
driveevidence search    执行预算化失效发现搜索
driveevidence audit     校验账本哈希链 + 清单哈希
driveevidence replay    精确重放一个归档回合
driveevidence report    从运行产物生成 Markdown / HTML 报告
```

## 结果长什么样

来自归档运行的真实输出（由
[`scripts/make_figures.py`](scripts/make_figures.py) 生成——每个数字都可
追溯到 `runs/formal_experiment_v2p1/`，无任何人工调整值）：

![失效轨迹](docs/_figures/trajectory_collision.png)

![间距与速度](docs/_figures/gap_and_speed.png)

![搜索对比](docs/_figures/search_comparison.png)

![证据流水线](docs/_figures/evidence_pipeline.png)

## 结果与证据

正式协议 v2.1（冻结预注册），后端 `builtin/1.1`，8192 个发现回合 + 384 个
ε-扰动留出回合：

| 方法 | 发现率 [Wilson 95%] | 测试数 | 稳定 | 稳定率 [Wilson 95%] |
|---|---|---|---|---|
| random | 0.0444 [0.0385, 0.0512] | 64 | 57 | **0.8906 [0.7910, 0.9460]** |
| mutation | 0.4114 [0.3964, 0.4265] | 64 | 61 | **0.9531 [0.8710, 0.9839]** |

| 假设 | 结果 |
|---|---|
| H1 — 随机搜索稳定率 > 0.1 | **支持**（Wilson 下界 0.791） |
| H2 — mutation 与 random 稳定率差异 | **未检出**（Δ=+0.0625，Newcombe 95% CI [−0.0365, +0.1668] 跨 0） |
| H3 — mutation 发现率更高 | **支持**（Δ=+0.3669，配对 bootstrap 95% CI [0.3218, 0.4124]） |

正确解读：*mutation 每个 episode 发现的失效多得多，但两方法找到的失效对扰动的
稳健程度大致相当。* H2 是"未检出差异"，**不是**"两方法等价"。

不必信任我们，自己核验每个数字：

```bash
python scripts/verify_evidence_bundle.py
```

它会走查哈希链、对清单核验 773 个文件，并从原始产物**重算**所有头条统计量。

### 你应该知道的一次撤回

协议 v1 曾报告 random 占优的稳定率（0.111 vs 0.010）。该结果已被**撤回**：审计发现
仿真器创建了 RNG 但从未使用，导致 1716 个候选在三个"独立"留出种子下逐位相同——
100% 稳定率是同义反复。撤回过程、修正后的协议（v2/v2.1）与完整审计见
[`docs/SCIENTIFIC_AUDIT.zh-CN.md`](docs/SCIENTIFIC_AUDIT.zh-CN.md)。v1 原始产物
保留在证据束中，未被修改。

## 文档

| 文档 | 内容 |
|---|---|
| [`docs/API.md`](docs/API.md) | 公共 API 参考（含可运行示例） |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | 分层、契约、数据流 |
| [`docs/LIMITATIONS.md`](docs/LIMITATIONS.md) | 完整的范围与局限披露 |
| [`docs/SCIENTIFIC_AUDIT.zh-CN.md`](docs/SCIENTIFIC_AUDIT.zh-CN.md) | 撤回 v1、验证 v2 的审计 |
| [`docs/PROTOCOL-frozen-v2.md`](docs/PROTOCOL-frozen-v2.md) | 正式结果使用的预注册协议 |
| [`docs/DECISIONS.md`](docs/DECISIONS.md) | 工程与科研决策日志 |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | 贡献与科研诚信规则 |
| [`docs/OPEN_SOURCE_QUALITY_AUDIT.md`](docs/OPEN_SOURCE_QUALITY_AUDIT.md) | 开源质量对标报告 |

## 局限（简版）

- **仅限仿真。** 不做、也不支持任何实车或道路安全声明。
- **场景族极窄。** 直道三车道、单车前车、规则规划器。结果不外推到该族之外。
- **H2 是"未检出"，不是"无差异"**——64 对样本无法分辨 6 个百分点的差异。
- **尚无外部复现（T3）。** 全部产物来自同一作者、代码库与机器。内部审计通过 ≠
  独立验证。
- **CommonRoad 是部分的**（交换已验证，动力学仍是本项目的）；**CARLA 未实现**。

完整逐项披露：[`docs/LIMITATIONS.md`](docs/LIMITATIONS.md)。

## 参与贡献

欢迎 Issue 与 Pull Request——见 [`CONTRIBUTING.md`](CONTRIBUTING.md) 与
[`docs/OPEN_SOURCE_FINAL_ACCEPTANCE.md`](docs/OPEN_SOURCE_FINAL_ACCEPTANCE.md)
（每次改动都应通过的验证步骤）。

## 许可证

Apache-2.0——第三方归属与 AI 辅助开发披露见 [`LICENSE`](LICENSE) 与 [`NOTICE`](NOTICE)。
安全政策见 [`SECURITY.md`](SECURITY.md)，社区准则见 [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md)。

## 引用

```bibtex
@software{driveevidence2026,
  title  = {DriveEvidenceLab: Reproducible Driving Failure Discovery and Evidence Toolkit},
  author = {DriveEvidenceLab Team},
  year   = {2026},
  note   = {Simulation-only research software; protocol v2.1 results; no external replication yet},
  url    = {https://github.com/lin-lab666/DriveEvidenceLab}
}
```
