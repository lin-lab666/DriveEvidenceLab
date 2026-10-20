# DriveEvidenceLab｜最终交付报告

> 日期：2026-10-19　｜　总指挥：GLM-5.3　｜　仓库：`D:/DriveEvidenceLab`（本地）
> 科学审计报告：[`docs/SCIENTIFIC_AUDIT.zh-CN.md`](SCIENTIFIC_AUDIT.zh-CN.md)
> 实验协议：[`docs/PROTOCOL-frozen-v2.md`](PROTOCOL-frozen-v2.md)

---

## 1. 项目状态

- **当前提交**：`f0115ca`（其后为文档补全提交）。
- **工作区状态**：干净，全部变更已提交。
- **版本**：`driveevidence 0.2.0`，可 `pip install -e .` 安装，`driveevidence` 命令可用（已在仓库外目录验证）。

**模块完成度**

| 模块 | 状态 | 说明 |
|---|---|---|
| `scenario/ir.py` | ✅ 完成 | IR v1，canonical 哈希，validate 与安全判据分离 |
| `scenario/perturb.py` | ✅ 完成（v2 新增） | 确定性、结构保持、有界 ε-扰动 |
| `sim/builtin.py` | ✅ 完成 | 确定性运动学直道仿真器 |
| `sim/highwayenv_adapter.py` | ✅ 可运行 | highway-env 1.12.1 真实适配；IR 摆位为近似映射，已声明 |
| `planners/rule_based.py` | ✅ 完成 | `constant_speed`、`safe_follow`（IDM-lite） |
| `search/` | ✅ 完成 | Budget 不变式、RandomSearch、MutationSearch |
| `stats/estimators.py` | ✅ 完成 | Wilson、Newcombe、Fisher、bootstrap、Cohen's h、Holm、BH |
| `evidence/` | ✅ 完成 | 哈希链账本、episode 归档、manifest、replay、recorder |
| `report/` | ✅ 完成 | Markdown / HTML |
| `cli/` | ✅ 完成 | 7 个子命令，端到端测试覆盖 |
| CommonRoad | ⚠️ 适配器已用真实 `commonroad-io 2026.1` 验证（部分完成） | 场景交换 / 判定语义已交叉核对；**未接第三方动力学**，故为 PARTIAL 而非 PASS |
| CARLA | ❌ 未实现 | 接口预留，标记 NOT VERIFIED |
| CornerCaseLab / SafeFlipLab 兼容 | ❌ 未实现 | 见 §8 |

---

## 2. Gate A→F 总表

| Gate | 状态 | 验收依据 | 证据位置 | 剩余阻塞 |
|---|---|---|---|---|
| **A 方案与协议冻结** | **PASS** | 研究方案 v0.2 经 Step-5-Preview 独立复审 3.00/3；协议 v2 正文哈希可复现 | `research/algorithm-design-v0.2.md`、`research/review-algorithm-design-v2.md`、`docs/PROTOCOL-frozen-v2.md`、`docs/PROTOCOL-v2.freeze.json` | 无 |
| **B CPU 真跑闭环** | **PASS** | builtin + highway-env 真实运行；确定性、碰撞、越界、超速、超时、不可行均有测试 | `tests/test_sim_builtin.py`(15)、`tests/test_sim_highwayenv_integration.py`(3) | 无 |
| **C 研究核心** | **PASS** | IR、搜索、统计、证据四层实现并被端到端测试覆盖 | `tests/test_search.py`、`tests/test_stats.py`、`tests/test_ledger.py`、`tests/test_cli_endtoend.py` | 无 |
| **D 第二仿真系统** | **PARTIAL（部分验证）** | CommonRoad 适配器已用真实 `commonroad-io 2026.1` 验证：80 个真实候选的 XML 往返 0 失败、轨迹逐位一致、失效类别一致 80/80；**但动力学仍为本项目运动学，未接第三方引擎** | `src/driveevidence/sim/commonroad_adapter.py`、`scripts/verify_commonroad_interop.py`、`runs/formal_experiment_v2p1/commonroad_interop.json`、`docs/GATE_D.zh-CN.md` | 需接入第三方动力学引擎并重跑候选集，才能升级为 PASS |
| **E 实验与审计** | **PASS（经 v2.1 修正）** | 协议 v2 的 8192+384 episodes 真实执行（后端 `builtin/1.1`）；独立审计 T1 15/15、T2 4/5；H1/H2/H3 判定可重算 | `runs/formal_experiment_v2p1/`、`evidence/gateE-v2p1-full.tar.gz`、`audit.json` | 无外部复现（T3） |
| **F 开源工程** | **PASS（本地）** | 144 项测试、CLI、双语文档、CI、证据核验脚本 | 全仓库 | GitHub 公开与 Release 需用户授权 |

> ⚠️ **Gate E 的重要更正**：v1 的 Gate E 曾标记 PASS，但其稳定性结论已被撤回（原因见 §5.1）。
> 现在的 PASS 只对协议 v2 成立。

---

## 3. 智能体交付情况

| 角色 | 派发模型 | 实际交付 | 说明 |
|---|---|---|---|
| 总指挥 | GLM-5.3 | 架构、契约、全部模块实现、实验与审计 | 自报确认 |
| 算法工程师 | GLM-5.3 | 研究方案 v0.1/v0.2、相关工作、协议 v1 | 自报确认 |
| 科研审查员 | Step-5-Preview | 审查清单、v0.1 审查（打回）、v0.2 复审（通过） | 自报确认；本次审计另派后台独立复核 |
| 编程工程师 | DeepSeek-V4.1-Flash | Round 1 交付 recorder.py（24 项测试） | **模型身份未确认**：子智能体自报底层为 GLM-5.3 |
| 测试工程师 | DeepSeek-V4.1-Flash | 测试套件、独立验收记录 | **模型身份未确认**；身份不确定性不归因于结果正确性 |

**必须如实说明的三点**

1. **Round 4 的 4 个并行子智能体全部因全局 429 限流启动失败**，由总指挥直接完成对应模块；未冒充子智能体身份。
2. **DeepSeek 路由疑点未解决**：两次成功派发中，子智能体自报底层为 `glm-5.3`。可能是提供商故障时的静默回退，也可能是环境信息噪声，从子智能体内部无法区分。所有相关记录标注 `identity-unconfirmed`。
3. 所有代码提交署名为 `DriveEvidenceLab Team`，未使用真实个人身份。

---

## 4. 测试报告

**最终结果**

```
$ PYTHONPATH=src python -m unittest discover -s tests -p "test_*.py"
Ran 144 tests in 85.698s
OK
```

> 耗时随可选依赖变化：未装 `commonroad-io` 时 11 项自动 skip，约 26 s；
> 装齐 `[sim,dev]` 后为 86 s。测试数不变（skip 的用例仍计入 `Ran`）。

| 测试文件 | 数量 | 覆盖 |
|---|---|---|
| `test_recorder.py` | 24 | 证据链记录器 API、JSON roundtrip、异常路径 |
| `test_stats.py` | 22 | Wilson/Newcombe/Fisher/bootstrap/Holm/BH，含已知值校验 |
| `test_sim_builtin.py` | 15 | 确定性、碰撞、越界、超速、超时、不可行、NEAR_MISS 可达性、`steps` 语义 |
| `test_perturb.py` | 15 | 扰动确定性、带宽、结构不变、无重叠下限 |
| `test_cli_endtoend.py` | 14 | 7 个 CLI 子命令的真实调用链 + 统一错误边界（9 项非法输入） |
| `test_ledger.py` | 13 | 哈希链、篡改检测、manifest、replay 配置保真 |
| `test_commonroad_interop.py` | 11 | IR→CommonRoad 往返、`check_validity`、类别一致、缺库时 skip |
| `test_doc_consistency.py` | 10 | 文档数字必须等于原始产物；Gate D 口径不许回退；逐文件计数自校验；README/API.md 不得混入 v2.0 数字 |
| `test_public_api.py` | 8 | 包级 `__all__` 导出与版本一致性，防止重构破坏文档化导入路径 |
| `test_search.py` | 6 | Budget 不变式、两方法等预算、确定性 mock |
| `test_sim_highwayenv_integration.py` | 3 | highway-env 真实 episode + 同 seed 复现 |
| `test_release_gate.py` | 2 | 发布门：PLACEHOLDER URL 阻断 `--commit`，预览构建放行 |
| `test_open_source_quality.py` | 12 | 公开 demo 可运行、案例包 SHA256SUMS 完整、README 图表/链接/双语数字一致性 |
| `test_example.py` | 1 | 子进程执行 `examples/minimal_sdk_example.py`，防止示例与 API 脱节 |
| **合计** | **156** | 与 `Ran 156 tests` 一致 |

**开发过程中真实出现并修复的失败**（不隐藏）

| 失败 | 根因 | 修复 |
|---|---|---|
| 适配器未注册 | `sim/__init__.py` 未 import 子模块 | 补 import |
| 规划器 `default` 查不到 | 注册表用别名而非真实名 | 注册时同时绑别名 |
| off-road 测试未触发 | 测试把 ego 放在道路外但检测在记录前 | 修正测试构造 |
| Wilson 上界浮点越界 0.9999… | 边界舍入 | 显式钳制 |
| Holm 测试期望值写错 | 测试笔误（算法正确） | 修测试而非改实现 |
| **replay 配置丢失** | `replay_kwargs` 忽略 `raw.max_steps` | 恢复顶层配置 + 4 项回归测试（见 §5.2） |

---

## 5. 端到端演示与实验结果

### 5.1 v1 结论撤回（必须先看这一节）

审计发现：`builtin` 仿真器创建 `rng = default_rng(seed)` 后**从未使用**。
六个不同 seed 跑同一场景，轨迹 SHA-256 完全相同（`1ab76b8b90eda348`）。
统计 v1 全部产物：**1716/1716 候选在 3 个"独立" holdout 种子下逐位相同**。

因此 v1 的 `stable yield = 100%` 是同义反复；其 primary 指标
`前16确认数 / 全部提名数` 退化为 `16 / 提名数`（random 16/144=0.1111，mutation 16/1572=0.0102），
度量的是**发现数量**而非稳定性。**v1 的稳定性数值与 H1/H2 结论已撤回。**

### 5.2 审计中发现并修复的真实缺陷（D014）

`EpisodeStore.replay_kwargs` 只读 `result.raw.config`，而 builtin 把 `max_steps` 记在 `raw` 顶层。
一个 `max_steps=80` 的 timeout episode 重放时退回默认 300 步：`steps` 81→301、
`final_x_m` 漂移 274 m，**但 category 仍然是 timeout**——只看类别会漏判。
修复后归档 episode 重放 5/5 完全一致。

### 5.3 协议 v2 正式实验（真实执行）

```bash
PYTHONPATH=src python scripts/run_formal_experiment_v2.py --out runs/formal_experiment_v2
PYTHONPATH=src python scripts/audit_scientific_validity.py
PYTHONPATH=src python scripts/verify_evidence_bundle.py
```

实际输出：

```
discovery 8192 episodes in 13.4s
holdout   384 episodes in 6.6s
random    tested=64 stable=57 yield=0.890625 [0.7910, 0.9460]
mutation  tested=64 stable=61 yield=0.953125 [0.8710, 0.9839]
H1 random stability supported : True
H2 method difference supported: False
H3 discovery replication      : True
ledger chain ok=True first_bad=None
```

| 方法 | discovery yield [95% CI] | 提名 | 实测 | 稳定 | stable yield [95% CI] | 单次扰动确认率 |
|---|---|---|---|---|---|---|
| random | 0.0444 [0.0385, 0.0512] | 182 | 64 | 57 | 0.890625 (57/64) [0.7910, 0.9460] | 0.8490 (163/192) |
| mutation | 0.4114 [0.3964, 0.4265] | 1685 | 64 | 61 | 0.953125 (61/64) [0.8710, 0.9839] | 0.9375 (180/192) |

| 假设 | 判据 | 结果 |
|---|---|---|
| H1（random 稳定性） | Wilson 95% 下界 > 0.1 | **支持**（下界 **0.7910**，Holm p=9.03e-49） |
| H2（方法差异） | Newcombe 95% CI 不含 0 | **不支持**（Δ=+0.0625，CI **[−0.0365, +0.1668]**，Fisher p=0.324，h=0.2377） |
| H3（发现率复现） | 配对 bootstrap 95% CI 不含 0 | **支持**（Δ=+0.3669，CI [0.3218, 0.4124]，Holm p=0.001） |

> 上表三个数值均可用 `scripts/audit_independent_recompute.py` 从原始产物独立重算
> （该脚本不导入本项目统计模块）。独立实现给出 H1 下界 0.791011、H2 CI
> [−0.036549, +0.166768]、H3 CI [+0.3191, +0.4128]，判定完全一致；H3 的
> 末端差异来自独立 RNG 的 bootstrap 抽取，不影响是否排除 0。

稳定性判据确实有鉴别力：random 有 4 个候选未过（3 个 1/3、1 个 0/3），
mutation 有 3 个未过（其中 1 个 3 次扰动全部转为 `timeout`）。

### 5.4 CLI 端到端（对外承诺的最小示例）

```bash
driveevidence run --scenario examples/scenarios/tailgate_risk.json \
                  --adapter builtin --seed 123 --run-id demo --out runs
driveevidence audit --run runs/demo        # ledger + manifest
driveevidence replay --run runs/demo --seq 1 --adapter builtin
driveevidence report --run runs/demo --format html --out runs/demo/report.html
```

产物：`runs/demo/{ledger.jsonl, manifest.json, episodes/0001.json, report.html}`。

---

## 6. 可复现性说明

1. **环境**：Python ≥3.10（本项目验证于 3.13.14），`pip install -e ".[sim,dev]"`。
2. **测试**：`PYTHONPATH=src python -m unittest discover -s tests -p "test_*.py"`。
3. **一键**：`bash scripts/run_all.sh`（加 `--with-formal` 会重跑正式实验到 `runs/formal_experiment_v2_rerun`，不覆盖参考产物）。
4. **正式实验**：`scripts/run_formal_experiment_v2.py`，种子、预算、扰动带宽全部硬编码并与协议一致。
5. **核验证据**：`scripts/verify_evidence_bundle.py`（校验和 → 哈希链 → manifest → 从原始数据重算）。
6. **环境变量**：`PYTHON` 可覆盖解释器；`scripts/run_all.sh` 不再硬编码本机路径。
7. **行尾**：写文件统一 `newline="\n"`，避免 CRLF 导致哈希漂移（这是开发中真实踩到的坑）。

---

## 7. 研究有效性边界（三层，禁止混用）

| 层级 | 当前状态 | 能支持什么 | 不能支持什么 |
|---|---|---|---|
| **T1 内部一致性** | **15/15 通过** | 产物自洽；statistics 可从原始数据重算；文件未被篡改；episode 可逐位重放 | 不能证明实验设计正确、指标有效 |
| **T2 方法学有效性** | **v2 通过；保留 1 项 FAIL** | ε-扰动确实改变了输入（192/192 每次扰动场景哈希都不同）；指标分母为实测数；候选抽样可复现 | 保留异常：v1 协议内嵌哈希不可核验。且 ε 带宽是人为选择 |
| **T3 外部独立复现** | **不具备** | 无 | 不能声称结论已被独立验证 |

**系统能支持的结论**
- 在 `builtin` + `safe_follow` + 直道 3 车道单前车场景族内，随机搜索发现的失效对
  协议规定的 ε 扰动高度稳健（0.8906，Wilson 下界 0.7910）。
- 同等预算下，mutation 的发现率显著高于 random（0.404 vs 0.040），此结果在两个独立种子集上复现。
- 两种方法的失效稳健性**没有**可检出的差异。

**系统不能支持的结论**
- 任何真实道路交通安全结论。
- "mutation 比 random 更能发现稳定失效"——H2 不支持，且 v1 的相反结论已被撤回。
- 跨仿真器（`builtin` vs `highwayenv`）的定量比较。
- 改变 ε 带宽后的稳定性数值。
- 把哈希链通过、manifest 通过当作"实验为真"。

---

## 8. 残余问题

| 问题 | 原因 | 风险 | 解除条件 |
|---|---|---|---|
| 无外部复现（T3） | 仅单机单作者 | **高**（发表层面） | 由第三方按 README 复现并记录 |
| v1 协议哈希不可核验 | 自指构造 + 值来源不明 | 中（治理层面） | 保留异常；v2 已改用可复现约定 |
| v1 discovery 真实耗时缺失 | `--resume` 覆盖了计时字段 | 低 | 重跑一次不带 resume 的 v1（可选） |
| Gate D 仅部分验证 | 无第三方动力学引擎，CARLA 未接 | 中（限制一切跨仿真器主张） | 接入真实动力学后按协议 v3 重跑 |
| CornerCaseLab / SafeFlipLab 兼容层未实现 | 本轮未排期 | 低 | 按其公开格式实现适配器 |
| DeepSeek 模型身份未确认 | 子智能体自报与派发不一致 | 低（不影响功能，影响归因审计） | 查阅 WorkBuddy 后台路由日志 |
| `highwayenv` 未纳入正式实验 | 摆位近似，跨后端不可比 | 低（已声明） | 实现精确摆位后另立协议 |
| GitHub 未发布 | `gh` CLI 不可用 + 需授权 | — | 用户确认后执行 `docs/RELEASE_CHECKLIST.md` |

---

## 9. 下一阶段建议（只列最有价值的三项）

1. **拿一次真正的外部复现**：请第三方在干净机器上跑 `scripts/verify_evidence_bundle.py`
   与 `scripts/run_all.sh --with-formal`，把结果写入 `docs/` 并更新 T3。这是当前最大的缺口。
2. **扩展场景族后再谈泛化**：加入多前车、变道、切入等交互，重复 v2 的流程；只有跨场景族的稳定性
   才有讨论价值。当前单前车族的高稳定率不应被引用为"系统脆弱"的证据。
3. **完成 Gate D**：安装 CommonRoad（CPU 可行）并实现精确 IR 摆位的适配器，使跨仿真器比较
   从"不可比"变为"在能力交集内可比"。
