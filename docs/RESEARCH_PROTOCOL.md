# DriveEvidenceLab｜预注册实验协议模板

> 此文件初始为研究协议 TEMPLATE，不意味着任何实验已经执行或得到正结果。负责统计的 Agent 和质疑审稿 Agent 必须在正式数据解锁前签核。

## 1. 核心问题与可证伪假设
- 主要研究问题：____
- Null hypothesis 和 alternative：____
- 主要结果指标：____（定义、单位、取值范围、每个 seed/method 的聚合规则）
- 负结果如何解释：____
- 适用范围与不适用范围：____

## 2. 实验对象和版本冻结
- simulator(s) + EXACT VERSION + compatibility matrix：____
- ego controller/planner + frozen config：____
- scenario family/ODD/地图/vehicle models：____
- canonical scenario IR version：____
- platform and dependencies locked：____
- execution seed derivation：____（稳定 SHA-256 派生，不使用 Python hash）

## 3. 比较方法与公平预算
- Baseline 1 (e.g. Random)：____
- Method 2：____
- Method 3（若有）：____
- 每 method/master seed 的总 episode/cost cap：____
- 搜索/确认/独立 audit 分账：____
- 重试、超时、失败如何计费：____
- 方法间可见数据是否对等：____
- 事前选择的非预期偏差和控制方法：____

## 4. 数据切分与冻结
- 开发/调参 seed set：____
- 发现阶段 seed set：____
- 独立确认/holdout set：____
- 正式锁定 formal seeds：____
- 防数据泄漏检查：____
- 搜索候选提名如何冻结：____
- 冻结人/时间/协议哈希：____

## 5. 预设评估和异常口径
- 场景有效性约束（含不支持条件）：____
- collision/near-miss/rule-violation/infeasible/unknown 定义：____
- planned/effective/launched/failed/cancelled counters：____
- incomplete audit candidate 如何表示：____
- 不确定性与比较（paired bootstrap, CI 等）：____
- 多重比较：____
- effect sizes and raw distributions：____
- Stop conditions（resource/safety/time）：____

## 6. 迁移性检验
- Transfer preconditions：____
- 可比较 IR 子集：____
- 不能迁移的 scenario 记录：____
- Cross-sim/planner metrics and uncertainty：____
- Domain mismatch 的解释边界：____

## 7. 不允许的推断
- 不能从仿真 failure rate 推出真实道路事故概率。
- 不能把候选数量直接当独立根因数。
- 没有独立 holdout 就不能写“已证实稳定”。
- 不能根据正式结果调参后仍把它作为同一个预注册实验。
- 一个仿真器的性能不能推断真实车载系统安全。

## 8. 审核印记
- 协议已冻结：YES/NO
- 独立 QA review：PASS/FAIL
- 所有正式实验事前运行授权：YES/NO
- Run manifest digest：____
