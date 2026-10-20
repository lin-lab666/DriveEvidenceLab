# DriveEvidenceLab｜技术与研究规格（工程架构草案）

## 目标定义
构建一个有证据链的自动驾驶闭环测试框架，支持“场景提案→真实仿真→初步发现→约束化反事实→独立重测→可迁移性检查→证据包→统计报告”，服务于研究和算法调试，不用于实际道路车辆控制。

## 新研究问题（必须在文献调查后缩窄成 1–2 个核心 hypothesis）
1. 已发现的 failure candidates 中，有多大比例能在独立 holdout/重复运行中保持相同类型的失败？
2. 不同验证策略能否在公平预算下提高**可审计的稳定 failure yield**，而非仅提高一次碰撞数？
3. 对可比较的 scenario/车辆策略子集，跨仿真器或跨 planner 的迁移率及不确定性如何？记录不兼容和不可比较例子，**不得把一致性解释为现实道路外推**。
4. 引入 minimal-counterfactual / constrained scenario reduction 后，能否在保留失败的前提下降低场景复杂度并提升解释性？

## 避免重复研究
Scenic（抽象场景生成）、CARLA ScenarioRunner（场景执行）、SafeBench（多策略安全测试）、ScenicRules（多目标规则基准）、MultiSim（多仿真器测试）都已提供强相关能力。差异化不应是“我也支持这些”，而是“不可变的证据链、可审计失败复现、分母和消耗严格记录、跨环境不兼容也可解释”。提交 `docs/RELATED_WORK.md` 严格比较其实现、实验与许可证。

## 逻辑架构
```
Scenario DSL / Canonical IR / ODD constraints
                  |
       Synthesis + Mutation + Search
                  |
     Feasibility/Semantics Validator
                  |
       Simulation Adapter interface
       |          |             |
   HighwayEnv   CommonRoad      CARLA
   (CPU base)   (if feasible)   (optional heavy)
                  |
       Controller / Policy adapters
                  |
         Frozen execution ledger
                  |
 Discovery -> confirmation -> independent holdout audit
                  |
      replay+artifact manifest+sha256
                  |
      visual report / CLI / optional Web
```

## 代码结构（建议，可由架构师修改并留 ADR）
- `src/driveevidence/scenario/`：canonical scene schema、units、frame of reference、ODD constraints、applicability and versioned encoding。
- `src/driveevidence/sim/`：SimulatorAdapter Protocol、HighwayEnv、CommonRoad、CARLA adapter、capability negotiation，使用真实 API。
- `src/driveevidence/planners/`：在各仿真器中明确限定的 rule-based baselines，以及可接入外部闭环 planner 的 contract。
- `src/driveevidence/search/`：Random / evolutionary / model-based or adaptive methods；共享预算与相同候选评估规则。
- `src/driveevidence/evidence/`：append-only execution ledger、episode storage、sha256 manifest、resume、replay、diagnostics。
- `src/driveevidence/stats/`：paired uncertainty、Wilson/bootstraps where appropriate、missingness and multiple comparison handling。
- `src/driveevidence/report/`：中英报告，图表关联真实 evidence IDs。
- `tests/`、`examples/`、`configs/`、`docs/`、`scripts/`、`reports/`、`runs/`。

## 科学性与跨仿真器的关键陷阱
- Canonical IR 只描述**两个适配器都能表达的交集**；同名参数不代表相同物理含义，必须标明“可比较/近似/不可比较”。
- 场景合法性检查应独立于安全判据，例如轨迹/速度/加速度/碰撞几何和 spawn 可行性。
- 量纲一致性（m、s、m/s、rad）、坐标系约定、地图与道路语义必须有版本标注。
- 失败类别：collision、off-road、speed/rule violation、near miss、infeasible、simulator error、timeout、unknown。仅适配器明确支持的类别可用于统计。
- 控制器冻结：同一比较组不得在方法间暗改 policy 或随机化机制。
- 计费：每个 launch/重试、失败、崩溃记录；按照实际使用的研究成本口径预算闭合。
- 执行前写明必要性及 proxy 属性；TTC 或碰撞不是现实安全证明。区分 failure severity、failure incidence、scenario validity、planner performance。
- 禁止以漂亮视频代替可复现的对照实验；可视化只是证据展示。
- 禁止仅以“不同 simulator 都 collision”推断同一根因。

## 开源可用性
CPU 端到端 demo 优先不需要 Docker/GPU；重型 CARLA 作为 extra，不拖累 CI quickstart。提供平台兼容矩阵和“verified on”记录。发布 API 示例、示例 scenario 和最少一次真实运行日志，假数据明确标注。优先 Apache-2.0，但需审计所有引入代码与二进制许可；不兼容时寻求替代或调整许可方案。

## 延展性
未来可引入 Scenic/OpenSCENARIO 2.0 **经测试支持的特定语义子集**；不要声称完全符合标准。可另做可选远程 Web UI，但 CLI/数据格式先稳定。
