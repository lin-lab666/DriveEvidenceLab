# 发布检查清单（Release Checklist）

> 用途：在把仓库公开、打 tag、创建 GitHub Release 之前，逐项确认。
> 状态：**未执行**。公开发布需要用户明确授权（见任务书第五节）。

## A. 科学有效性

- [x] 冻结协议存在且有可核验哈希（`docs/PROTOCOL-frozen-v2.md` + `docs/PROTOCOL-v2.freeze.json`）
- [x] v1 的无效稳定性结论已撤回并记录（`docs/DECISIONS.md` D015）
- [x] v2 指标分母 = 实测候选数，不是提名数
- [x] 候选选择预注册且可复现（`selection.json` 与 `rng(4000)` 重抽一致）
- [x] 错误/超时/不可行全部入账，未从分母剔除
- [x] 负结果与不支持假设如实报告（H2 不支持已写进 README 与报告）
- [x] 区分 T1/T2/T3 三层结论（`docs/SCIENTIFIC_AUDIT.zh-CN.md`）
- [x] 后端缺陷修正后重跑，**两次运行并列保留、未择优**（D017：`runs/formal_experiment_v2/` + `runs/formal_experiment_v2p1/`）
- [x] 失败类别口径变化已披露（`near_miss` 由不可达变为 57 次）
- [ ] **外部独立复现** —— 尚未发生；发布时必须显式声明这一点
- [x] 未把仿真结果表述为真实道路验证
- [x] Gate D 口径正确：CommonRoad 仅**部分验证**，文档中一律写 PARTIAL，
      未出现"用 CommonRoad 复现了实验"这类越界表述（`docs/GATE_D.zh-CN.md`）
- [x] 新增后端不夸大能力：`commonroad` 的 `capabilities()` 显式声明
      `independent_dynamics=False`、`third_party_dynamics_engine=False`，且被测试锁定

## B. 代码与测试

- [x] `python -m unittest discover -s tests -p "test_*.py"` 全绿（156 项）
- [x] `pip install -e .` 后 `driveevidence --help` 可用（已在仓库外目录验证）
- [x] **wheel 干净安装验证**：`pip wheel` 产出 `driveevidence-0.2.0-py3-none-any.whl`（35 个条目，
      含 `py.typed` 与全部子包），装入一个**全新 venv**（除 pip 外只有 numpy），
      在仓库外临时目录跑通 sample → run → search → audit → replay → report html，
      replay 类别一致且指标差全为 0.0；同一环境下 Wilson `[0.791, 0.946]`、
      Newcombe 差 `+0.0625 [-0.0365, 0.1668]` 与仓库内结果一致。
- [x] 可选依赖缺失时优雅降级：干净 venv 无 scipy/gymnasium/highway-env/commonroad 时
      `doctor` 逐项报 `NOT INSTALLED (optional)`，核心链路仍可运行
- [x] `doctor` 区分"源码检出"与"已安装包"，不把 site-packages 误标为 project_root
- [x] `scripts/run_all.sh` 可从干净 checkout 跑通
- [x] 关键异常路径有测试（非法场景、缺失文件、篡改账本、空分母）
- [x] 无跳过/删除测试来"凑绿"
- [x] 无 `print` 调试残留于库代码（脚本除外）

## C. 证据与可复现

- [x] `evidence/` 含 v2 完整包与 v1 holdout 明细，附 `SHA256SUMS`
- [x] `scripts/verify_evidence_bundle.py` 在独立临时目录核验通过
- [x] ledger 哈希链、manifest、episodes 重放均 PASS
- [x] 环境版本记录（Python / NumPy / adapter version）在 `summary.json`
- [ ] 在一台**全新机器**上从零复现（当前仅同一台机器，属于 T3 边界）

## D. 文档

- [x] `README.md` / `README.zh-CN.md` 含真实结果与边界声明
- [x] `docs/ARCHITECTURE.md`（架构与契约）
- [x] `docs/API.md`（API 参考）
- [x] `docs/SCIENTIFIC_AUDIT.zh-CN.md`（审计）
- [x] `CHANGELOG.md`（含 0.1.0 结论撤回说明）
- [x] `CONTRIBUTING.md`
- [x] `NOTICE`（第三方许可与免责声明）
- [x] `CITATION.cff`
- [x] `docs/RELATED_WORK.md`（许可证已核实，未核实项已标注）

## E. 许可证与合规

- [x] `LICENSE` = Apache-2.0（完整文本）
- [x] 依赖许可兼容（BSD-3 / MIT）
- [x] 无 vendored 第三方代码
- [x] 仓库历史无个人邮箱（提交身份为 `DriveEvidenceLab Team <team@driveevidencelab.invalid>`，
      全部 18 个提交的 author 与 committer 均一致，已用 `git log --format` 去重核实）
- [ ] 工作树与入库文档中无本机绝对路径 / 文件名 —— **不完全成立，已定位并处置**：
      用 `scripts/privacy_scan.py` 扫描 13 854 个文件，命中 **1 个跟踪文件**
      （`tests/acceptance-round2.md` 第 13、22 行的解释器绝对路径）与 **1 个未跟踪文件**
      （`.workbuddy/memory/MEMORY.md`，已在 `.gitignore` 中）。
      处置方式见 E-1：不改科研仓库，只在公开副本中脱敏。
- [ ] **历史的旧提交 blob 中仍含本机用户名** —— 已确认存在（`git cat-file` 扫描命中多个 blob）。
      这是**已知未清除项**，处置方式见 E-1。

### E-1 处置方案（已决定：独立脱敏副本）

**更正一处先前的不准确表述**：本清单原写"审计报告与 `scripts/audit_scientific_validity.py`
用 `051b5923` 这个冻结提交证明协议未被改动"。实际 grep 结果显示 `051b5923`
**只出现在本文档**，审计脚本并不依赖它——T1 的协议完整性检查用的是正文哈希与文件字节比对。
因此"改写历史会摧毁一条自动化审计链"的说法过强，改写历史的主要代价是**文档引用失效**，
而不是审计失效。

尽管如此，仍然选择**不重写科研仓库历史**，理由与代价如下：

| 方案 | 做法 | 优点 | 代价 |
|---|---|---|---|
| **A（已选）** | 另建脱敏公开副本，科研仓库原样保留 | 本地冻结锚点、全部提交哈希、`runs/` 原始产物完全不动；隐私不外泄 | 公开历史是"整理后的单一提交"，不能当作完整研发史；须显式披露 |
| B | 在原仓库 `filter-repo` 重写全部历史 | 公开历史连续 | 所有提交哈希改变；文档里引用的哈希全部失效；`runs/` 本就不在 git 中，重写后仍无法公开核验原始产物；风险与收益不匹配 |

方案 A 的实现与凭证：

- `scripts/privacy_scan.py` —— 三面扫描（内容 / 路径名 / 历史 blob + 提交元数据），可对任意目录运行。
- `scripts/build_public_release.py` —— 从 `git ls-files` 构建副本，仅把家目录段替换为
  `<LOCAL_HOME>`，输出 `PUBLIC_MANIFEST.json`（逐文件 SHA-256）与 `PUBLIC_RELEASE.md`
  （逐文件脱敏计数 + 冻结协议哈希 + 证据束校验和 + "整理后历史"披露）。
- 公开副本的核验锚点**不依赖 git**：协议正文哈希 `205ecf9f…` 与 `evidence/SHA256SUMS`
  在副本中原样保留，第三方可独立核验。

## F. 发布动作（需用户授权）

**已在本地完成（未发布）**

- [x] 公开副本构建脚本与隐私扫描脚本就位，副本可重复构建（`scripts/build_public_release.py`）
- [x] 版本标签方案已定：`v0.2.0-research-preview`（不是 `v0.2.0` 正式版，避免暗示已稳定）
- [x] Release notes 草稿：`docs/RELEASE_NOTES-v0.2.0-research-preview.md`
- [x] 公开副本 `PUBLIC_RELEASE.md` 含整理后历史披露、冻结哈希、T3 与 Gate D 声明

**必须由用户确认后才能做**

- [ ] 把 `pyproject.toml` 的 `Homepage` / `Repository` 占位符替换为真实仓库地址
- [ ] 创建 GitHub 仓库并 push 公开副本（**需用户确认**）
- [ ] 在公开仓库创建 tag 与 Release，附 `evidence/gateE-v2p1-full.tar.gz` 与 `SHA256SUMS`
- [ ] Release notes 必须包含：v1 结论撤回、v2/v2.1 协议偏差、T3 未复现声明、
      Gate D 仅 PARTIAL、适用范围限制（可直接用草稿）

## G. 发布后

- [ ] 用另一台机器按 README 走一遍安装 → 运行 → 核验
- [ ] 收集外部复现反馈，写入 `docs/` 并更新 T3 状态
