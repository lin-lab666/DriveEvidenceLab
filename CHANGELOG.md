# Changelog

本项目遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

## [0.2.0] — 2026-10-19

### 科学有效性（破坏性修正）

- **撤回**协议 v1 的 `stable failure yield` 数值与基于它的 H1/H2 稳定性结论。
  原因：`builtin` 仿真器创建 `rng = default_rng(seed)` 后从未使用，v1 的 holdout
  种子对结果零影响；1716/1716 候选在 3 个"独立种子"下逐位相同，"稳定率 100%"
  是同义反复。
- **撤回** v1 的 primary 指标 `前16确认数 / 全部提名数`：在全部候选稳定时它恒等于
  `16 / 提名数`，只反映提名规模，不反映稳定性。
- **修正** H1 的适用对象：协议仅对随机搜索定义，v1 报告越界应用到两种方法。

### 新增

- `docs/PROTOCOL-frozen-v2.md` + `docs/PROTOCOL-v2.freeze.json`：修正版协议，
  运行前冻结；采用可复现的**正文哈希**约定（v1 的内嵌自指哈希不可核验）。
- `driveevidence.scenario.perturb`：确定性、结构保持、有界的场景 ε-扰动
  （`eps-perturb/1.0`），使 holdout 种子成为有语义的输入变化。
- `docs/SCIENTIFIC_AUDIT.zh-CN.md`：三层（内部一致性 / 方法学有效性 / 外部复现）审计报告。
- `scripts/run_formal_experiment_v2.py`：全新种子的 64×master_seed 配对实验。
- `scripts/audit_scientific_validity.py`：不信任 `summary.json` 的独立重算审计。
- `scripts/verify_evidence_bundle.py`：第三方核验压缩证据束。
- `evidence/`：v2 完整证据包与 v1 holdout 明细（压缩 + SHA-256 清单）。
- `docs/ARCHITECTURE.md`、`docs/API.md`、`CONTRIBUTING.md`、`NOTICE`、`docs/RELEASE_CHECKLIST.md`。
- 统计工具：`newcombe_diff_ci`、`fisher_exact_two_sided`、`binomial_tail_p`、`bootstrap_p_value`。
- `scripts/audit_seed_coupling.py`：量化 random/mutation 的 RNG 耦合（逐对场景序列重合度）
  并对 H3 做分层敏感性分析（D019-C）。
- **`commonroad` 后端**（`sim/commonroad_adapter.py`）：把 IR 映射为真实的
  `commonroad.scenario.Scenario`，经 CommonRoad XML 往返并交由 CommonRoad 自身
  `check_validity` 校验；碰撞改用 `RectObstacleShape` 占位 + shapely 相交，越界改用
  lanelet 多边形并集包含判定。`capabilities()` 显式声明 `independent_dynamics=False`、
  `third_party_dynamics_engine=False`。
- `scripts/verify_commonroad_interop.py`：用正式实验的真实候选交叉核对两个后端的
  场景交换、轨迹与失效类别。
- `docs/GATE_D.zh-CN.md`：Gate D 的真实进展、已验证范围与未完成部分。
- 可选依赖组 `commonroad`（`pip install driveevidence[commonroad]`）。

### 修复

- **replay 配置丢失（D014）**：`EpisodeStore.replay_kwargs` 只读 `raw.config`，
  忽略 builtin 写在 `raw` 顶层的 `max_steps`，导致重放退回默认 300 步。
  症状：`max_steps=80` 的 timeout episode 重放后 steps 81→301、`final_x_m` 漂移
  274 m，但 **category 仍然一致**——只看类别会漏判。现已恢复顶层配置并新增
  4 项回归测试。
- **NEAR_MISS 不可达死代码（D017）**：`builtin` 的 `for ... else` 在循环正常结束
  时无条件把 `category` 赋为 `TIMEOUT`，导致其后的近失判定块永远不执行。
  实证：v1 的 8192 episodes 与 v2.0 的 8192 episodes 中 `near_miss` 出现次数
  均为 0，失效率分类实际退化为"只有 collision"。已在 `builtin/1.1` 中把近失
  判定移入 `else` 分支，重跑后 `near_miss` 出现 57 次。新增 3 项可达性测试。
  后端版本号 `builtin/1.0` → `builtin/1.1`。
- **CLI 对非法输入抛原始 traceback**：`audit`/`report`/`replay` 遇到不存在的 run 目录、
  缺 `ledger.jsonl`、坏 JSON、非法场景时直接抛出 `LedgerError`/`FileNotFoundError` 栈。
  现统一在 CLI 边界捕获：可预期的用户错误打印 `error: ...`，不可预期的异常打印
  `internal error: ...`（明确标注这是本包 bug，不是用户输入问题），均返回退出码 2；
  设 `DRIVEEVIDENCE_DEBUG=1` 可恢复完整 traceback。新增 9 项测试。
- **`replay` 类别不一致时返回 0**：原先 `return 0 if match else 0`，使 CI 无法发现
  复现失败。现不一致时打印 WARNING 并返回 1。
- **测试硬编码本机解释器路径**（`tests/test_cli_endtoend.py` 内写死
  `C:/Users/.../python.exe`），其他机器无法运行端到端测试。改用 `sys.executable`。

- **CommonRoad XML 精度导致的假失败（D020）**：writer 默认 `decimal_precision=4`，
  使 80 个候选中的 71 个在 1e-6 容差下比对失败（实际偏差 4e-5）。提高序列化精度到 8，
  **未**放宽容差。
- **XML 往返后障碍物顺序不保证（D021）**：原先按 `dynamic_obstacles[0]` 取 ego，
  双车场景下取到前车。改为按 `obstacle_id` 匹配。

### Gate D（部分完成，非 PASS）

- CommonRoad 适配器已用真实 `commonroad-io 2026.1` 验证：XML 往返 0/80 失败、
  两后端轨迹逐位一致 80/80、失效类别一致 80/80（collision 77、near_miss 3）。
- **未接入第三方动力学引擎**，rollout 仍是本项目运动学，只换了判定层。
  因此 Gate D 记为 **PARTIAL**，不得表述为 PASS 或"用 CommonRoad 复现了实验"。
  CARLA 仍未实现，保持 `NOT VERIFIED`。

### 文档（补充说明，非行为变更）

- `docs/API.md` 明确 `EpisodeResult.steps` 的语义：它是**轨迹采样点数**而非积分步数，
  timeout 时 `steps == max_steps + 1`。轨迹本身完整无重复；不改字段值，因为改动会
  破坏已归档 v1/v2 证据的逐位重放。新增 3 项测试固化该语义。

### 变更

- 版本号 `0.1.0` → `0.2.0`。
- `scripts/run_all.sh` 不再硬编码解释器路径（`PYTHON` 环境变量可覆盖），
  新增证据核验步骤与 `--with-formal` 选项。
- **测试数 67 → 112。**

### 结果（协议 v2.1，`builtin/1.1`，真实运行）

| 方法 | discovery yield [95% CI] | 实测 | 稳定 | stable yield [95% CI] |
|---|---|---|---|---|
| random | 0.0444 [0.0385, 0.0512] | 64 | 57 | 0.8906 [0.7910, 0.9460] |
| mutation | 0.4114 [0.3964, 0.4265] | 64 | 61 | 0.9531 [0.8710, 0.9839] |

H1 支持（Wilson 下界 0.7910 > 0.1，Holm p=9.03e-49）；
H2 **不支持**（Δ=+0.0625，Newcombe 95% CI [−0.0365, +0.1668]，Fisher p=0.324）；
H3 支持（Δ=+0.3669，配对 bootstrap 95% CI [0.3218, 0.4124]，Holm p=0.001）。

> 同一协议在 `builtin/1.0` 下的 v2.0 运行结果为 random 0.9375 (60/64)、
> mutation 0.9531 (61/64)。两次运行假设方向一致、量级不同，作为协议偏差
> 并列保留（`runs/formal_experiment_v2/` 与 `runs/formal_experiment_v2p1/`），
> 未覆盖、未择优。

## [0.1.0] — 2026-10-19

- 首个可安装骨架：scenario IR v1、builtin 与 highway-env 适配器、规则规划器、
  随机/变异搜索、统计估计、哈希链账本、episode 归档、manifest、replay、CLI、报告生成。
- 67 项测试；Gate A/B/C/F 本地通过；Gate D（CommonRoad/CARLA）未验证。
  （**历史状态**：0.2.0 起 Gate D 为 **PARTIAL**，见 `docs/DECISIONS.md` D022。）
- 注：本版本的 Gate E 稳定性结论已在 0.2.0 中撤回，请勿引用。
