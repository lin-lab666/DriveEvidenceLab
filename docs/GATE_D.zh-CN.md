# Gate D — 第二仿真系统：真实推进记录

> 状态：**PARTIAL（部分验证）**。**不是** PASS，也**不是**原来的 NOT VERIFIED。
> 记录时间：2026-10-19　环境：Windows / Python 3.13.14 / `commonroad-io 2026.1`

---

## 1. 为什么不能给 PASS

Gate D 的原始要求是「至少一个真实可运行的仿真后端 + CARLA/CommonRoad 适配器接口」。
本轮做到了后者，**没有**做到前者（第二个**动力学仿真器**）。区别很重要：

| 能力 | 是否完成 | 说明 |
|---|---|---|
| 场景与 CommonRoad 的双向交换 | **完成** | IR → `commonroad.scenario.Scenario` → XML → 读回，字段逐一比对 |
| 用 CommonRoad 官方校验器校验场景 | **完成** | `CommonRoadFileWriter(..., check_validity=True)`，由其自身判定合法性 |
| 用 CommonRoad 几何做失效判定 | **完成** | 碰撞用 `RectObstacleShape` 占位 + shapely 相交；越界用车辙多边形是否落在 lanelet 并集内 |
| 两种判定实现的一致性交叉核对 | **完成** | 80 个真实候选，类别一致率 80/80 = 100% |
| **独立的第三方动力学仿真** | **未完成** | 没有接入任何第三方动力学引擎；rollout 仍是本项目的运动学循环 |

因此正确表述是：**「CommonRoad 适配器与判定语义已用真实 `commonroad-io` 库验证；第二动力学仿真后端仍未接入」**。
任何把它说成"用 CommonRoad 复现了实验"的说法都是错的。

---

## 2. 实际做了什么

### 2.1 新增后端 `commonroad`

`src/driveevidence/sim/commonroad_adapter.py`，注册名 `commonroad`。
`capabilities()` **显式**声明了它不是什么，防止被误用：

```python
{
  "collision": True, "off_road": True, "rule_violation": False,
  "near_miss": True, "deterministic_replay": True,
  "commonroad_geometry": True,             # 判定层来自 CommonRoad
  "commonroad_scenario_exchange": True,    # 场景交换经过 CommonRoad XML
  "independent_dynamics": False,           # 动力学与 builtin 相同
  "third_party_dynamics_engine": False,    # 没有接第三方仿真器
}
```

动力学部分与 `builtin` **逐行同构**（ego 跟规划器、他车匀速），因此：

> 两个后端在同一 scenario/seed/config 下产生**完全相同**的轨迹。
> 于是两者类别不一致时，唯一可能的来源是**判定层**差异，而非动力学差异。

这一点被显式测试固定（`test_trajectory_matches_builtin`，容差 1e-9），
也是本验证有意义的前提——否则"类别一致"可能只是"两边都没跑对"。

### 2.2 判定层如何换成 CommonRoad

| 判据 | builtin（原实现） | commonroad（新后端） |
|---|---|---|
| 碰撞 | 自写 OBB 分离轴相交 | `RectObstacleShape.compute_occupancy_for_state(...).shapely_object.intersects(...)` |
| 越界 | `ego.y ± width/2` 是否超出 `[0, lanes*lane_width]` | ego 车辙多边形是否 `within` 所有 lanelet 多边形的并集 |
| 超速 | 与限速 + 容差比较 | 同（CommonRoad 侧未额外建模） |

### 2.3 交叉核对结果（`scripts/verify_commonroad_interop.py`）

数据来源：`runs/formal_experiment_v2p1` 的**真实候选**，每方法取前 40 个去重候选（共 80）。
配置统一 `max_steps=80`、`safe_follow`、`seed=0`。

```
commonroad-io     : 2026.1
builtin version   : builtin/1.1
commonroad adapter: commonroad-io/2026.1+kinematics/1.0

exchange failures     : 0 / 80
trajectory mismatches : 0 / 80
category agreement    : 80 / 80  (100.0%)

agreement matrix (builtin -> commonroad):
  collision      -> collision         77
  near_miss      -> near_miss          3
```

产物：`runs/formal_experiment_v2p1/commonroad_interop.json`（含全部逐条明细与不一致清单，本次为空）。

**这说明了什么**：至少在这 80 个真实失效场景上，"碰撞"这个标签不依赖于本项目自写的 OBB 实现——
换成 CommonRoad 的官方几何后结论不变。这排除了"判定层是自己写错才导致的高发现率"这一类怀疑。

**这不说明什么**：不说明结果在**另一个动力学模型**下成立。车辆动力学换成真实模型后，
轨迹会变，失效是否复现是**未验证**的。

---

## 3. 过程中发现并修正的问题

### D020｜CommonRoad XML 默认精度导致 71/80 假失败
首次运行 `exchange failures = 71/80`。排查发现不是映射错误：CommonRoad 的 XML writer
默认 `decimal_precision=4`，把 `v=31.15544248...` 写成 `31.1554`，与本项目 1e-6 的比对容差冲突
（实际差值 4.2e-5）。改为 `decimal_precision=8` 后降为 0/80。

**没有**通过放宽容差来"让它过"：提高的是序列化精度，比对容差保持 1e-6。

### D021｜读回后障碍物顺序不保证
最初按 `obstacles[0]` 取 ego，在双车场景（ego + 前车）下取到了前车，导致速度比对全部失败。
改为按写入时分配的 `obstacle_id == 1` 匹配。这是真实的解析陷阱，已固化为代码注释。

---

## 4. 复现方式

```bash
pip install commonroad-io          # 可选依赖，未安装时相关测试自动 skip
PYTHONPATH=src python scripts/verify_commonroad_interop.py
PYTHONPATH=src python -m unittest tests.test_commonroad_interop -v
```

未安装 `commonroad-io` 时：`commonroad` 后端仍会注册但任何 `run_episode` 会抛出
带安装提示的 `RuntimeError`，11 项集成测试自动 skip，其余测试不受影响（当前总计 144 项）。

---

## 5. Gate D 要到 PASS 还缺什么

1. 接入一个真正的第三方动力学/交通仿真器（CommonRoad 生态内的 SUMO 场景、
   或 CARLA，或 `commonroad-idm` 之类的 IDM 实现），而不是复用本项目的运动学；
2. 用**该仿真器**重跑协议 v2 的候选集，报告失效在异构动力学下的复现率——
   这才是"跨仿真系统"的科研结论；
3. 这会引入新的不确定性（传感器/执行器模型、地图差异），必须作为协议 v3 预先声明，
   不能拿本轮结果去凑。

在上述完成前，本项目的 Gate D 状态保持 **PARTIAL**，
最终报告与 README 中均按此口径表述。
