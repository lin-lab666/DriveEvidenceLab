# DriveEvidenceLab｜独立方法学审查（research-reviewer，Step-5-Preview）

审查对象：`runs/formal_experiment_v1/`（Gate E v1）与 `docs/PROTOCOL-frozen-v1.md`。
纪律：未改动任何既有文件；自写脚本仅置于系统临时目录；所有数字来自本人实际运行。
注：v2 协议已列出 D-1~D-4（与总指挥 C1~C4 对应）；本报告为独立复验，不引用其结论作为证据。

## 1. 我实际执行的命令与真实输出摘录

环境：`PYTHONPATH=src`，Python = `.../envs/driveevidence/Scripts/python.exe`。

(1) C1 实证（同一场景，seed ∈ {3000,3001,3002,42,0,2147483647}）：
```
{"seed":3000,"category":"collision","steps":5,"traj_sha256":"fbeedc7c59037f4f"}
{"seed":3001,...同上...}  {"seed":42,...}  {"seed":0,...}  {"seed":2147483647,...}
DISTINCT_RESULTS_ACROSS_SEEDS=1   # 1 => seed 对仿真零影响
```
(2) holdout 全量产物统计（脚本遍历 1716 个 cand_*/summary.json）：
```
[random]   candidates=144  all3_identical=144  stable=144  categories={'collision':144}
[mutation] candidates=1572 all3_identical=1572 stable=1572 categories={'collision':1572}
seed_pattern_ok=True（候选 j 得 3000+(j%20),(j+1)%20,(j+2)%20）；confirmed_count 全为 0 或 3
```
(3) 统计量独立重算（对原始 discovery/holdout 产物）：
```
capped_yield random  =0.111111111111  summary=0.111111111111  match=True
capped_yield mutation=0.010178117048  summary=0.010178117048  match=True
mean_diff=0.3486328125 summary=0.3486328125；boot_ci=(0.3010192871,0.3945312500) 与 summary 一致
full_yield 均=1.0；Wilson CI 全部逐位一致
```
(4) 发现阶段完整重放（重新执行 128 次搜索，对比归档报告）：
```
discovery reproduction mismatches: 0/128   # episode 摘要、候选哈希、budget 全部一致
```
(5) 协议哈希（`sha256sum docs/PROTOCOL-frozen-v1.md` 及变体）：
```
实际文件      = 9dcbd0974d500eb9429440c306b84f6ec5fe64dea3a4dcf7d6a23a4046149b82
文件末尾声明  = 247f6721ee26ae76e7e9258e3e43065ea2189fe4d37254ff62b8074ae8e92e29
去末行/末2行/末3行/CRLF 变体：b2b55b37…/2d9fc589…/4d3adce9…/9dcbd097…（无一等于 247f…）
git show 051b592:docs/PROTOCOL-frozen-v1.md | sha256sum = 9dcbd097…（提交时即已不符）
```
(6) 类别分布与截断敏感性：
```
discovery 8192 episodes：random={timeout:3952, collision:144}；mutation={timeout:2516, collision:1572, infeasible:8}
near_miss / off_road / rule_violation 出现次数 = 0；collision 步数 ∈ [2,32]
300 个 TIMEOUT 场景 @max_steps=300：仍全部 TIMEOUT（0 个转为 collision）；其中 3 个 min_gap<1.0m
```

## 2. C1–C4 逐项裁定

- **C1：成立**（措辞需精确化，见 §4）。`builtin.py:131` 创建 `rng` 后全文再无使用；6 个 seed 下轨迹 SHA-256、类别、步数、指标完全一致。1716 个候选的 3 次 holdout 逐位相同（all3_identical=1716/1716），"3 个独立 holdout 种子"实为同一确定性函数的 3 次重复调用；full stable yield=1.0 由确定性先验保证，是同义反复而非实证发现。
- **C2：成立**。全部候选皆稳定时 `stable_failure_yield_protocol_cap = min(16,提名数)/提名数 = 16/提名数`：random 16/144=0.1111，mutation 16/1572=0.0102，与 summary 精确一致。该量只反映提名数量（且系统性惩罚提名多的方法），不反映稳定性；Cohen's h=-0.4776 完全由 144 vs 1572 决定，用于算法比较具有误导性。
- **C3：成立**。实际哈希 9dcbd097…（summary.json 采用值，正确）≠ 声明值 247f6721…；我测试的 4 种自然约定（去末行/末2行/末3行/CRLF）无一匹配，协议未定义任何计算约定；git 显示提交时即不符。"把文件自身哈希写入文件"在数学上要求 SHA-256 不动点，不可实现。
- **C4：成立**。协议 §1 H1 明文限定"**随机搜索**发现的 failure candidates"（PROTOCOL-frozen-v1.md:12）；report.md:63 却同时以 H1 判定 random 与 mutation 两方法，属超出预注册范围的额外检验（虽未据此宣称阳性，但超出了预注册边界）。

## 3. 我额外发现的问题（按严重度排序）

1. **【高】NEAR_MISS 是不可达死代码，失败类别空间实际塌缩为 COLLISION 单一类别**。`builtin.py:225-230` 的 for-else 保证循环正常结束时 `category=TIMEOUT`，故 `if category == FailureCategory.NONE`（builtin.py:235）永假，NEAR_MISS 分支不可达；8192+5148 次运行中 near_miss 出现 0 次即证据。此外 OFF_ROAD（ego heading=0、y 恒定）与 RULE_VIOLATION（safe_follow 加速度上限使 v≤33）结构性不可达。协议 §5 的 4 类失败口径与"保持同类型失效"的表述因此失去意义。
2. **【高】H2 被偷换指标（比 C4 更严重的预注册偏离）**。协议 H2 预注册的是"stable failure yield 差异 + 配对 bootstrap + Cohen's h"；实际执行的是 discovery_yield 差值的配对 bootstrap，报告仍标注"支持 H2"（仅在一句从属说明中承认替换）。预注册的 H2 分析从未按注册形式执行。
3. **【中高】holdout 执行量超冻结预算约 71 倍，且 first-16 选择规则未预注册**。协议 §3"总确认 ≤ 96 seeds"，ledger 实记 5148 次 holdout episode（另有 1716 次 replay 存档，共 6864 次仿真调用）；cap 仅在分析阶段施加。"选前 16 个候选"这一决定结论的规则不见于冻结协议，属分析师自由度，且 first-seen 顺序使 capped 子集仅覆盖最早几个 master seed 的候选（顺序偏差）。
4. **【中高】H1 判定完全由未预注册的 cap 制造**。random capped Wilson 下界 0.0696（<0.1，判"不支持"）vs full-budget 下界 0.974（>0.1，判"支持"）——结论随 cap 翻转；而 full 侧的"支持"又是确定性的同义反复。两种口径下 H1 判定都不含关于鲁棒性的信息。
5. **【中】"独立种子"设计双重落空 + 搜索 RNG 耦合**。holdout 种子跨候选复用（候选 j 与 j+20 共享 3000+(j%20)），叠加 C1 的确定性，复测零信息量；另 mutation 在 round 0（archive 为空）与 random 共用同一 `default_rng(master_seed)` 流，两方法每个 master seed 的首个场景逐位相同（random/mutation 的 cand_0000 哈希均为 d1702e62d7c8…）。协议 §3/§4 自身还有"60 个 vs 96 个"holdout 种子的内部不一致。

## 4. 我不同意总指挥的地方

- C1 的"seed 对仿真结果零影响"应精确为"**episode seed 对仿真零影响**"。master seed（2000–2063）通过场景生成真实影响结果：我完整重放 128 次发现运行 0/128 mismatch，证明流水线确定性可复现；换 master seed 会产生不同场景。因此 mutation 与 random 的 discovery_yield 差异（0.3486，CI [0.3010, 0.3945]，我已复算）是**真实的、种子驱动的发现率差异**，不是赝像——总指挥若把 C1 外推为"v1 全部数字皆无效"则过度。v1 的 discovery_yield 与预算记账仍然有效。
- **max_steps=80 截断 concern：我未能证实**。抽样 300 个 TIMEOUT 场景以 300 步重跑，全部仍为 TIMEOUT，无一转为 collision——没有证据表明截断隐藏了碰撞。3/300 样本 min_gap<1.0m 只说明存在近距离事件，而它们不可见的原因是 §3-1 的死代码，不是视界截断。发现阶段 wall time 0.377s 与碰撞集中于第 2–32 步相符，非异常。

## 5. 对 H1/H2 在当前证据下的独立判断

- **H1（稳定性，预注册仅限 random）**：按注册口径无法有效判定。capped 检验失败（0.0696<0.1）但该指标是 C2 赝像且 cap 未预注册；full 检验通过（0.974>0.1）但是确定性的同义反复（C1）。结论：**H1 未能验证**——v1 证据对"失败在独立种子下是否稳定"不提供任何信息，因为"独立种子"从未真正变化。
- **H2（方法比较）**：按注册形式（stable yield 比较）**不可执行且未执行**（stable yield 无法按 master seed 配对，脚本自述）；报告实际回答的是未注册的 discovery_yield 差异问题。该发现率差异本身真实且可复现（本人复算一致），可作为历史发现引用；但"stable failure yield 存在方法差异"这一预注册命题在 v1 证据下**不成立判定**。
- 总体：v1 唯一站得住的实证结论是"等预算下 mutation 比 random 发现更多碰撞类场景"；一切冠以 stable/H1/H2 的稳定性结论均应标记为无效（与 v2 协议 D-1~D-4 的处置方向一致，此为本审查独立得出的同一结论）。

---
审查人：research-reviewer（Step-5-Preview）｜日期：2026-10-19｜仅复验与独立分析，未修改任何既有文件。
