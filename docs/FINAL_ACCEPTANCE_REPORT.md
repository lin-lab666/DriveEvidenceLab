# DriveEvidenceLab 最终交付验收报告

> 日期：2026-10-20 | 验收人：总指挥（独立复核） | 版本：driveevidence 0.2.0（Gate E v2.1）
> 性质：发布前最后一轮独立验收，不扩充功能，仅核验 + 修正一致性问题。

---

## 0. 总判定

| 维度 | 判定 |
|---|---|
| 发行候选（SDK + CLI） | **PASS** |
| 证据链完整性（T1） | **PASS**（15/15） |
| 方法学有效性（T2） | **PASS**（保留 1 项 FAIL：v1 协议自指哈希） |
| 外部独立复现（T3） | **不具备**（诚实标注，非阻塞项） |
| Gate D（第二仿真系统） | **PARTIAL**（无第三方动力学） |
| CARLA | **NOT VERIFIED** |
| 公开发布 | **BLOCKED**（唯一硬性阻断：`pyproject.toml` 的 PLACEHOLDER URL，需真实 GitHub 地址） |

---

## 1. D019-C "保守"表述核对与修正（发现并修复真实一致性问题）

### 1.1 核对结论

`docs/DECISIONS.md` 的 D019-C 条目（第 146–148 行）原文写"合并估计 +0.3669 是**保守的**"，与
`docs/LIMITATIONS.md` §4（第 81 行）的现行权威解释相矛盾。LIMITATIONS.md 的表述更严谨：

> 重合使配对差值向 0 收缩是**机制性解释**，不是已证明的偏差方向；分层（事后重组）不构成
> 因果识别，只支持"方向稳健"，**不支持**"合并估计必然保守"。

另发现 `docs/SCIENTIFIC_AUDIT.zh-CN.md` 两处残留过强表述（§10.4 "偏保守"、§12 "使 H3 更保守"）。

### 1.2 修正动作（保留原始决策历史）

| 文件 | 动作 |
|---|---|
| `docs/DECISIONS.md` | D019-C 条目**原文保留不删**，其后**追加**"D019-C 后续修正（2026-10-20）"块，指向 LIMITATIONS.md 现行口径 |
| `docs/SCIENTIFIC_AUDIT.zh-CN.md` | §10.4 与 §12 两处"保守"表述收窄为"机制性解释 + 方向稳健"，与 LIMITATIONS.md 对齐 |
| `scripts/audit_seed_coupling.py` | docstring + `direction` 字段从 "pooled estimate is conservative" 改为 "sign of H3 is robust; does NOT establish conservatism" |
| `runs/.../seed_coupling.json`（证据束内） | **保持原始字节不变**——证据束是冻结锚点，`build_evidence_bundle.py --check` 仍 MATCH |

### 1.3 纪律说明

修正只落在**活代码**（脚本）与**文档**（DECISIONS/SCIENTIFIC_AUDIT/LIMITATIONS 已先行对齐），
**不改写**已归档的证据束。这正符合"保留原始决策历史 + 明确记录后续修正"的要求。未来重跑
`audit_seed_coupling.py` 会产出新措辞，但已归档产物保留当时的记录。

**验证命令**：`python scripts/build_evidence_bundle.py --check` → `MATCH`（证据束未动）。

---

## 2. 公开副本 115 文件 vs 隐私扫描 114 文件的统计差异

### 2.1 数字来源核对（无盲区）

| 数字 | 来源 | 含义 |
|---|---|---|
| **115** | `git ls-files \| wc -l` | 公开副本的**源文件数**（从科研仓库 tracked 文件拷贝） |
| **117** | 公开副本落盘 `find -type f` | 115 + 构建脚本自生成的 `PUBLIC_MANIFEST.json` + `PUBLIC_RELEASE.md` |
| **114** | `privacy_scan.py` 的 `scanned_files` | 117 − 2（两个 `.tar.gz` 二进制，被**内容扫描**跳过）− 1（`privacy_scan.py` 自身，`SELF_PATH` 跳过） |

### 2.2 差异逐项解释（确认无扫描盲区）

1. **两个证据束 tar.gz**（`gateE-v2p1-full.tar.gz`、`gateE-v1-holdout-summaries.tar.gz`）：
   是二进制归档，被内容扫描按 `BINARY_SUFFIXES` 跳过；**但**由 `scan_archives()` 单独扫描
   （成员名 + 文本成员内容），不存在盲区。
2. **`scripts/privacy_scan.py` 自身**：扫描器必然包含它要检测的模式，扫描只会产生自我匹配，
   故按 `SELF_PATH` 跳过——这是设计使然，非盲区。

### 2.3 扫描结果

三面扫描（文件内容 / 路径名 / git 历史 blob+元数据）+ 归档扫描 **0 发现，CLEAN**。

**验证命令**：
```
python scripts/build_public_release.py --out <tmp>/public --force   # files: 115, redacted: 0
python scripts/privacy_scan.py --root <tmp>/public --git             # files scanned: 114, findings: 0, CLEAN
```

---

## 3. 干净环境验证（从最终源码重新构建）

### 3.1 构建

```
python -m build --outdir <tmp>/dist .
# 产物：driveevidence-0.2.0-py3-none-any.whl + driveevidence-0.2.0.tar.gz
```
> 有 license classifier 弃用警告（非阻断，建议后续改 SPDX 表达式，见 §7）。

### 3.2 干净 venv 安装与版本

```
python -m venv <tmp>/cleanvenv
<cleanvenv>/python -m pip install driveevidence-0.2.0-py3-none-any.whl
<cleanvenv>/python -c "import driveevidence; print(driveevidence.__version__)"  # 0.2.0 ✓
```
版本正确读自 `importlib.metadata`（单一来源 pyproject.toml）。

### 3.3 SDK 示例

```
<cleanvenv>/python examples/minimal_sdk_example.py
# scenario: tailgate_risk (ir/v1); adapters: builtin/commonroad/highwayenv
# episode: steps=15 category=collision; search: 0 failures/32; Wilson CI [0.0000, 0.1072] ✓
```

### 3.4 CLI 7 子命令冒烟

`doctor` / `sample` / `run` / `search` / `audit` / `replay` / `report` 全部端到端通过。
`replay` 逐位一致（metric diffs 全 0，category match）。

### 3.5 Quick Start

Quickstart 流程（sample → run → audit → replay → report）在干净 venv 全通过，`--seed 2101`
（非退化种子）验证 OK。

---

## 4. 版本 / 依赖 / 证据哈希 / 隐私扫描 / 发布门验证

| 项 | 命令 | 结果 | 证据位置 |
|---|---|---|---|
| 版本 | `import driveevidence; __version__` | 0.2.0 ✓ | pyproject.toml + importlib.metadata |
| 依赖 | `pip install <wheel>` | 核心仅 numpy；sim/stats/commonroad 可选 | pyproject.toml optional-dependencies |
| 证据哈希 | `python scripts/verify_evidence_bundle.py` | T1 全 PASS | 见下方明细 |
| 证据确定性 | `python scripts/build_evidence_bundle.py --check` | MATCH | 打包确定性可复现 |
| 隐私扫描 | `python scripts/privacy_scan.py --root <public> --git` | 0 发现 CLEAN | §2.3 |
| 发布门（commit） | `python scripts/build_public_release.py --out X --commit` | exit **1**（拒绝 PLACEHOLDER） | §4.1 |
| 发布门（预览） | 同上无 `--commit` | exit **0**（允许预览） | §4.1 |

### 4.1 证据核验明细（T1 全 PASS）

```
[T1] checksums: PASS
[T1] ledger hash chain: PASS (260 entries, first_bad_seq=None)
[T1] manifest: PASS (773 files, 0 mismatched)
[T1] statistics recomputation: PASS
[T1] v1 degeneracy recount: 1716 identical / 0 varying  [PASS]

Recomputed (raw artifacts only):
  random   launched=4096 discovery_yield=0.0444 tested=64 stable=57 stable_yield=0.8906 [0.7910, 0.9460]
  mutation launched=4096 discovery_yield=0.4114 tested=64 stable=61 stable_yield=0.9531 [0.8710, 0.9839]
  H1: supported=True   H2: supported=False   H3: supported=True
```

### 4.2 发布门闭环验证

```
# 存在 PLACEHOLDER 时 --commit 拒绝（exit 1）
error: refusing to commit a public copy with outstanding blockers:
  - `pyproject.toml` still contains a `PLACEHOLDER` repository URL

# 无 --commit 的预览构建允许（exit 0，供 CI 隐私扫描）
```

---

## 5. 多智能体审查记录复查（区分独立审查 vs 总控自查）

### 5.1 真正的子智能体独立审查（有独立落盘 + 时间戳证据）

| 审查 | 执行者 | 证据 | 产出 |
|---|---|---|---|
| 方法学独立复验 | Step-5-Preview（research-reviewer） | `docs/review/independent-method-review-v1.md` | C1–C4 独立复验 + 5 项额外发现 + 2 处对总指挥的纠正 |
| 跨模型协作派发 | 12 次真实派发 | `docs/collab-test-report.md` + `logs/round1-3/*.log` | 真实并行（时间戳重叠）、真实制衡（v0.1 被打回 2.17/3 → v0.2 复审 3.00/3） |
| 本轮最终 Red Team | Explore 子智能体 | PROGRESS.md / D025 | 发现 API.md v2.0 残留 + 发布门装饰性 2 个真实缺陷 |

### 5.2 总控自查（非子智能体审查，已如实区分）

- `scripts/audit_independent_recompute.py`（D023）：总指挥**不导入项目统计模块**独立实现 Wilson/Newcombe/Fisher/bootstrap 重算——属"总控独立复算"，文档已明确标注，**未**冒称子智能体审查。
- `scripts/audit_seed_coupling.py`（D019-C）：总指挥独立实测 RNG 耦合，同样标注为总控行为。

### 5.3 结论

真实子智能体独立审查（Step-5-Preview 方法学复验、Explore Red Team）与总控自查（独立复算脚本）在
文档中有清晰区分，无冒充。所有 git 提交署名 `DriveEvidenceLab Team`，未冒充子智能体身份。

---

## 6. 测试与构建结果汇总

| 项 | 结果 |
|---|---|
| 完整测试套件 | **144 项全通过**（`python -m unittest discover`，46s，OK；验收时点快照，当前套件已扩至 156 项） |
| 端到端 `run_all.sh` | **exit 0**（含 CommonRoad 交叉核对 PASS、证据 --check MATCH、种子耦合审计） |
| CommonRoad 交叉核对（Gate D） | exchange 0 失败、轨迹逐位一致、类别 80/80 一致 → PASS（但仍 PARTIAL，无第三方动力学） |
| wheel 干净安装 | version=0.2.0 ✓ |

---

## 7. 发行候选 SHA-256（核验锚点）

```
00f45717d02778ed91dfb84a4fedae978c84a3d8f71f48a6ff3074540d2dbd98  driveevidence-0.2.0-py3-none-any.whl
2291e6c1a046436850c9be6afbc99c80765de95557b6ad2526919c7622417f55  driveevidence-0.2.0.tar.gz
23bd6570991cb27b83acd6c999c5ca803fd039223e8a496ce549622537dfc9ea  gateE-v2p1-full.tar.gz
a5863f8b259a2989a35fd4af32bfcb55cf333052d43fc1f92a43d0e3b58e36d6  gateE-v1-holdout-summaries.tar.gz
8832e9de4aeef174b6bbfbbd0e442484b96ae7dfe842c693243d147b56b7aa9e  SHA256SUMS
```

---

## 8. 剩余问题清单（按性质分类）

### 8.1 需用户授权/外部动作（BLOCKED，不自行动手）

1. **真实 GitHub 仓库地址**（唯一硬性阻断）：填 `pyproject.toml` 的 `[project.urls] Homepage`
   的 PLACEHOLDER → 建仓库 → push 公开副本 → 打 tag `v0.2.0-research-preview` → 创建 Release。
2. 授权后可选：PyPI 发布（本报告未做，需单独授权）。

### 8.2 科研后续（诚实标注，非阻塞）

| 项 | 状态 |
|---|---|
| T3 外部独立复现 | 不具备（同作者/代码/机器） |
| v3 第三方动力学 | 未完成（SUMO 下载两次中断），草案见 PROTOCOL-v3-draft.md |
| CARLA | NOT VERIFIED（无 GPU） |
| Gate D 升级为 PASS 的前提 | 接第三方动力学 + 按协议 v3 重跑（当前未达成） |

### 8.3 小问题（非阻塞，记录待修）

1. `pyproject.toml` 的 `license = { text = "Apache-2.0" }` + license classifier 触发弃用警告，
   建议改 SPDX 表达式 `license = "Apache-2.0"`。
2. `d2bf3b4` 提交信息拼写 "privace"（应为 "privacy"，历史记录不改，仅备忘）。

---

## 9. 完成 / 部分 / 未完成统计

| 状态 | 项目 |
|---|---|
| **完成（PASS）** | SDK 包（公共 API/CLI/SDK 示例）、144 测试、干净 venv 验证、证据链 T1 15/15、隐私扫描 CLEAN、发布门闭环、D019-C 一致性修正、多智能体审查记录区分 |
| **部分（PARTIAL）** | Gate D（CommonRoad 判定层已验证，第三方动力学未接） |
| **未完成（BLOCKED/不具备）** | 公开发布（缺真实 URL）、T3 外部复现、v3 第三方动力学、CARLA |
