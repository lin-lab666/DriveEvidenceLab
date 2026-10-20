# 贡献指南（Contributing）

感谢你愿意参与 DriveEvidenceLab。这是一个**科研工具**，所以除了"代码能跑"，我们同样在意"结论站得住"。

## 1. 环境搭建

```bash
git clone <your-fork>
cd DriveEvidenceLab
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[dev]"                                 # 核心 + 测试
pip install -e ".[sim]"                                 # 可选：highway-env 集成测试
```

验证：

```bash
python -m unittest discover -s tests -p "test_*.py"
./scripts/run_all.sh
```

## 2. 提交前必须满足

1. **全部测试通过**。不接受"只在我机器上过"。
2. **不降低断言**。为了变绿而删除测试、放宽容差、跳过用例的 PR 会被直接拒绝。
3. **新增行为必须有测试**，包括：
   - 正常路径；
   - 边界（`n=0`、空列表、退化比例）；
   - 异常路径（非法输入、缺失文件、损坏证据）。
4. **不伪造任何运行结果**。PR 描述里的数字必须能被复现命令重现。
5. **统计函数改动必须给出已知值校验**（手工可算的数值 + `assertAlmostEqual`）。

## 3. 研究诚信规则（硬约束）

这些规则不是风格问题，违反会导致 PR 被拒：

| 规则 | 说明 |
|---|---|
| 区分仿真与真实 | `builtin`/`highway-env` 的结果**不得**表述为真实道路验证 |
| 区分失效类别 | `TIMEOUT`/`INFEASIBLE`/`SIMULATOR_ERROR` 不计入 failure，但必须入账 |
| 区分三层结论 | 内部一致性（T1）≠ 方法学有效性（T2）≠ 外部复现（T3） |
| 哈希链不等于科学有效 | 不要把 `manifest` 通过写成"实验已验证" |
| 协议不可回改 | 冻结协议只能新增 v2/v3，不得据结果修改 v1 |
| 报告负结果 | 搜索没发现失败、假设不成立，都要写出来 |

## 4. 代码风格

- Python ≥ 3.10，`from __future__ import annotations`。
- 公共函数必须有类型注解与 docstring；统计函数必须在 docstring 里注明方法来源（如 Wilson 1927 / Newcombe 1998）。
- 核心库只依赖标准库 + NumPy。引入新依赖需要说明理由，并放进相应的 optional extra。
- 文件路径用 `pathlib`；写文件显式 `newline="\n"`，避免跨平台哈希漂移。

## 5. 新增仿真后端

必须实现 `SimulatorAdapter` 并：

1. `@register_adapter` 注册；
2. `capabilities()` **如实**声明支持项，不支持写 `False`；
3. 非法场景返回 `INFEASIBLE` 而非抛异常；
4. `raw` 里记录实际生效的 `dt`/`max_steps`（重放依赖它）；
5. 加一个集成测试，真实跑 2 个 episode 并断言同 seed 可复现；
6. 在 `docs/ARCHITECTURE.md` §9 与 README 的能力表中登记，并写明局限。

## 6. 修改统计方法

1. 先在我们的 `docs/PROTOCOL-frozen-v2.md`（或新协议）里写清楚**为什么**改；
2. 若改动影响已发布的实验结论，必须**新建协议版本**并重跑，不得覆盖旧结果；
3. 同时更新 `scripts/audit_scientific_validity.py` 的重算逻辑，保证审计仍能独立复现。

## 7. 提交信息

遵循 Conventional Commits：

```
feat: add CommonRoad adapter skeleton
fix: restore max_steps when replaying archived episodes
docs: clarify that hash-chain integrity is not scientific validity
test: cover zero-denominator Wilson interval
```

破坏性变更用 `feat!:` / `fix!:` 并在正文说明影响。

## 8. 提交身份与隐私

- 不要提交真实姓名、邮箱、机构、绝对路径或任何凭据。
- 仓库历史使用 `DriveEvidenceLab Team <team@driveevidencelab.invalid>`。
- 运行产物 `runs/` 已被 `.gitignore` 排除；需要分享证据时用 `evidence/` 里的压缩束。

## 9. 报告问题

请附上：

1. 复现命令（完整、可直接粘贴）；
2. `driveevidence doctor` 输出；
3. 期望行为 vs 实际行为；
4. 若是数值问题，附 `summary.json` 相关片段。

请不要附带真实道路数据或任何个人信息。
