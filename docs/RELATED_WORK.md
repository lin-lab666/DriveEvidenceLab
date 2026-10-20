# DriveEvidenceLab — 相关工作与差异化边界

> 最后核实日期：2026-10-19。所有许可证信息均来自对应公开仓库/文档；若日后变更，以官方源为准。

## 1. 相关工作表

| 项目/论文 | 定位 | 许可证（公开来源） | 与本项目的功能对比 | 与本项目的差异边界 |
|---|---|---|---|---|
| **Scenic** | 面向网络物理系统的概率式场景描述语言；可生成静态/动态场景并对接多种仿真器 | BSD-3-Clause（官方文档 scenic-lang.readthedocs.io） | 擅长抽象、可解释的场景建模与采样 | Scenic 本身不内置“失败复现审计链”和“按 episode 的预算/失败分母账本”；DriveEvidenceLab 聚焦证据包、sha256 manifest 与独立 holdout 复现 |
| **CARLA ScenarioRunner** | CARLA 的交通场景定义与执行引擎，支持 Python 接口与 OpenSCENARIO | MIT（GitHub: carla-simulator/scenario_runner） | 提供真实的 OpenSCENARIO/CARLA 场景执行能力 | 本项目的差异在于：跨后端 Canonical IR、证据链哈希、失败 candidate 的 holdout 复现、明确记录不可比较语义；ScenarioRunner 是单一后端执行器 |
| **SafeBench** | 基于 CARLA 的自动驾驶安全基准平台，集成 NHTSA 场景与 DRL 测试代理 | MIT（GitHub: trust-ai/SafeBench） | 提供大规模安全场景基准与策略排行榜 | SafeBench 侧重**统一排行榜**，本项目侧重**可审计的单个发现及其复现率**；不把候选数直接当根因 |
| **ScenicRules** | 基于 Scenic 与 Rulebook 的多目标自动驾驶基准 | BSD-3-Clause（GitHub: BerkeleyLearnVerify/ScenicRules） | 多目标优先级规范与场景评估 | 本项目不引入 Rulebook 优先级，而是记录失败 category、置信区间与跨环境不一致性 |
| **CommonRoad / commonroad-io** | 可组合的道路运动规划基准与场景格式 | BSD-3-Clause（GitHub: CommonRoad/commonroad-io） | 提供结构化场景/地图/车辆模型与复现 ID | 本项目当前仅实现 straight-road IR v1，CommonRoad 的曲线/车道级语义不在支持范围内；预留适配接口，待验证 |
| **MultiSim** | 多仿真器集成搜索，优先发现“跨仿真器一致”的失败场景 | EMSE 2026 / arXiv:2503.08936 | 与本项目同样关注跨仿真器一致性与 simulator-agnostic failure | 本项目把“不一致性”本身作为必须记录的审计证据，而非仅优先一致样本；同时要求每 episode 的预算/失败/重试全入账 |

## 2. 差异化总结

DriveEvidenceLab 的边界不是“比其他工具更全”，而是在以下轴向上做**透明、可审计的研究支持**：

1. **不可变的证据包**：每个 run 生成 ledger（哈希链）+ episode 存储 + manifest（SHA-256），支持篡改检测与独立 replay。
2. **公平预算与完整分母**：搜索/确认/审计三阶段分离；launched/completed/failed/cancelled/infeasible 全部入账；重试计入消耗。
3. **跨仿真器不可比性文档化**：Canonical IR 只表达各适配器交集；同名参数若物理语义不同，必须在 `capabilities`/`raw` 中声明，禁止把“都碰撞”解释为同一根因。
4. **统计有效性**：预注册假设、Wilson CI、配对 bootstrap、多重比较校正；负结果与否定结论同样记录。
5. **不宣称真实道路安全**：仅限仿真内策略表现；任何真实道路外推必须明确标记为**未验证/Unsupported**。

## 3. 许可与引用说明

- 本项目采用 **Apache-2.0** 许可证（见 `LICENSE`）。
- 不复制上述项目的代码或私有数据，仅借鉴其公开 API、研究纪律与许可证公开信息。
- 若未来引入 Scenic/CommonRoad 等第三方运行时依赖，将在 `THIRD_PARTY_NOTICES.md` 中列出并审计兼容性。
