# DriveEvidenceLab 测试计划 v1（Round 1）

> 负责人：test-engineer（模型：DeepSeek-V4.1-Flash）
> 日期：2026-10-19 | 被测对象：`src/evidence` —— `DrivingEvidenceRecorder`
> 测试套件：`tests/test_recorder.py`（仅 Python 标准库 unittest，禁第三方依赖）

## 1. 测试策略：三层分层

### 1.1 单元层（Unit）—— 本轮交付
- **对象**：`DrivingEvidenceRecorder` 单类的接口契约行为。
- **方法**：黑盒测试，只依赖接口规范中公开的方法
  （`__init__` / `add_state` / `add_event` / `link_cause` / `to_json` / `from_json` / `summary`），
  不耦合实现内部结构与 JSON 内部 schema。
- **覆盖矩阵**：

  | 规范条目 | 测试用例（类.方法） |
  |---|---|
  | 构造默认值 sampling_hz=10.0 | `TestConstruction.test_default_sampling_hz_is_10` |
  | 自定义 sampling_hz | `TestConstruction.test_custom_sampling_hz_accepted` |
  | 初始零计数 | `TestConstruction.test_initial_summary_zero_counts` |
  | 状态序号从 1 递增 | `TestAddState.test_first_state_returns_one` / `test_state_indices_increment` |
  | 事件 ID 从 1 递增 | `TestAddEvent.test_first_event_returns_one` / `test_event_ids_increment` |
  | link_cause 正常路径 | `TestLinkCause.test_link_cause_normal_increments_count` |
  | confidence 边界 0.0/1.0 合法 | `TestLinkCause.test_link_cause_confidence_boundaries_accepted` |
  | link_cause 事件不存在 → KeyError | `TestLinkCause.test_unknown_{effect,cause}_event_raises_keyerror` |
  | confidence 越界 → ValueError | `TestLinkCause.test_confidence_{below_zero,above_one}_raises_valueerror` |
  | 异常不污染计数 | `TestLinkCause.test_invalid_link_not_counted` |
  | summary 必需键 | `TestSummary.test_summary_contains_required_keys` |
  | summary 混合计数 | `TestSummary.test_summary_counts_after_mixed_operations` |
  | JSON roundtrip summary 一致 | `TestJsonRoundtrip.test_roundtrip_summary_consistency` |
  | from_json 为 classmethod | `TestJsonRoundtrip.test_from_json_is_classmethod_like` |
  | extra 字段透传保留（双程） | `TestJsonRoundtrip.test_roundtrip_preserves_extra_fields` |
  | 事件元数据保留 | `TestJsonRoundtrip.test_roundtrip_preserves_event_metadata` |
  | 落盘文件为合法 JSON | `TestJsonRoundtrip.test_json_output_is_valid_json_document` |

### 1.2 回归层（Regression）—— Round 2 起
- 以 Round 1 套件为基线：任何对 `src/evidence` 的后续修改（归因算法扩展、schema 演进）
  必须全量重跑 `test_recorder.py` 且全绿，防止接口契约漂移。
- 本套件同时可被 pytest 收集运行（`unittest.TestCase` 兼容），
  与团队章程第 3.4 条"pytest 验收"约定兼容；CI 命令二选一：
  - `python -m unittest discover -s tests -v`
  - `python -m pytest tests/ -v`（环境具备时）

### 1.3 复现层（Reproduction）—— Round 2+ 按需
- 针对仿真回放/归因场景的端到端复现：固定 scenario_id 与输入序列，
  断言证据链（状态 → 事件 → 因果链接）完整可回放。
- 触发条件：算法工程师交付场景级功能或审查员提出可复现缺陷时，
  以最小失败用例（MFE）形式追加 `tests/test_repro_*.py`。

## 2. TDD 约定与守卫机制
- 本轮模块本体并行开发中，测试先行交付；`test_recorder.py` 通过
  `setUpModule` 守卫：`src/evidence` 未就位或未导出
  `DrivingEvidenceRecorder` 时整套 **SKIP**（不伪绿、不误红）。
- 导入路径约定：测试自动将 `src/` 加入 `sys.path`，依次尝试
  `evidence.recorder` / `evidence` 顶层导出。
- 黑盒断言原则：extra 字段与事件元数据的保留性通过
  "to_json 落盘 → JSON 递归展平 → (键, 值) 对存在性" 判定，
  不依赖实现内部 schema，给编程工程师留出自由实现空间。

## 3. Round 2 验收流程
1. **就位检查**：确认 `src/evidence` 已实现并导出 `DrivingEvidenceRecorder`。
2. **语法/导入冒烟**：`python -m py_compile tests/test_recorder.py`；
   确认 SKIP 守卫解除（`setUpModule` 不再触发 SkipTest）。
3. **全量运行**：`python -m unittest discover -s tests -v`，
   真实记录输出到 `logs/round2/test-engineer.log`（含时间戳）。
4. **结果判定**：
   - 全绿 → 出具验收通过结论，套件冻结为回归基线；
   - 有失败 → 逐条记录失败用例与 traceback，如实上报编程工程师修复，
     禁止为凑绿修改测试断言（除非确认断言本身偏离接口规范）。
5. **归档**：测试报告写入 `docs/`，日志证据写入 `logs/round2/`，
   任务清单状态同步总指挥。

## 4. 变更记录
- 2026-10-19 v1：初版（test-engineer，DeepSeek-V4.1-Flash）。
