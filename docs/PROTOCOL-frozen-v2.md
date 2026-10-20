# DriveEvidenceLab｜预注册实验协议 v2.0（v1 缺陷修正版）

> 版本：v2.0 | 状态：已冻结 | 日期：2026-10-19
> 依据：`docs/PROTOCOL-frozen-v1.md` 第 3 行条款「任何后续修改必须另存为 v2 并说明变更理由」
> 前置审计：`docs/SCIENTIFIC_AUDIT.zh-CN.md`（Gate E v1 科学有效性审计）
>
> **本文件在 v2 实验运行之前写定。** 若 v2 结果不理想，不得回改本文件；
> 如需再改，另存 v3。

## 0. 为什么需要 v2（缺陷陈述，均已被实测证实）

| 编号 | v1 缺陷 | 实测证据 | 影响 |
|---|---|---|---|
| D-1 | `builtin` 仿真器创建 `rng = np.random.default_rng(seed)` 后**从未使用**，seed 对结果零影响 | 同一场景 seed=0/1/3000/3001/3002/999999，轨迹 SHA-256 完全相同（`1ab76b8b90eda348`），category/steps 相同 | v1 的「独立 holdout 种子」实为同一确定性函数的重复调用；「stable yield = 100%」是同义反复 |
| D-2 | `stable_failure_yield_protocol_cap = 前 16 个候选确认数 / 全部提名数` | 全部候选稳定时该值恒为 `16 / 提名数`：random 16/144=0.1111，mutation 16/1572=0.0102 | 该量只度量「提名数量」，与稳定性无关；用于算法比较具有误导性（发现越多的方法被惩罚） |
| D-3 | v1 要求「本文件 SHA-256 写入末尾」，属自指构造；内嵌 `247f6721…` 与文件实际 SHA-256 `9dcbd097…` 不一致，且不等于任何可复现的计算约定 | 见 `docs/SCIENTIFIC_AUDIT.zh-CN.md` §4 | 冻结印记不可核验 |
| D-4 | v1 的 H1 仅针对「**随机搜索**发现的 failure candidates」定义，但 Gate E 报告对两种方法同时宣告 H1 成立/不成立 | `runs/formal_experiment_v1/report.md` | 超出预注册范围 |

**v1 数据的处置**：`runs/formal_experiment_v1/` 原样保留，不删除、不重算其数字。
但 v1 的 **stable failure yield 及其 H1/H2 稳定性结论一律标记为 INVALID**（不具备方法学效力）。
v1 的 `discovery_yield` 与预算记账仍然有效（它们不依赖 seed 语义），可作为历史记录引用。

## 1. 假设（v2 重新预注册）

- **H1-v2（稳定性，仅限随机搜索）**：随机搜索提名的失败候选，在初始条件 ε-扰动下保持同类型失效的比例（stable yield）显著大于 0。判定：Wilson 95% 下界 > 0.1。
  - 与 v1 的差别：v1 用无效的 seed 重复，v2 用真实扰动；假设对象仍严格限定为随机搜索，不扩展到变异搜索。
- **H2-v2（方法比较）**：等预算下变异搜索与随机搜索的 stable yield 存在差异。方向不预设。判定：Newcombe hybrid score 95% CI 不含 0，并报告 Fisher 精确检验双侧 p 与 Cohen's h。
  - 与 v1 的差别：v1 用「capped 确认数 / 全部提名」这一混淆量，v2 用「确认数 / 实测数」，并要求两方法实测候选数相等。
- **H3-v2（发现率复现）**：在全新种子上复现 v1 的 discovery_yield 差异（mutation − random）。判定：配对 bootstrap 95% CI 不含 0（B=2000，seed=2026）。

多重比较：H1/H2/H3 构成一个检验族，按 Holm 校正（FWER 0.05）报告校正后 p 值。H1 为单侧下界判定，其余为双侧。

## 2. 稳定性的操作化定义（v2 核心修正）

**扰动方案** `eps-perturb/1.0`（实现：`src/driveevidence/scenario/perturb.py`）：

| 量 | 扰动半宽 | 说明 |
|---|---|---|
| ego 纵向速度 | ±2.0 m/s | 均匀分布 |
| ego 横向偏移 | ±0.15 m | 均匀分布 |
| 他车纵向间距 | ±3.0 m | 下限保证不重叠（`min_gap_m=2.0` + 车长和的一半） |
| 他车速度 | ±1.5 m/s | 均匀分布 |

- 扰动只改初始条件，不改车道数、道路几何、车辆数量与 id（结构保持），因此失效类别仍可比。
- 扰动流由 `SeedSequence(entropy=[seed, 0x9E3779B9])` 派生，与搜索 RNG 完全隔离。
- 每个候选使用 **3 个扰动种子**；种子从池中轮转分配（候选 j 取 `pool[(j+k) % 20]`，k=0..2），避免所有候选共享同一组种子。

**稳定候选判据（v2 收紧）**：3 次扰动中 **≥2 次**复现与发现阶段相同的 failure category。
（v1 为「≥1 次」，在确定性重复下几乎不可能失败，故收紧。）

**指标定义（v2）**：

```
stable_yield_v2 = 稳定候选数 / 实测候选数
```

- 分母是**实际执行了 holdout 的候选数**，不是全部提名数。提名规模单独以 `nominated_candidates` 与 `discovery_yield` 报告。
- 两方法实测候选数必须相等（见 §3），否则该比较无效。

## 3. 候选选择（消除顺序偏差）

- 发现阶段结束后，每方法按 `scenario_hash` 去重，得到提名集合。
- **预注册的均匀随机抽样**：用 `numpy.random.default_rng(4000)` 从提名集合中无放回抽取 `N_TEST = 64` 个候选；若提名数 < 64，则全取。
- 抽样在 holdout 执行之前完成，候选列表写入 `selection.json` 并与 ledger 哈希链绑定。
- 被抽中但 `validate()` 失败的扰动场景：计入实测分母，计为「未确认」，且单独统计 `infeasible` 数。

## 4. 种子集与预算（v2 使用全新种子）

| 用途 | 取值 |
|---|---|
| 开发/调试 | 1000–1009（不参与分析） |
| 发现阶段 master seed | **2100–2163（64 个）** |
| 候选抽样 seed | **4000** |
| 扰动种子池 | **4100–4119（20 个）** |
| 每 master seed 预算 | 64 episodes |

预算：

- 发现阶段：64 seeds × 64 episodes × 2 方法 = **8192 episodes**。
- 确认阶段：64 候选 × 3 扰动 × 2 方法 = **384 episodes**。
- 确认预算总量 384 高于 v1 的 96，理由是 v1 的 96 预算正是 D-2 分母混淆的直接成因；v2 以「两方法各 64 个实测候选」为保证可比性的最小规模，并在运行前写定。

## 5. 与 v1 一致、不变的部分

- 仿真后端 `builtin/1.0`、规划器 `safe_follow`、直道 3 车道、road_length=500 m、lane_width=3.7 m、speed_limit=33 m/s、`max_steps=80`。
- failure category 口径：COLLISION / OFF_ROAD / NEAR_MISS / RULE_VIOLATION 计 failure；INFEASIBLE / SIMULATOR_ERROR / TIMEOUT / NONE 不计 failure，但全部记账。
- 预算不变式：`launched = completed + failed + cancelled + infeasible`，`launched ≤ max_episodes`。
- 禁止推断条款沿用 v1 §7 全部内容。

## 6. 哈希约定（修正 D-3）

v1 的自指哈希不可实现。v2 采用**可核验的正文哈希**：

```
protocol_body_sha256 = SHA-256( UTF-8 bytes of this file up to, but excluding,
                                the line containing "<!-- SIGNATURE -->" )
```

即：把签名块整体排除后再计算。任何一个第三方都能用一条命令复现该值。

注意：**全文件哈希不能写进文件自身**（否则又会变成 D-3 式的自指）。因此全文件
SHA-256 记录在同目录的 `docs/PROTOCOL-v2.freeze.json` 中，并与 git 提交绑定。

## 7. 结果解释的强制边界

- v2 的动机是**事后发现缺陷**（post-hoc defect discovery）。虽然 v2 跑在全新种子上、指标在运行前写定，但它**不是**完全独立于 v1 结果的预注册。任何依赖 v2 的结论必须同时声明这一点。
- 没有任何**外部**独立团队复现过本实验。`runs/formal_experiment_v1` 与 `runs/formal_experiment_v2` 都是同一作者、同一代码库、同一台机器产生。
- 结论适用范围：`builtin` 运动学仿真器 + `safe_follow` + 直道 3 车道场景族。不外推到真实道路，不外推到 highway-env，不外推到其他规划器。
- 若 stable yield 很高：只说明「该失效对本协议规定的 ε 扰动稳健」，不等于「系统在该场景族中普遍失效」，也不等于「真实世界中会失效」。

<!-- SIGNATURE -->
protocol_version = v2.0
protocol_body_sha256 = 205ecf9ff156d003887502f438dc4975bcd3a9b3e85b4a2c70feb54eea8a5137
frozen_at = 2026-10-19
