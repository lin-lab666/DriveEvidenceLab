# DECISIONS（架构与科研决策记录）

> 格式：ADR 编号 | 日期 | 决策 | 理由 | 状态

## D001 | 2026-10-19 | 项目定名与包结构
- 包名 `driveevidence`，src 布局（`src/driveevidence/`），模块划分按 docs/SPEC.md：scenario / sim / planners / search / evidence / stats / report / cli。
- 前期原型 `src/evidence/recorder.py`（24/24 测试通过）迁移为 `src/driveevidence/evidence/recorder.py`，保持 API 兼容，原文件移除、历史记录保留在 logs/ 与 git 历史。
- 状态：已实施

## D002 | 2026-10-19 | 仿真后端矩阵
- **HighwayEnv 1.12.1 + gymnasium 1.4.0**（已装入项目 venv）作为首个真实 CPU 后端，目标 Gate B。
- 自带 `builtin` 运动学仿真器（确定性、轻量）用于单元测试、性质测试与 replay 一致性核验——它是测试基件，不冒充第三方仿真验证。
- CARLA：需 GPU/重型依赖，本机未安装，标记 **UNSUPPORTED / NOT VERIFIED**。
- CommonRoad：~~未安装，标记 **UNSUPPORTED / NOT VERIFIED**（接口预留）~~。
  **本行已被 D022 更新**：2026-10-19 已安装 `commonroad-io 2026.1` 并完成适配器与判定语义验证，状态改为 **PARTIAL**（仍未接第三方动力学）。
- 状态：已实施（CommonRoad 部分由 D022 推进）

## D003 | 2026-10-19 | 环境
- 项目 venv：WorkBuddy 托管的 `python/envs/driveevidence`（Python 3.13.14；绝对路径含本机用户名，
  已在入库文档中隐去，见 `docs/RELEASE_CHECKLIST.md` §E 的发布前检查）。
- 依赖锁定：发布前 `pip freeze` 生成 requirements-lock.txt。
- gh CLI 不可用 → GitHub 发布需用户自行认证路径，且发布前需用户最终确认（任务书第六节）。
- 状态：已实施

## D004 | 2026-10-19 | DeepSeek 模型路由疑点处理
- 既有疑点（子智能体自报底层为 GLM-5.3 vs 派发指定 DeepSeek-V4.1-Flash）**标记为未确认**，不阻塞不依赖模型归因的研发任务。
- 后续协作报告中涉及 DeepSeek 派发的产出，标注 "model identity unconfirmed"。
- 状态：开放

## D005 | 2026-10-19 | 证据链设计
- RunLedger 采用 append-only JSONL + sha256 哈希链（每条记录含 prev_hash），防篡改可审计。
- 每个正式 run 的证据包：ledger.jsonl + episodes/*.json + manifest.json（全文件 sha256）+ config 快照 + 复现命令。
- 状态：已实施

## D006 | 2026-10-19 | 科学边界（承任务书）
- 仅研究仿真内策略表现；三套种子（开发/发现/留出审计）分离；协议在正式实验前冻结；mock 仅用于单元测试；失败/超时/取消全部计费入账。
- 状态：约束生效

## D007 | 2026-10-19 | 搜索方法预算公平
- `RandomSearch` 与 `MutationSearch` 共享 `Budget` 规则；infeasible/失败均入账；候选重录使用同一 episode store。
- 状态：已实施

## D008 | 2026-10-19 | 跨仿真器不可比性处理
- `highwayenv_adapter` 无法保证 exact IR placement，在 `capabilities` 与 `raw` 中诚实声明；跨适配器比较仅限 capability 交集。
- 状态：已实施

## D009 | 2026-10-19 | CLI 与可复现证据包
- 所有正式运行产物统一落盘 `runs/<run_id>/`：ledger.jsonl + episodes/*.json + manifest.json + report.md/html；复现命令由 ledger 首条记录保存。
- 状态：已实施

## D010 | 2026-10-19 | 模型身份未确认的处理（承 D004）
- Round 4 子智能体全部因 429 限流失败，由总指挥直接完成对应模块；所有代码提交签名为 `DriveEvidenceLab Team`，未冒充任何子智能体身份。
- DeepSeek-V4.1-Flash 派发的历史记录仍标记为 identity-unconfirmed；当前代码与测试结果由 GLM-5.3 主智能体验收通过。
- 状态：已记录

## D011 | 2026-10-19 | Gate E 正式实验执行方式
- 按 `docs/PROTOCOL-frozen-v1.md` 执行 64×master_seed 配对实验（discovery seeds 2000–2063，每方法 budget=64）。
- Holdout 确认预算严格按协议 §3 的 96-seed 总上限执行：每方法最多确认 16 个候选；其余提名候选计入 stable yield 分母但计为未确认。
- 全部候选的 holdout 仍运行并归档，作为敏感性分析的原始证据；primary 结论仅使用 capped 子集。
- 状态：已实施

## D012 | 2026-10-19 | 协议内部歧义处理
- 协议 §3 规定总确认 ≤ 96 seeds，§4 提到 holdout 种子“共 60 个”（20 unique × 3）。两者不一致。
- 决策：采用 §3 的显式预算上限（96 seeds = 32 candidates）作为 primary 约束；20 unique seeds 用于 round-robin 分配，可跨候选复用。
- 状态：已记录

## D013 | 2026-10-19 | 协议自签 hash 异常处理
- `docs/PROTOCOL-frozen-v1.md` 末尾声明的 `protocol_sha256`（`247f67...`）与文件实际内容 SHA-256（`9dcbd...`）不一致。
- 决策：不修改冻结协议文件；实验证据包以实际文件内容 hash 作为协议标识，并在报告、审计和 DECISIONS 中显式记录该异常。
- 状态：已记录

## D014 | 2026-10-19 | Replay 配置丢失缺陷（审计发现，已修复）
- 现象：`EpisodeStore.replay_kwargs` 仅读 `result.raw.config`，而 builtin 适配器把 `max_steps` 记在 `raw` 顶层；重放退回默认 300 步。
- 后果：一个 `max_steps=80` 的 timeout episode 重放后 steps 81→301、`final_x_m` 漂移 274 m；category 仍一致，因此**只看类别会漏判**。
- 修复：`replay_kwargs` 恢复 `raw` 顶层 `dt/max_steps` 等键，允许 `extra.config` 覆盖；新增 `TestReplayConfigFidelity` 4 项回归测试。
- 影响范围：不影响 v1/v2 已归档的实验数据（重放只读），影响的是"可复现性验证"的可靠性。
- 状态：已修复并验证（修复后归档 episode 重放 5/5 一致）

## D015 | 2026-10-19 | Gate E v1 稳定性结论撤回 + 协议 v2
- 缺陷 1：builtin 仿真器创建 `rng = default_rng(seed)` 后从未使用 → v1 的 holdout 种子无任何效果，1716/1716 候选在 3 个种子下逐位相同。
- 缺陷 2：v1 primary 指标 `前16确认数/全部提名数` 在"全部稳定"时恒等于 `16/提名数`，只反映提名数量。
- 缺陷 3：v1 协议内嵌 `protocol_sha256` 不对应任何可复现计算约定（自指构造）。
- 缺陷 4：v1 的 H1 仅对随机搜索定义，报告却对两方法同时判定。
- 决策：**撤回 v1 的 stable yield 数值与 H1/H2 稳定性结论**（保留原始文件与产物，不删除、不改数）；另存 `docs/PROTOCOL-frozen-v2.md`，用 ε-扰动、实测分母、预注册抽样、全新种子（2100–2163 / 4100–4119）重做。
- v1 仍然有效的部分：`discovery_yield`、预算记账、哈希链完整性（这些不依赖 seed 语义）。
- 状态：已实施

## D016 | 2026-10-19 | 科研结论的三层分级制度
- 任何结论必须标注其所属层级，禁止混用：
  - **T1 内部一致性**：产物自洽、可重算。哈希链/manifest 属于此层，**不能**证明实验为真或方法有效。
  - **T2 方法学有效性**：测量确实测到了协议声称的量。需要独立设计审查与负对照。
  - **T3 外部独立复现**：由独立第三方在独立环境复现。
- 当前状态：T1 = 15/15；T2 = v2 通过但保留 1 项 FAIL（v1 协议哈希）；T3 = 不具备。
- 状态：制度生效

## D017 | 2026-10-19 | NEAR_MISS 死代码缺陷（独立审查发现，已修复）+ v2.1 重跑
- 缺陷：`builtin.py` 的 `for ... else` 在循环自然结束时必然置 `category=TIMEOUT`，循环后的
  `if category == FailureCategory.NONE` 永假 → `NEAR_MISS` 分支不可达。8192 个发现 episode 中
  `near_miss` 出现 0 次，四类失败口径实际塌缩为 `COLLISION` 单一类别。
- 修复：near-miss 判定移入 `else` 分支，先判 near-miss 再退化到 TIMEOUT；
  `builtin/1.0` → `builtin/1.1`；新增 3 项回归测试。
- 影响：这是对**已冻结代码**的修改，构成协议偏离。因此保留两次运行：
  - `runs/formal_experiment_v2`（builtin/1.0）：random 0.9375、mutation 0.9531；
  - `runs/formal_experiment_v2p1`（builtin/1.1，**主结果**）：random 0.8906、mutation 0.9531。
  H1/H2/H3 的判定方向在两次运行中一致（支持/不支持/支持），数值变化归因于类别口径变化
  导致的提名集合变化。
- 状态：已修复、已重跑、两版结果并存

## D018 | 2026-10-19 | v1 的 H2 指标替换（协议—报告不一致）
- 协议 v1 的 H2 预注册为「stable failure yield 差异 + 配对 bootstrap + Cohen's h」；
  实际执行的是「discovery_yield 差值的配对 bootstrap」，报告仍以 H2 之名标注"支持"。
- 判定：预注册的 H2 分析从未按其注册形式执行，v1 的 H2 结论**撤回**。
- 后续：协议 v2 将该问题拆为 H2（stable yield，Newcombe CI + Fisher）与 H3（discovery yield，
  配对 bootstrap），二者分别判定，不再混称。
- 状态：已记录并修正

## D019 | 2026-10-19 | 已知设计耦合（记录，不在本轮修改）
- holdout 种子跨候选复用：v2 用 20 个扰动种子分配给 64 个候选，每种子约使用 9.6 次。
  「独立」仅在同一候选的 3 次之间成立；因不同候选场景不同，输入仍不同，但种子不唯一。
- 两方法搜索 RNG 在 round 0 耦合：`MutationSearch` 在 archive 为空时与 `RandomSearch`
  共用同一 `default_rng(master_seed)` 流，导致每个 master seed 的首个场景在两方法下逐位相同
  （1/64 episode 共享）。
- 决策：**不在本轮修改**。两者都会改变候选集合与结果，属"看到结果后改实验设计"的风险区；
  正确做法是在新协议（v3）中预先声明独立的 RNG 派生（如按方法加 salt）并扩大种子池。
- 影响评估：~~round 0 共享仅影响 1/64 的 episode，不改变 H1/H2/H3 的判定方向。~~
  **该评估不准确，已被 D019-C 的实测推翻**（重叠远不止 1 个 episode）。见下条。
- 状态：已记录，耦合已量化（D019-C），修复仍留待 v3

## D019-C | 2026-10-19 | 耦合程度实测与 H3 敏感性（更正 D019 的影响评估）
- 方法：从 `runs/formal_experiment_v2p1/discovery/*/seed_*/report.json` 逐种子比对两方法
  64 个 episode 的场景哈希序列，计算逐位置重合数；再按重合度分层重算 H3。
  脚本：`scripts/audit_seed_coupling.py`，产物：`runs/formal_experiment_v2p1/seed_coupling.json`。
- 实测：重合数 min=1、median=16、mean=23.0、max=64（满分 64）。**17/64 对至少一半 episode
  完全相同**，而非先前以为的仅 round 0 的 1 个。
- 其中 **4 对完全退化**（seed 2100 / 2138 / 2144 / 2161）：两方法执行了逐位相同的 64 个场景。
  机制：mutation 在 failure archive 为空时退化为随机初始化，且与 random 共用
  `default_rng(master_seed)` 流；该 seed 下始终未找到失败，archive 永远为空，故整轮退化为
  random search。这 4 对同时也正是两方法候选数均为 0 的 seed（交集完全吻合）。
- H3 敏感性（配对 bootstrap，B=2000，seed=2026）：
  | 子集 | n | Δ | 95% CI | 排除 0 |
  |---|---|---|---|---|
  | 全部 | 64 | +0.3669 | [+0.3218, +0.4124] | 是 |
  | 剔除 4 对退化 | 60 | +0.3914 | [+0.3490, +0.4333] | 是 |
  | 重合 < 中位数(16) | 31 | +0.5096 | [+0.4844, +0.5328] | 是 |
  | 重合 ≥ 中位数(16) | 33 | +0.2330 | [+0.1799, +0.2865] | 是 |
- 偏差方向：重合会**衰减**配对差值（重合越多，mutation 专属 episode 越少），因此合并估计
  +0.3669 是**保守的**，不是被耦合抬高。低重合层的效应（+0.51）明显大于高重合层（+0.23），
  与衰减机制一致。
- 但耦合确实使「有效独立配对」少于名义上的 64：完全退化的 4 对贡献差值恒为 0，
  属于无效观测（对结论取保守方向）。
- 决策：仍**不在本轮修改**（改动 RNG 派生会改变候选集合，属"看到结果后改实验设计"）。
  在 v3 中预先声明按方法加 salt 的独立 RNG 派生，并在报告中把「逐对重合度」列为常规披露项。
- 状态：已实测、已披露、已做敏感性分析；修复留待 v3

> **D019-C 后续修正（2026-10-20，最终验收轮）**：本条目第 146–148 行原写"合并估计
> +0.3669 是**保守的**"、第 150 行"对结论取保守方向"。经最终验收复核，此表述**过强**，
> 已按 `docs/LIMITATIONS.md` §4 的现行解释收窄（该文件是当前权威口径）：
> - 重合使配对差值向 0 收缩，只是**机制性解释**，**不是**已证明的偏差方向；
> - 分层（剔除退化 / 低重合 / 高重合）是对**同一数据的事后重组**，不构成因果识别，
>   只支持"方向稳健"，**不支持**"合并估计必然保守"。
> - 相应地把 `scripts/audit_seed_coupling.py` 的 `direction` 字段与脚本 docstring 从
>   "pooled estimate is conservative" 改为"sign of H3 is robust across strata; does NOT
>   establish conservatism"。**证据束保持冻结**：`evidence/gateE-v2p1-full.tar.gz` 内归档的
>   `seed_coupling.json`（含旧 direction 措辞）**未改动**，`build_evidence_bundle.py --check`
>   仍为 MATCH；未来重跑脚本会产出新措辞，但已归档产物保留当时的记录。原始决策历史
>   （第 129–153 行）**保留不删**。

## D020 | 2026-10-19 | CommonRoad XML 默认精度造成的假失败（已修，未放宽容差）
- 现象：Gate D 交叉核对首次运行 `exchange failures = 71/80`。
- 排查：不是映射错误。CommonRoad 的 XML writer 默认 `decimal_precision=4`，
  `v=31.15544248…` 被写成 `31.1554`，与本项目 1e-6 的比对容差冲突（实际差 4.25e-5）。
- 处理：把 writer 的 `decimal_precision` 提到 8，使往返误差 < 1e-6；
  **比对容差保持 1e-6 不变**——刻意不放宽容差来让测试变绿，因为那会把真正的映射错误一起掩盖。
- 结果：0/80 失败。
- 状态：已修复

## D021 | 2026-10-19 | 读回后障碍物顺序不保证（解析陷阱）
- 现象：双车场景（ego + 前车）下速度比对全部失败。
- 原因：最初按 `dynamic_obstacles[0]` 取 ego；XML 往返后顺序不保证，取到了前车。
- 处理：改为按写入时分配的 `obstacle_id == 1` 匹配，并在代码中注释说明该陷阱。
- 状态：已修复

## D022 | 2026-10-19 | Gate D 定为 PARTIAL 而非 PASS
- 完成：CommonRoad 适配器用真实 `commonroad-io 2026.1` 验证——XML 往返 0/80 失败、
  两后端轨迹逐位一致（1e-9）、失效类别一致 80/80（collision 77、near_miss 3）。
- 未完成：没有接入任何第三方**动力学**引擎。rollout 仍是本项目的运动学循环，
  只把**判定层**（碰撞/越界几何）换成了 CommonRoad 的实现。
- 判定：这验证了"失效标签不依赖自写 OBB 实现"，是有价值的排除性证据；
  但**不构成**跨仿真器结论。因此 Gate D 记为 **PARTIAL**，禁止表述为 PASS 或"用 CommonRoad 复现了实验"。
- `capabilities()` 中显式写入 `independent_dynamics=False`、`third_party_dynamics_engine=False`，
  让"不是仿真器"这件事无法被后续使用者误读。
- 升级为 PASS 的条件（需协议 v3 预先声明）：接入真实动力学引擎 → 重跑候选集 →
  报告异构动力学下的失效复现率。
- 状态：已记录，PARTIAL

## D023 | 2026-10-19 | 报告数字与原始产物脱钩（三处真实错误），加机器化防复发
- 现象：`docs/FINAL_REPORT.zh-CN.md` 的"实际输出"块写成 `stable=60 yield=0.8906`——
  60/64 = 0.9375，0.8906 是 57/64；这两个数不可能同时成立。H1 引用 Wilson 下界 `0.8500`
  （v2.0 值），H2 引用 Newcombe 区间 `[−0.0748, +0.1084]`（v2.0 值），而 v2.1 是
  `[−0.0365, +0.1668]`。
- 根因：v2.1 重跑后手工把 yield 更新到新值，但漏改相邻的 stable 计数与两个 CI；
  没有任何机制比对"文档里的数字"与"产物里的数字"。
- 独立复算（`scripts/audit_independent_recompute.py`，**不导入本项目统计模块**，
  自实现 Wilson / Newcombe / Fisher / paired bootstrap / Holm）从原始 holdout 文件
  与 discovery 报告重算，得到：random 57/64 = 0.890625、Wilson [0.791011, 0.946000]；
  mutation 61/64、[0.871001, 0.983931]；H2 Δ=+0.0625、[−0.036549, +0.166768]；
  H3 Δ=+0.366943、[+0.319086, +0.412848]。与产物一致，与旧文档不一致。
- 处理：修正文档三处数字并附重算说明；新增 `tests/test_doc_consistency.py`（8 项）
  把"文档数字必须等于产物"变成会失败的测试，同时禁止 Gate D 被写成 PASS、
  禁止逐文件测试表与源码脱节。测试总数 123 → 131。
- 顺带修正：逐文件测试表原只列 97 项且完全漏掉 `test_commonroad_interop.py`(11)，
  `test_sim_builtin.py` 与 `test_cli_endtoend.py` 仍是旧计数。
- 状态：已修复并有回归测试

## D024 | 2026-10-19 | 公开发布采用独立脱敏副本，不改写科研仓库历史
- 约束：本地 git 历史的提交元数据本身是干净的（`DriveEvidenceLab Team
  <team@driveevidencelab.invalid>`），泄漏的是**文件内容**里的绝对家目录路径
  （本机 Windows 账户名），出现在 `tests/acceptance-round2.md` 与未跟踪的
  `.workbuddy/memory/MEMORY.md`。历史 blob 中也存在该路径。
- 备选：(a) 在现有仓库 `filter-repo` 重写历史 —— 会改变所有提交哈希，使文档中引用的
  冻结提交锚点失效，且 `runs/` 不在 git 中、重写并不能提升可核验性；(b) 另建脱敏副本。
- 决定：(b)。本地科研仓库与完整历史保持不变；`scripts/build_public_release.py`
  从 `git ls-files` 构建公开副本，只对家目录段做 `<LOCAL_HOME>` 脱敏，
  记录逐文件脱敏日志与全部文件 SHA-256，并写成**单一整理提交**。
- 披露：公开副本的 `PUBLIC_RELEASE.md` 明确说明"这是一次整理后的提交，不是原始研发历史"，
  并给出不依赖 git 的核验锚点（协议正文哈希、证据束校验和），使第三方仍可核验冻结协议。
- 禁止：不 push、不建远端、不创建 Release，直到用户明确授权。
- 状态：已实施（本地副本），未发布

## D025 | 2026-10-20 | 发布前 Red Team 独立审查：修两处真实缺陷 + 补开源体验
- 背景：用户下达"最终科研与开源发布审查"总任务，要求代码作者不得单独验收自己模块，
  必须交叉审查。本轮改动（版本统一、公共 API 导出、CI、SDK 示例、Issue/PR 模板）经
  独立子智能体（Explore）审查，发现 2 个真实缺陷 + 2 个隐患。
- 缺陷 1（真实）：`docs/API.md` 的统计函数示例用 `wilson_ci(60,64)` /
  `newcombe_diff_ci(60,64,61,64)`——60/64 是 v2.0 值，读者无法区分示例与正式结果。
  且 `test_doc_consistency.py` 只查 FINAL_REPORT/README，漏了 API.md。已改为 v2.1 的
  57/64 并加注释 + 新增 `test_api_doc_examples_use_v21_numbers`。
- 缺陷 2（真实）：`build_public_release.py` 检测到 PLACEHOLDER URL 后只写进
  PUBLIC_RELEASE.md 说明，`return 0` 无条件——带 `--commit` 的发布动作仍会成功，门是
  装饰性的。已改为 `--commit` 且存在 blocker 时 exit 1 拒绝；无 `--commit` 的预览构建
  仍 exit 0（CI 用它做隐私扫描）。新增 `tests/test_release_gate.py`(2)。
- 隐患（接受，不改）：`__version__` 的 importlib.metadata fallback `"0.2.0"` 是第二份
  硬编码版本号，与"单一来源"注释有轻微矛盾，但属标准做法，权衡后保留。
- 开源体验补齐：新增 `.github/ISSUE_TEMPLATE/{bug_report,feature_request,question}.md`
  与 `.github/pull_request_template.md`（此前完全缺失）；README 双语补 SDK 示例入口。
- 版本统一：`__version__` 从硬编码 0.1.0 改为 importlib.metadata 读取（fallback 0.2.0），
  消除与 pyproject.toml 0.2.0 / tag v0.2.0-research-preview 的三处不一致。
- 测试总数 131 → 144（新增 test_public_api 8、test_example 1、test_release_gate 2、
  test_doc_consistency +2）。
- 状态：已修复并有回归测试；T3 外部复现与 v3 第三方动力学仍不具备（见 LIMITATIONS.md）。
