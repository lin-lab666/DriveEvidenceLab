# 架构说明（Architecture）

> 适用版本：driveevidence 0.2.0　｜　最后更新：2026-10-19

## 1. 一句话定位

DriveEvidenceLab 是一个**仅限仿真**的自动驾驶证伪研究工具包：它把「场景定义 → 搜索 → 仿真执行 → 失效发现 → 统计 → 证据持久化 → 完整性校验 → 重放复现 → 结论审计」串成一条可核查的流水线，并且**强制把"数据完整"与"结论有效"分开陈述**。

## 2. 分层结构

```
┌──────────────────────────────────────────────────────────────────┐
│ 表示层    cli/main.py            report/generator.py             │
│          doctor sample run search audit replay report            │
├──────────────────────────────────────────────────────────────────┤
│ 研究层    search/{base,random_search,mutation_search}.py          │
│          stats/estimators.py                                     │
├──────────────────────────────────────────────────────────────────┤
│ 证据层    evidence/{ledger,episode_store,manifest,replay,        │
│                     recorder}.py                                 │
├──────────────────────────────────────────────────────────────────┤
│ 仿真层    sim/{base,builtin,highwayenv_adapter}.py                │
│          planners/rule_based.py                                  │
├──────────────────────────────────────────────────────────────────┤
│ 契约层    scenario/{ir,perturb}.py                               │
└──────────────────────────────────────────────────────────────────┘
```

依赖方向严格自上而下。**契约层不依赖任何上层**，因此可以独立被第三方复用。

## 3. 关键契约

### 3.1 `ScenarioIR`（`scenario/ir.py`，`ir/v1`）

- 单位固定：m、s、m/s、rad；x 沿道路正向，y 横向左正。
- 只支持直道；曲线必须被 `validate()` 拒绝。
- `scenario_hash` 是 canonical JSON 的 SHA-256，**跨进程稳定**，是候选去重、证据索引与复现比对的唯一键。
- `validate()` **只做几何/语义合法性**，不做安全判定——这是刻意的职责分离：`INFEASIBLE` 不等于"安全"。

### 3.2 `SimulatorAdapter`（`sim/base.py`）

```python
class SimulatorAdapter(ABC):
    name: str
    version: str
    def capabilities(self) -> Dict[str, bool]: ...
    def run_episode(self, scenario, seed, planner_name, config) -> EpisodeResult: ...
```

- `capabilities()` 必须**如实声明**该后端真正支持的检测项；不支持就写 `False`，禁止虚报。
- `run_episode` 对非法场景**不抛异常**，而是返回 `failure_category=INFEASIBLE` 的 `EpisodeResult`，保证"失败也入账"。
- 注册机制：`@register_adapter` + `create_adapter(name)`。

### 3.3 `FailureCategory` 语义分级

| 类别 | 含义 | 计入 failure？ |
|---|---|---|
| `COLLISION` / `OFF_ROAD` / `RULE_VIOLATION` / `NEAR_MISS` | 安全相关失效 | **是** |
| `INFEASIBLE` | 场景本身非法，未真正运行 | 否（但入账） |
| `SIMULATOR_ERROR` | 后端异常 | 否（但入账，且必须单独报告） |
| `TIMEOUT` | 达到步数上限未终止 | 否（但入账） |
| `NONE` | 正常结束 | 否 |

这个分级是统计有效性的基础：把 `TIMEOUT` 当 failure 会人为抬高失效率，把 `INFEASIBLE` 从分母剔除会让预算看起来比实际小。

### 3.4 `EpisodeResult`

包含 `scenario_hash`、`adapter_name/version`、`planner_name`、`seed`、`steps`、`trajectory`、`metrics`、`raw`。
`raw` 记录后端的**实际生效配置**（如 `dt`、`max_steps`）——重放依赖它，见 §6 的教训。

## 4. 数据流

```
ScenarioIR ──► SearchMethod ──► adapter.run_episode ──► EpisodeResult
    ▲                │                                     │
    │                ├─ Budget（launched/completed/        │
    │                │   failed/cancelled/infeasible）     │
    │                └─ FailureCandidate（scenario_hash +  │
    │                    scenario_dict + 首次出现顺序）     │
    │                                                      ▼
    └──── perturb_scenario(seed) ◄── 候选集合 ──► EpisodeStore（场景+结果归档）
                                       │
                                       ├─► RunLedger（SHA-256 哈希链，逐事件）
                                       ├─► manifest.json（全文件哈希清单）
                                       └─► statistics（Wilson / bootstrap / Newcombe / Fisher / Holm）
```

## 5. 证据层设计

| 组件 | 作用 | 防的是什么 |
|---|---|---|
| `RunLedger` | append-only JSONL，每条 `hash = SHA256(prev_hash + 本条)` | 事后篡改记录、插入/删除事件 |
| `EpisodeStore` | 场景 + 结果 + extra 的归档 | 结果无法重放 |
| `manifest` | 每个文件的 SHA-256 与大小 | 文件被替换或缺失 |
| `replay` | 用归档配置重跑并比对类别与指标 | 代码漂移导致结果不可复现 |
| `DrivingEvidenceRecorder` | 单场景内的驾驶证据链（状态序列 + 事件 + 因果链接） | 事件无法追溯 |

**必须说清楚**：哈希链与 manifest 只能证明"这些字节没有变过"（T1 内部一致性）。它们**不能**证明实验设计正确、指标有效、结论为真（T2），更不能替代外部独立复现（T3）。详见 `docs/SCIENTIFIC_AUDIT.zh-CN.md`。

## 6. 一个真实教训：为什么 `raw` 必须记录生效配置

审计发现（D014）：`replay_kwargs` 曾只读 `raw.config`，而 builtin 把 `max_steps` 记在 `raw` 顶层，导致 `max_steps=80` 的 episode 重放时退回默认 300 步。表现是 **category 仍然一致**，但 `steps` 81→301、`final_x_m` 漂移 274 m。

结论：**"类别一致"不足以证明复现**。现在的 `ReplayOutcome` 同时比对类别与全部 metrics，审计脚本要求 ≤1e-6 才判 PASS。

## 7. 扰动模块（v2 起）

`scenario/perturb.py` 提供 `perturb_scenario(scenario, seed, bands)`：

- 只改初始条件（ego 速度/横向、他车间距/速度），**不改**车道数、几何、车辆数与 id；
- 用 `SeedSequence([seed, SALT])` 派生，与搜索 RNG 隔离；
- 确定性：同一 `(scenario, seed)` 跨进程得到同一场景。

它存在的原因是一次失败：v1 的 holdout 只换 seed，而 builtin 根本不消费 seed，导致"稳定率 100%"是同义反复。扰动把 seed 变成**有语义的输入变化**。

## 8. 并发与性能

- 单进程设计：`RunLedger` 明确声明线程不安全。
- 参考量级：8192 个 discovery episodes（`max_steps=80`，CPU）+ 384 个扰动 episode，合计约 20 秒。
- 证据体积：v2 完整包 773 文件 / 5.9 MB（压缩后 806 KB）。

## 9. 扩展点

| 想做什么 | 改哪里 |
|---|---|
| 接入新仿真器 | 实现 `SimulatorAdapter` + `@register_adapter`；如实填 `capabilities()` |
| 新规划器 | `planners/rule_based.py` 的 `PlannerRegistry` |
| 新搜索策略 | 继承 `BaseSearchMethod`，复用 `Budget` |
| 新失效判据 | 扩展 `FailureCategory`，同步更新协议口径 |
| 新报告格式 | `report/generator.py` |
