# Round 2 验收记录 —— evidence/recorder 测试套件独立运行

- 角色：测试工程师（agent=test-engineer）
- 被测实现：`src/evidence/recorder.py`（`DrivingEvidenceRecorder`）
- 测试套件：`tests/test_recorder.py`（unittest，24 个用例，Round 1 产出）
- 验收性质：独立验收，由测试工程师亲自运行；编程工程师自行的运行结果不作为依据。

## 1. 测试环境

| 项目 | 值 |
| --- | --- |
| 操作系统 | Windows 11 Home China (win32) |
| 解释器路径 | `<LOCAL_HOME>/.workbuddy/binaries/python/versions/3.13.12/python.exe` |
| 实际解释器版本 | Python 3.13.14（注：安装目录名为 `3.13.12`，但 `python --version` 实测为 `3.13.14`，属路径命名与实际版本不一致，不影响验收） |
| 运行目录 | `D:/DriveEvidenceLab/src` |
| 第三方依赖 | 无（仅标准库 unittest / json / tempfile / pathlib / sys） |

## 2. 运行命令

```bash
cd D:/DriveEvidenceLab/src
<LOCAL_HOME>/.workbuddy/binaries/python/versions/3.13.12/python.exe \
    -m unittest discover -s ../tests -p "test_*.py" -v
```

导入路径说明：测试套件内部已将 `SRC_ROOT = tests/../src` 插入 `sys.path`，
因此在 `src` 或任意目录下运行均可正确导入 `evidence.recorder`；本次按建议在
`src` 目录下运行。

## 3. 结果统计（真实输出，未做任何删改）

逐用例结果（verbose）：24 个用例逐条显示 `ok`，无 FAIL / ERROR / SKIP，涉及
测试类：

- `TestConstruction`（4 例）— ok
- `TestAddState`（3 例）— ok
- `TestAddEvent`（3 例）— ok
- `TestLinkCause`（7 例）— ok
- `TestSummary`（2 例）— ok
- `TestJsonRoundtrip`（5 例）— ok

最终统计行（原样粘贴）：

```
----------------------------------------------------------------------
Ran 24 tests in 0.050s

OK
```

进程退出码：0。

## 4. 失败用例清单

无。24 / 24 全部通过，不存在需要修改断言或上报的失败项。

## 5. JSON roundtrip 文件抽查（独立补充验证）

测试套件使用 `tempfile.TemporaryDirectory`，运行后临时 JSON 已被自动清理，
故由测试工程师在系统临时目录另行做了一次独立的 to_json/from_json 抽查
（脚本一次性执行，未写入仓库）：

- 构造含 2 帧 state（含 extra 字段 `lane_id` / `accel`）、2 个 event（含
  description 中文 / severity）、1 条 causal_link 的记录器，`to_json` 落盘；
- `json.load` 读取成功：文件为合法 JSON 文档，顶层键为
  `['causal_links', 'events', 'sampling_hz', 'scenario_id', 'states']`；
- 关键内容全部正确：`scenario_id`、`sampling_hz`、state 的 extra 字段、
  事件中文 description、`confidence=0.87` 均按预期保留；
- `from_json` 恢复后 `summary()` 与原实例一致：
  `{'scenario_id': 'SC-SPOTCHECK', 'n_states': 2, 'n_events': 2, 'n_causal_links': 1}`；
- 恢复实例可继续追加数据，新事件 ID 为 3（递增逻辑正确）。

抽查结论：SPOTCHECK: ALL PASS。

## 6. 验收结论

**通过。**

`src/evidence/recorder.py` 的实现通过了 Round 1 测试套件全部 24 个用例，
且独立 JSON roundtrip 抽查确认落盘文件内容合法、roundtrip 语义正确。

## 7. 遗留问题

1. 解释器安装目录名 `3.13.12` 与实际版本 `3.13.14` 不一致（环境侧命名问题，
   不影响测试结果，建议环境维护方知悉）。
2. `from_json` 对 `seq` / 递增计数的恢复基于 `len(states)+1` / `len(events)+1`，
   若未来 states/events 允许删除操作则该假设会失效；当前接口无删除操作，
   属未来演进注意事项，非本轮问题。
3. 测试套件未覆盖 `link_cause` 的 `relation` 参数取值约束（接口规范未约定），
   维持现状即可。

## 8. 留痕

日志文件：`D:/DriveEvidenceLab/logs/round2/test-engineer.log`
（phase=start 于运行前写入，phase=end result=OK 于收尾写入）
