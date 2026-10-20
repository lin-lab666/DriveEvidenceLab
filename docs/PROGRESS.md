# PROGRESS（进度实录）

> 只记录真实发生的事。每个 Gate 更新。不写计划当成果。

## 2026-10-19（下午/晚间）

### Gate A — 调研与方案冻结：PASS（总指挥复核）
- 启动包治理文档已纳入（SPEC / RESEARCH_PROTOCOL / ACCEPTANCE_AND_RELEASE / CODEBUDDY）。
- `docs/RELATED_WORK.md` 完成：Scenic/CARLA ScenarioRunner/SafeBench/ScenicRules/CommonRoad/MultiSim 的许可证与差异化边界已核实并记录。
- `docs/PROTOCOL-frozen-v1.md` 完成并签署 protocol_sha256：`247f6721ee26ae76e7e9258e3e43065ea2189fe4d37254ff62b8074ae8e92e29`。
- 研究方案 v0.2 已通过 Step-5-Preview 独立复审（3.00/3）。

### Gate B — CPU 真跑闭环：PASS（总指挥复核）
- `driveevidence.sim.builtin`：确定性运动学 straight-road 仿真器，支持 COLLISION/OFF_ROAD/RULE_VIOLATION/NEAR_MISS/TIMEOUT/INFEASIBLE。
- `driveevidence.sim.highwayenv_adapter`：真实 highway-env 1.12.1 适配器；明确声明 exact IR placement 为近似映射。
- 规划器：`constant_speed`、`safe_follow`（IDM-lite）。
- 测试：9 项 builtin 测试 + 3 项 highway-env 真实集成测试全部通过。

### Gate C — 研究核心：PASS（总指挥复核）
- Scenario IR v1：确定性的 canonical 编码与 sha256 场景哈希、合法性验证。
- Search：`RandomSearch` + `MutationSearch`，共享 Budget 规则，完整 budget 记账不变式。
- Stats：Wilson CI、stable failure yield、配对 bootstrap、Cohen's h、Holm、Benjamini-Hochberg。
- Evidence：`RunLedger` 哈希链、`EpisodeStore`、manifest、replay；recorder.py 迁移后 24/24 通过。
- 测试：search 6 项 + stats 10 项 + evidence 10 项 + recorder 24 项全部通过。

### Gate D — 第二仿真系统：PARTIAL（部分验证，非 PASS）
- 已安装 `commonroad-io 2026.1` 并实现 `commonroad` 后端（`sim/commonroad_adapter.py`）。
- 真实数据交叉核对（`scripts/verify_commonroad_interop.py`，80 个正式实验候选）：
  - CommonRoad XML 往返失败 **0/80**（由 CommonRoad 自己的 `check_validity` 校验场景合法性）
  - 两后端轨迹逐位一致 **80/80**（动力学同构，容差 1e-9）
  - 失效类别一致 **80/80**（collision 77、near_miss 3）→ 失效标签不依赖本项目自写的 OBB 实现
- **未完成**：没有接入任何第三方**动力学**引擎，rollout 仍是本项目运动学，只换了判定层。
  因此**不构成**跨仿真器结论，Gate D 记 **PARTIAL**。
- 已在 `capabilities()` 中写死 `independent_dynamics=False`、`third_party_dynamics_engine=False`。
- CARLA 仍未实现，标记 NOT VERIFIED。
- 详见 `docs/GATE_D.zh-CN.md`；决策 D020/D021/D022。

### Gate E — 实验与审计：PASS（经 v2.1 修正后成立）

**v1 的稳定性结论已被撤回**（缺陷与证据见 `docs/SCIENTIFIC_AUDIT.zh-CN.md`）：
- builtin 仿真器创建 `rng(default_rng(seed))` 后从未使用 → holdout 种子无效果；1716/1716 候选在 3 个种子下逐位相同，"稳定率 100%" 是同义反复。
- v1 primary 指标「前 16 确认数 / 全部提名数」在全部稳定时恒等于 `16/提名数`，只反映提名规模（random 16/144=0.1111，mutation 16/1572=0.0102）。
- 因此 v1 的 stable yield 数值与基于它的 H1/H2 稳定性结论**全部撤回**；v1 的 `discovery_yield` 与预算记账仍然有效。

**v2 修正实验（`docs/PROTOCOL-frozen-v2.md`，运行前冻结）**：
- 全新种子：discovery 2100–2163（64 个），扰动池 4100–4119，抽样 seed 4000；每方法 budget=64。
- holdout 改为**初始条件 ε-扰动**（ego 速度 ±2 m/s、横向 ±0.15 m、他车间距 ±3 m、他车速度 ±1.5 m/s），每候选 3 次，≥2 次同类别算稳定。
- 候选选择：预注册均匀随机抽 64 个/方法（可复现校验通过，无顺序偏差）。

| 方法 | discovery episodes | discovery yield [95% CI] | 提名 | 实测 | 稳定 | stable yield [95% CI] |
|---|---|---|---|---|---|---|
| random | 4096 | 0.0444 [0.0385, 0.0512] | 182 | 64 | 57 | 0.8906 [0.7910, 0.9460] |
| mutation | 4096 | 0.4114 [0.3964, 0.4265] | 1685 | 64 | 61 | 0.9531 [0.8710, 0.9839] |

> **后端修正导致的协议偏差（D017）**：以上为 `builtin/1.1`（v2.1 运行）的结果。
> 首次 v2 运行使用 `builtin/1.0`，该版本的 `NEAR_MISS` 判定分支因 `for ... else`
> 先把 `category` 置为 `TIMEOUT` 而永不可达（v1 与 v2.0 共 16384 个 episode 中
> `near_miss` 出现 0 次）。修正后 `near_miss` 出现 57 次，随机搜索的稳定率从
> 0.9375（60/64）变为 0.8906（57/64）。两次运行的产物并列保留在
> `runs/formal_experiment_v2/`（1.0）与 `runs/formal_experiment_v2p1/`（1.1），
> 未覆盖、未择优；假设方向一致，量级不同。

假设检验（Holm 校正，族大小 3）：
- **H1 支持**：random stable yield Wilson 下界 0.7910 > 0.1（p=9.03e-49）。
- **H2 不支持**：Δ=+0.0625，Newcombe 95% CI [−0.0365, +0.1668] 含 0（Fisher p=0.324，h=0.2377）。
- **H3 支持**：mutation 的 discovery yield 显著更高，Δ=+0.3669，配对 bootstrap 95% CI [0.3218, 0.4124]（Holm p=0.001）。

工程与完整性：发现阶段 13.39s + holdout 阶段 6.51s（共 20.19s）；ledger 260 条哈希链完整；manifest 零失配；归档 episode 重放 5/5 一致。
审计：T1 内部一致性 15/15；T2 方法学有效性 v2 通过、保留 1 项 FAIL（v1 协议哈希不可核验）；T3 外部复现不具备。
证据路径：`runs/formal_experiment_v2p1/`（`audit.json`、`report.md`、`summary.json`、`selection.json`、`ledger.jsonl`、`manifest.json`、`seed_coupling.json`）。

**补充审计（D019-C）：两方法 RNG 耦合的实际程度**
- 逐对比较两方法 64 个 episode 的场景序列：重合数 min=1、median=16、mean=23.0、max=64；17/64 对至少一半相同。
- **4 对完全退化**（seed 2100/2138/2144/2161）：mutation 与 random 执行了逐位相同的 64 个场景——mutation 在 archive 为空时退化为随机初始化且共用同一 RNG 流。这 4 个 seed 恰是两方法候选数均为 0 的 seed。
- H3 分层敏感性：全部 64 对 Δ=+0.3669 [+0.3218,+0.4124]；剔除退化对 n=60 Δ=+0.3914 [+0.3490,+0.4333]；
  低重合层 n=31 Δ=+0.5096 [+0.4844,+0.5328]；高重合层 n=33 Δ=+0.2330 [+0.1799,+0.2865]。各层 CI 均排除 0。
- **解释边界**：重合会使配对差值向 0 收缩，这是对"观测差值幅度"的机制性解释，**不是**已证明的
  偏差方向。分层只支持"结论方向在分层后依然成立"，**不支持**"合并估计必然保守"——分层是对同一
  数据的事后重组，不构成因果识别。
- 先前"仅 round 0 共享 1/64"的评估**已被推翻并更正**；脚本 `scripts/audit_seed_coupling.py` 可复现。

### Gate F — 开源工程：PASS（本地可安装/可运行）
- CLI：`doctor / sample / run / search / audit / replay / report` 全部可用；仓库外临时目录跑通完整链路（sample → run → audit → search → audit → report md/html）。
- CLI 错误处理：非法/缺失输入不再抛 traceback，统一 `error:` + 退出码 2（`DRIVEEVIDENCE_DEBUG=1` 可看栈）；`replay` 类别不一致改为退出码 1。新增 9 项测试。
- **wheel 干净安装验证**：构建 `driveevidence-0.2.0-py3-none-any.whl`，装入全新 venv
  （除 pip 外仅 numpy），在仓库外目录跑通 sample → run → search → audit → replay → report；
  replay 类别一致、指标差全 0.0；同一环境重算 Wilson `[0.791, 0.946]` 与
  Newcombe `+0.0625 [-0.0365, 0.1668]`，与仓库内结果一致。
- 可选依赖缺失时优雅降级（`doctor` 逐项 `NOT INSTALLED (optional)`，核心链路照常运行）；
  `doctor` 区分源码检出与已安装包。
- README（中英双语）、LICENSE Apache-2.0、.gitattributes、run_all.sh。
- 全测试套件：**144 项通过**（0 失败）。
- 正式实验脚本：`scripts/run_formal_experiment_v2.py`、`scripts/audit_scientific_validity.py`、`scripts/verify_evidence_bundle.py`、`scripts/audit_seed_coupling.py`。
- GitHub 远程发布与 Release **未执行**（无 gh CLI，且需用户最终确认）。

### 关键未决事项
- DeepSeek 模型路由疑点：子智能体自报底层为 GLM-5.3，与派发指定不一致；已标记为未确认（D004），不影响本阶段可交付功能。
- Gate D 要升到 PASS：需接入第三方动力学引擎并按协议 v3 重跑候选集（CARLA 仍未实现）。
- `docs/PROTOCOL-frozen-v1.md` 末尾声明的 protocol_sha256 与实际文件 hash 不一致；建议治理流程检查签署脚本。

---

## 2026-10-19（发布前最终科研与开源审查）

### 报告一致性修复（D023）
- 发现三处真实错误：`stable=60` 与 `yield=0.8906` 并存（不可能同时成立，0.8906 = 57/64）；
  H1 引用 v2.0 的 Wilson 下界 `0.8500`；H2 引用 v2.0 的 Newcombe 区间 `[−0.0748, +0.1084]`。
- 用**独立实现**重算（`scripts/audit_independent_recompute.py`，不导入项目统计模块）：
  random 57/64 = 0.890625、Wilson [0.791011, 0.946000]；mutation 61/64、[0.871001, 0.983931]；
  H2 Δ=+0.0625、[−0.036549, +0.166768]；H3 Δ=+0.366943、[+0.319086, +0.412848]。全部与产物一致。
- 逐文件测试表原只列 97 项（漏 `test_commonroad_interop.py` 11 项，builtin/CLI 计数陈旧），
  已按源码重算对齐，并新增 8 项文档一致性测试锁定，总数 123 → 131。
- `tests/test_doc_consistency.py`：文档数字必须等于产物；Gate D 不得被写成 PASS；
  逐文件计数必须与源码一致。历史 CHANGELOG 条目加"历史状态"标注。

### 局限披露与 v3 决策
- 新增 `docs/LIMITATIONS.md`：按"结论会被怎样误用"组织，含三层结论状态、仿真器/场景族/
  统计/可复现性/工程五类局限、十类禁止引用表述、以及一条"可以这样引用"的合规模板。
- 明确写出 H2 是"未检出差异"而非"等价"；明确写出高稳定率**无法区分**"失效稳健"与
  "场景本身必然失效"这一解释性缺口。
- 协议修订史 v1 → v2.0 → v2.1 完整披露，三套产物并列保留。
- v3（第三方动力学）评估见 `docs/PROTOCOL-v3-draft.md`（草案，未冻结、未执行、无结果）。

### 公开发布脱敏（D024）
- `scripts/privacy_scan.py`：分三面扫描——文件内容、路径名、git 历史 blob + 提交元数据。
  本地仓库命中 3 处（`tests/acceptance-round2.md` 2 处、未跟踪的 `.workbuddy/memory` 1 处），
  提交元数据干净（`DriveEvidenceLab Team`）。
- `scripts/build_public_release.py`：从 `git ls-files` 构建公开副本，只脱敏家目录段为
  `<LOCAL_HOME>`，生成 `PUBLIC_MANIFEST.json`（全文件 SHA-256）与 `PUBLIC_RELEASE.md`
  （脱敏日志 + 冻结协议哈希 + 证据束校验和 + 明确"整理后历史"的披露）。

---

## 2026-10-20（最终科研与开源发布审查，D025）

按"一次性完整任务授权"执行：审查 → 拆解 → 开发 → 独立交叉审核 → 测试 → 修正 → 集成 → 发布准备。

### 修复的真实缺陷
- README 双语结果表残留 v2.0 的 `stable 60`（应为 57），且 `test_doc_consistency` 漏查 README。
- `__version__` 硬编码 0.1.0，与 pyproject 0.2.0 / tag 三处不一致 → 改 importlib.metadata。
- Quickstart 用 `--seed 2100`（0 candidates 退化种子）→ 改 2101。
- `docs/API.md` 统计示例用 v2.0 的 60/64 → 改 57/64（独立审查发现）。
- 发布门 PLACEHOLDER blocker 不阻断 exit code → `--commit` 时拒绝（独立审查发现）。
- `tests/acceptance-round2.md` 工作树含 2 处家目录路径 → 脱敏（历史 blob 保留，D024）。

### 新增
- search/planners/stats/report 子包公共 API 导出 + `test_public_api.py`(8)。
- `examples/minimal_sdk_example.py` 可运行 SDK 示例 + `test_example.py`(1)。
- Issue/PR 模板（bug/feature/question + PR checklist）。
- CI：装 commonroad（11 项真跑）、CLI 冒烟扩到 7 子命令、新增 evidence job。

### 验证
- **144 项测试全通过**；`run_all.sh` exit 0（含 CommonRoad 80/80 类别一致、种子耦合审计、证据包核验）。
- wheel 干净 venv 安装：version=0.2.0、公共 API 可导入、Wilson(57,64)=[0.791,0.946]。
- 公开副本 115 文件、0 脱敏、隐私扫描 CLEAN。
