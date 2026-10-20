# DriveEvidenceLab｜预注册实验协议 v1.0

> 版本：v1.0 | 状态：已冻结 | 日期：2026-10-19
> 负责人：总指挥（GLM-5.3） | 独立 QA：待 Step-5-Preview 签核
>
> ⚠️ 本协议在研究方案 v0.2（Step-5-Preview 复审 3.00/3 通过）基础上做了可执行化收窄。
> 任何后续修改必须另存为 v2 并说明变更理由，禁止根据结果回改本文件。

## 1. 核心问题与可证伪假设

- **主要研究问题**：在等预算条件下，变异搜索能否比随机采样发现更高比例的**稳定失败**（stable failure）？失败候选在独立 holdout 种子下保持同类型失效的比例是否显著大于 0？
- **H1（稳定性）**：随机搜索发现的 failure candidates 在独立 holdout 种子下保持同类型失效的比例（stable failure yield）显著大于 0。若 Wilson 95% 下界 > 0.1，则拒绝“无稳定失败”的虚无假设。
- **H2（方法比较）**：等预算下变异搜索与随机搜索的 stable failure yield 存在差异。方向不作单侧预设；报告配对 bootstrap 95% CI 与 Cohen's h 效应量。
- **主要结果指标**：
  - stable_failure_yield = 经 holdout 确认的失败数 / 发现阶段提名数（分母含全部被提名者，不 cherry-pick）。
  - discovery_yield = 发现阶段 failure category ∈ {COLLISION, OFF_ROAD, NEAR_MISS, RULE_VIOLATION} 的 episode 数 / 已发起 episode 数。
- **负结果解释**：若 stable failure yield 接近 0，说明当前场景族/规划器/预算不足以产生可复现的系统性缺陷，而非“系统安全”。
- **适用范围**：仅限仿真内 rule-based 规划器（safe_follow, constant_speed）在 straight-road  highway 场景族上的表现；不推断真实道路安全。

## 2. 实验对象和版本冻结

| 组件 | 版本/配置 |
|---|---|
| 仿真后端 | builtin/1.0（确定性运动学）+ highwayenv（highway-env 1.12.1 + gymnasium 1.4.0），各自独立分析 |
| 规划器 | safe_follow（默认）、constant_speed |
| 场景族 | straight-road，3 车道，road_length=500 m，lane_width=3.7 m，speed_limit=33 m/s |
| Canonical scenario IR | ir/v1 |
| Python | 3.13.14（项目 venv） |
| driveevidence | 当前 git HEAD（见 manifest） |
| 种子派生 | master_seed → SHA-256(master_seed + "dev/discover/holdout") 取前 32 位十六进制转 int，再按范围取模 |

## 3. 比较方法与公平预算

- **Baseline 1**：RandomSearch（name="random"），从固定先验采样。
- **Method 2**：MutationSearch（name="mutation"），从失败 archive 做 70% 变异 + 30% 随机初始化。
- **每方法预算**：发现阶段 ≤64 episodes；确认阶段每候选 ≤3 holdout seeds（总确认 ≤ 96 seeds）。
- **预算记账**：launched = completed + failed + cancelled + infeasible；任何重试额外计入 launched；超时/崩溃按 failure 或 SIMULATOR_ERROR 记账。
- **可见数据对等**：两种方法共享同一 Budget 规则、同一场景族、同一规划器集合、同一失败 category 口径。
- **非预期偏差控制**：主指标预注册、多重比较 Holm 校正、固定 seed 派生、协议先冻结。

## 4. 数据切分与冻结

- **开发/调参 seed set**：1000–1009（仅用于本地调试与 mock，不参与正式分析）。
- **发现阶段 seed set**：2000–2063（64 个 master_seed）。
- **独立 holdout set**：3000–3019（每个候选复测 3 个 holdout seeds，共 60 个）。
- **正式协议冻结**：本文件 SHA-256 写入末尾 `protocol_sha256`。
- **搜索候选提名冻结**：发现阶段运行结束后，对候选按 scenario_hash 去重并固定列表，方可进入 holdout 复测。

## 5. 预设评估和异常口径

- **场景有效性约束**：IR v1 验证；重叠 spawn、越界、未知 ODD key 均视为 INFEASIBLE；`validate()` 独立于安全判据。
- **failure category 口径**：
  - COLLISION、OFF_ROAD、NEAR_MISS、RULE_VIOLATION 计入 failure。
  - INFEASIBLE、SIMULATOR_ERROR、TIMEOUT、NONE、UNKNOWN 不计入 failure，但全部分母与 ledger 记账。
- **planned/effective/launched/failed/cancelled/infeasible**：每 episode 必须落到 ledger 中。
- **配对 bootstrap**：B=2000，固定 seed=2026，alpha=0.05；比较两方法在同一 64 个 master_seed 上的 yield 差值。
- **多重比较**：若同时比较 >1 个指标族，主指标用 Holm（FWER），次指标用 Benjamini-Hochberg（FDR）。
- **Stop conditions**：达到预算上限或时间上限 30 分钟；任何崩溃/异常如实记录为 SIMULATOR_ERROR 或 failed。

## 6. 迁移性检验

- **Transfer preconditions**：仅在两个适配器共同支持的 scenario 子集（straight-road、同车道语义、ego 纵向动力学）上比较。
- **可比较 IR 子集**：lanes ∈ {3}, road type="straight", planner ∈ {safe_follow, constant_speed}, 失效 category 必须被两个适配器同时声明支持。
- **不能迁移的记录**：highwayenv 适配器的 exact vehicle placement 是近似映射，因此 highwayenv 结果不与 builtin 直接合并，只分别报告。
- **Domain mismatch 解释边界**：任何从仿真 failure rate 到真实道路事故概率的推断均被禁止。

## 7. 不允许的推断

- 不能从仿真 failure rate 推出真实道路事故概率。
- 不能把候选数量直接当独立根因数。
- 没有独立 holdout 就不能写“已证实稳定”。
- 不能根据正式结果调参后仍把它作为同一个预注册实验。
- 一个仿真器的性能不能推断真实车载系统安全。

## 8. 审核印记

- 协议已冻结：YES
- 独立 QA review：PENDING
- 所有正式实验事前运行授权：YES（总指挥授权，预算内 CPU 运行）
- Run manifest digest：见运行产物 `manifest.json`

---

`protocol_sha256 = 247f6721ee26ae76e7e9258e3e43065ea2189fe4d37254ff62b8074ae8e92e29`
