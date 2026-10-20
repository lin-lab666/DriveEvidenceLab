# API 参考（API Reference）

> driveevidence 0.2.0　｜　所有公开符号均可 `from driveevidence.<module> import ...` 引入。
> 本项目只依赖 Python 标准库 + NumPy；`gymnasium`/`highway-env` 仅在 `[sim]` 额外依赖中需要。

---

## 1. 场景契约 `driveevidence.scenario`

### `ScenarioIR`

```python
@dataclass
class ScenarioIR:
    scenario_id: str
    road_length_m: float
    lanes: int
    lane_width_m: float
    speed_limit_mps: float
    ego: VehicleState
    vehicles: List[VehicleState] = []
    odd: Dict[str, Any] = {}
    meta: Dict[str, Any] = {}
    ir_version: str = "ir/v1"
```

| 方法 | 说明 |
|---|---|
| `validate() -> None` | 违反 IR v1 约束时抛 `ScenarioValidationError`。**只校验合法性，不做安全判定** |
| `to_dict() -> dict` | canonical 结构，可直接 `json.dump` |
| `from_dict(d) -> ScenarioIR` | 反序列化 |
| `.scenario_hash` | canonical JSON 的 SHA-256（属性），跨进程稳定 |

```python
from driveevidence.scenario import ScenarioIR, VehicleState

s = ScenarioIR(
    scenario_id="demo", road_length_m=500, lanes=3, lane_width_m=3.7, speed_limit_mps=33,
    ego=VehicleState(id="ego", x_m=50, y_m=1.85, v_mps=25, heading_rad=0),
    vehicles=[VehicleState(id="v1", x_m=70, y_m=1.85, v_mps=15, heading_rad=0)],
)
s.validate()
print(s.scenario_hash[:16])
```

### `VehicleState`

```python
VehicleState(id, x_m, y_m, v_mps, heading_rad,
             length_m=4.5, width_m=1.8, kind="car")
```

`kind ∈ {car, truck, bus, motorcycle, bicycle, pedestrian}`。

### `perturb_scenario(scenario, seed, bands=DEFAULT_PERTURBATION_BANDS, salt=PERTURBATION_SALT) -> ScenarioIR`

对初始条件施加**有界、确定性、结构保持**的 ε-扰动。用于"失效是否稳健"的 holdout 复测。

```python
from driveevidence.scenario.perturb import perturb_scenario, PerturbationBands

p = perturb_scenario(s, seed=4100)
p2 = perturb_scenario(s, seed=4100,
                      bands=PerturbationBands(ego_speed_mps=1.0, ego_lateral_m=0.0,
                                              lead_gap_m=2.0, lead_speed_mps=0.5,
                                              min_gap_m=2.0))
assert perturb_scenario(s, seed=4100).scenario_hash == p.scenario_hash
```

- 不改车道数、道路几何、车辆数量与 id。
- 同 `(scenario, seed)` 恒等；不同 seed 不同。
- 结果**未校验**，调用方需 `validate()` 并把失败记为 `INFEASIBLE`。

### `perturbation_seeds(seed_pool, index, n) -> List[int]`

从池中按轮转为第 `index` 个候选分配 `n` 个互不相同的 seed。`n > len(pool)` 抛 `ValueError`。

---

## 2. 仿真适配 `driveevidence.sim`

### `SimulatorAdapter`（抽象基类）

```python
class SimulatorAdapter(ABC):
    name: str
    version: str
    def capabilities(self) -> Dict[str, bool]: ...
    def run_episode(self, scenario: ScenarioIR, seed: int,
                    planner_name: str = "default",
                    config: Optional[dict] = None) -> EpisodeResult: ...
```

`capabilities()` 的键：`collision`、`off_road`、`rule_violation`、`near_miss`、`timeout`、`deterministic_replay`。
**后端不支持的检测必须写 `False`。**

### 注册与创建

```python
from driveevidence.sim import create_adapter, list_adapters, register_adapter

list_adapters()                 # ['builtin', 'commonroad', ('highwayenv', 可选)]
a = create_adapter("builtin")   # 未注册 -> KeyError
```

自定义后端：

```python
@register_adapter
class MyAdapter(SimulatorAdapter):
    name = "my"
    version = "my/0.1"
    def capabilities(self): return {"collision": True, "off_road": False}
    def run_episode(self, scenario, seed, planner_name="default", config=None):
        ...
```

### `EpisodeResult`

```python
@dataclass
class EpisodeResult:
    scenario_id: str; scenario_hash: str
    adapter_name: str; adapter_version: str
    planner_name: str; seed: int
    steps: int; wall_time_s: float
    terminated: bool; truncated: bool
    failure_category: FailureCategory
    failure_detail: str
    trajectory: List[TrajectorySample]
    metrics: Dict[str, float]
    raw: Dict[str, Any]      # 必须含实际生效的 dt / max_steps
```

> **`steps` 的确切语义**：`steps == len(trajectory)`，计的是**轨迹采样点数**，不是积分步数。
> 每个采样点在施加上一步动力学之后、判定该步失败之前记录，循环结束后再补一个终态样本，
> 因此：
> - 超时（`TIMEOUT` / 近失）：`steps == max_steps + 1`；
> - 第 `k` 步失败（碰撞/越界/超速）：`steps == k + 1`。
>
> 轨迹本身完整且无重复采样。字段名沿用历史命名，改动会破坏已归档证据的逐位重放，
> 故保留并在此明确（见 `docs/SCIENTIFIC_AUDIT.zh-CN.md` §11.13）。

### `FailureCategory`

`COLLISION` `OFF_ROAD` `RULE_VIOLATION` `NEAR_MISS` `TIMEOUT` `INFEASIBLE` `SIMULATOR_ERROR` `NONE`

只有前四个计入 failure。其余入账但不计分子（详见 `docs/ARCHITECTURE.md` §3.3）。

### 内置后端

| 后端 | 说明 | 关键局限 |
|---|---|---|
| `builtin` | 确定性运动学直道仿真器 | 无侧向动力学、无真实车辆模型；**不能**代表真实道路 |
| `highwayenv` | highway-env 1.12.1 + gymnasium 1.4.0 | IR 车辆位置为**近似映射**（`capabilities()["exact_ir_placement"]=False`），不可与 builtin 合并比较 |
| `commonroad` | commonroad-io 2026.1：场景经 CommonRoad XML 交换并由其 `check_validity` 校验，碰撞/越界判定使用 CommonRoad 几何 | **动力学与 builtin 同构**（`capabilities()["independent_dynamics"]=False`），只替换判定层；**不是**第二个仿真器，不可用于跨仿真器结论 |

---

## 3. 规划器 `driveevidence.planners`

```python
from driveevidence.planners.rule_based import get_planner, list_planners

list_planners()                 # ['constant_speed', 'safe_follow']
fn = get_planner("safe_follow") # (PlannerContext) -> accel_mps2
```

`PlannerContext` 字段：`ego`、`others`、`dt`、`speed_limit_mps`、`road_length_m`、`lanes`、`lane_width_m`。
`safe_follow` 是 IDM-lite：前方同车道间距不足 2 s 时按比例制动，<0.5 s 急刹，否则温和加速。

---

## 4. 搜索 `driveevidence.search`

### `Budget`

```python
Budget(max_episodes=64)
b.register_launch(); b.register_complete()
b.register_infeasible(); b.register_fail(reason); b.register_cancel()
b.exhausted          # launched >= max_episodes
b.snapshot()         # {'max_episodes','launched','completed','failed','cancelled','infeasible'}
```

不变式：`completed + failed + cancelled + infeasible == launched <= max_episodes`，违反抛 `RuntimeError`。

### `BaseSearchMethod`

```python
class BaseSearchMethod(ABC):
    name: str
    def search(self, adapter, budget: Budget, master_seed: int,
               seed_scenarios: Optional[List[ScenarioIR]] = None) -> SearchReport
```

### 内置方法

| 类 | `name` | 策略 |
|---|---|---|
| `RandomSearch` | `random` | 固定先验均匀采样 |
| `MutationSearch` | `mutation` | 70% 从失败 archive 变异 + 30% 随机初始化 |

### `SearchReport`

```python
SearchReport(method, master_seed, budget_snapshot, candidates, n_episodes, episode_summaries)
```

`candidates: List[FailureCandidate]`，每项含 `scenario_hash`、`scenario_dict`、`discovery_seed`、`failure_category`、`round_idx`、`metrics`。

```python
from driveevidence.search import RandomSearch, Budget
from driveevidence.sim import create_adapter

adapter = create_adapter("builtin")
report = RandomSearch(max_steps=80).search(adapter, Budget(64), master_seed=2000)
print(len(report.candidates), report.budget_snapshot)
```

---

## 5. 统计 `driveevidence.stats`

全部为纯函数，除注明外基于 NumPy。

| 函数 | 返回 | 说明 |
|---|---|---|
| `wilson_ci(k, n, z=1.96)` | `(lo, hi)` | Wilson 得分区间；`n=0` 返回 `(0.0, 1.0)` |
| `stable_failure_yield(confirmed, tested, z=1.96)` | `(point, (lo, point, hi))` | 稳定失败率的点估计 + CI |
| `paired_bootstrap_ci(diffs, n_boot=2000, seed=0, alpha=0.05)` | `(lo, hi)` | 配对差值的百分位 bootstrap CI |
| `bootstrap_p_value(diffs, n_boot=2000, seed=0)` | `float` | 双侧百分位 bootstrap p（近似，非精确） |
| `cohens_h(p1, p2)` | `float` | 两比例效应量 |
| `newcombe_diff_ci(k1, n1, k2, n2, z=1.96)` | `(diff, lo, hi)` | 独立两比例差的 Newcombe hybrid score CI（方法 10） |
| `fisher_exact_two_sided(a, b, c, d)` | `float` | 2×2 Fisher 精确检验（纯标准库实现） |
| `binomial_tail_p(k, n, p0)` | `float` | 单侧精确二项 `P(X >= k \| n, p0)` |
| `holm_correction(pvals)` | `List[float]` | Holm FWER 校正 |
| `benjamini_hochberg(pvals)` | `List[float]` | BH FDR 校正 |

```python
from driveevidence.stats import wilson_ci, newcombe_diff_ci, holm_correction

# 输入为协议 v2.1 的实测值（random 57/64、mutation 61/64）。
wilson_ci(57, 64)                  # (0.7910..., 0.9460...)
newcombe_diff_ci(57, 64, 61, 64)   # (0.0625, -0.0365..., 0.1668...)
holm_correction([0.001, 0.03, 0.2])
```

---

## 6. 证据 `driveevidence.evidence`

### `RunLedger`

```python
RunLedger(run_dir, run_id, config={})   # 同目录已存在则续写
ledger.record(event_type, payload) -> dict
ledger.verify_chain() -> (ok: bool, first_bad_seq: int | None)
ledger.entries() -> List[dict]
RunLedger.load(run_dir) -> RunLedger
```

每条记录：`{seq, ts, type, payload, prev_hash, hash}`，`hash = SHA256(prev_hash + canonical(seq,ts,type,payload))`，首条 `prev_hash="GENESIS"`。
**单进程设计，线程不安全。**

### `EpisodeStore`

```python
store = EpisodeStore(run_dir)
store.save(scenario, result, extra={}) -> str        # episodes/0001.json
store.load(seq) -> (ScenarioIR, EpisodeResult, extra)
store.iter_all() -> Iterator[(seq, ScenarioIR, EpisodeResult, extra)]
EpisodeStore.replay_kwargs(episode_data) -> {seed, planner_name, config}
```

### `manifest`

```python
build_manifest(run_dir, exclude=None) -> dict   # 写 manifest.json
verify_manifest(run_dir) -> Dict[relpath, "ok"|"missing"|"hash-mismatch"]
```

### `replay_episode(run_dir, seq, adapter) -> ReplayOutcome`

```python
@dataclass
class ReplayOutcome:
    original_category: str
    replayed_category: str
    category_match: bool
    metric_diffs: Dict[str, float]
    replayed_result: EpisodeResult
```

**不一致不抛异常**，如实返回。判定复现成功必须**同时**要求 `category_match` 与所有 `|metric_diffs| <= 1e-6`。

### `DrivingEvidenceRecorder`

单场景内的驾驶证据链记录器：

```python
rec = DrivingEvidenceRecorder("scenario-1", sampling_hz=10)
rec.add_state(t, x, y, v, heading, **extra) -> int   # 从 1 递增
rec.add_event(t, "hard_brake", "desc", severity=2) -> int
rec.link_cause(effect_id, cause_id, "triggered_by", confidence=0.8)  # 不存在的 id 抛 KeyError
rec.summary() -> {"scenario_id","n_states","n_events","n_causal_links"}
rec.to_json(path); DrivingEvidenceRecorder.from_json(path)
```

`confidence ∉ [0,1]` 抛 `ValueError`。

---

## 7. 报告 `driveevidence.report`

```python
load_report(run_dir) -> ReportSummary
generate_markdown(run_dir, out_path=None) -> str
generate_html(run_dir, out_path=None) -> str
```

---

## 8. 命令行

```bash
driveevidence doctor
driveevidence sample --id demo --out runs/demo.json
driveevidence run --scenario examples/scenarios/tailgate_risk.json --adapter builtin --seed 123 --run-id r1 --out runs
driveevidence search --method mutation --adapter builtin --budget 64 --seed 2000 --run-id r2 --out runs
driveevidence audit --run runs/r2
driveevidence replay --run runs/r2 --seq 1 --adapter builtin
driveevidence report --run runs/r2 --format html --out runs/r2/report.html
```

所有子命令返回退出码 0（成功）/ 非 0（失败），可直接用于 CI。

---

## 9. 实验脚本（不属于库 API，但属于交付物）

| 脚本 | 作用 |
|---|---|
| `scripts/run_formal_experiment_v2.py` | 按冻结协议 v2 跑 64×master_seed 配对实验 |
| `scripts/audit_scientific_validity.py` | 不信任 summary，从原始产物独立重算 + T1/T2/T3 分层判定 |
| `scripts/verify_evidence_bundle.py` | 第三方核验压缩证据束（校验和 → 链 → manifest → 重算） |
| `scripts/run_all.sh` | 一条命令跑测试 + CLI 冒烟 + 证据核验（`--with-formal` 追加正式实验） |
