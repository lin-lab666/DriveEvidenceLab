# -*- coding: utf-8 -*-
"""DriveEvidenceLab 驾驶证据链记录模块 —— TDD 测试套件（Round 1）。

被测接口规范（DrivingEvidenceRecorder）：
    - DrivingEvidenceRecorder(scenario_id: str, sampling_hz: float = 10.0)
    - add_state(timestamp, ego_x, ego_y, ego_v, ego_heading, **extra) -> int
      状态序号从 1 起递增；extra 键值对透传保留。
    - add_event(timestamp, event_type, description="", severity=1) -> int
      事件 ID 从 1 起递增。
    - link_cause(effect_event_id, cause_event_id, relation, confidence)
      事件 ID 不存在 -> KeyError；confidence 超出 [0, 1] -> ValueError。
    - to_json(path) / from_json(path)（classmethod），roundtrip 后 summary() 一致。
    - summary() -> dict，含 scenario_id / n_states / n_events / n_causal_links。

TDD 约定：
    - 本套件仅依赖 Python 标准库（unittest / json / tempfile / pathlib / sys）。
    - 模块本体由编程工程师并行开发；若 src/evidence 尚未就位，
      整个套件以 SKIP 结束（既不伪绿也不误红），待 Round 2 模块合入后运行。
    - 本套件同时兼容 unittest 与 pytest 两种运行器（pytest 可直接收集 unittest.TestCase）。
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

# 将 src/ 纳入导入路径（被测包预期位于 src/evidence/）
SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from driveevidence.evidence.recorder import DrivingEvidenceRecorder


def _flatten_pairs(obj, out):
    """递归展平 JSON 反序列化结果，收集全部 (键, 标量值) 对。

    由于接口规范未约定 JSON 内部 schema，extra 字段保留性等断言
    采用"键值对在全文档中出现"的黑盒判定，不耦合实现细节。
    """
    if isinstance(obj, dict):
        for key, value in obj.items():
            if isinstance(value, (str, int, float, bool)) or value is None:
                out.add((key, value))
            _flatten_pairs(value, out)
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            _flatten_pairs(item, out)
    return out


class RecorderTestCase(unittest.TestCase):
    """公共基类：提供构造便捷方法与临时 JSON 文件路径。"""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory(prefix="del_test_")
        self.addCleanup(self._tmpdir.cleanup)
        self.json_path = str(Path(self._tmpdir.name) / "evidence.json")

    def make_recorder(self, scenario_id="SC-001", sampling_hz=None):
        if sampling_hz is None:
            return DrivingEvidenceRecorder(scenario_id)
        return DrivingEvidenceRecorder(scenario_id, sampling_hz)

    def dump_pairs(self, path=None):
        """读取 to_json 落盘文件并展平为 (键, 值) 对集合。"""
        with open(path or self.json_path, "r", encoding="utf-8") as fh:
            return _flatten_pairs(json.load(fh), set())


class TestConstruction(RecorderTestCase):
    """构造函数与默认值。"""

    def test_default_sampling_hz_is_10(self):
        rec = self.make_recorder("SC-DEFAULT")
        self.assertEqual(getattr(rec, "sampling_hz", 10.0), 10.0)

    def test_custom_sampling_hz_accepted(self):
        rec = self.make_recorder("SC-HZ50", sampling_hz=50.0)
        self.assertEqual(getattr(rec, "sampling_hz"), 50.0)

    def test_scenario_id_recorded(self):
        rec = self.make_recorder("SC-EVIDENT")
        summary = rec.summary()
        self.assertEqual(summary.get("scenario_id"), "SC-EVIDENT")

    def test_initial_summary_zero_counts(self):
        rec = self.make_recorder("SC-INIT")
        summary = rec.summary()
        self.assertEqual(summary.get("n_states"), 0)
        self.assertEqual(summary.get("n_events"), 0)
        self.assertEqual(summary.get("n_causal_links"), 0)


class TestAddState(RecorderTestCase):
    """add_state：状态序号从 1 起严格递增。"""

    def test_first_state_returns_one(self):
        rec = self.make_recorder()
        self.assertEqual(rec.add_state(0.0, 0.0, 0.0, 25.5, 0.0), 1)

    def test_state_indices_increment(self):
        rec = self.make_recorder()
        seq = [rec.add_state(t * 0.1, t, 0.0, 25.5, 0.0) for t in range(5)]
        self.assertEqual(seq, [1, 2, 3, 4, 5])

    def test_summary_counts_states(self):
        rec = self.make_recorder()
        for _ in range(3):
            rec.add_state(0.0, 0.0, 0.0, 25.5, 0.0)
        self.assertEqual(rec.summary().get("n_states"), 3)


class TestAddEvent(RecorderTestCase):
    """add_event：事件 ID 从 1 起严格递增。"""

    def test_first_event_returns_one(self):
        rec = self.make_recorder()
        self.assertEqual(rec.add_event(1.23, "LANE_DEPARTURE"), 1)

    def test_event_ids_increment(self):
        rec = self.make_recorder()
        ids = [rec.add_event(t, "EVENT_%d" % t) for t in range(1, 4)]
        self.assertEqual(ids, [1, 2, 3])

    def test_summary_counts_events(self):
        rec = self.make_recorder()
        rec.add_event(0.5, "BRAKE")
        rec.add_event(1.5, "TAKEOVER")
        self.assertEqual(rec.summary().get("n_events"), 2)


class TestLinkCause(RecorderTestCase):
    """link_cause：正常链接、KeyError / ValueError 异常路径。"""

    def _recorder_with_two_events(self):
        rec = self.make_recorder()
        rec.add_event(0.5, "OBSTACLE_DETECTED")   # ID 1
        rec.add_event(2.5, "EMERGENCY_BRAKE")     # ID 2
        return rec

    def test_link_cause_normal_increments_count(self):
        rec = self._recorder_with_two_events()
        rec.link_cause(2, 1, "causes", confidence=0.9)
        self.assertEqual(rec.summary().get("n_causal_links"), 1)
        rec.link_cause(2, 1, "reinforces", confidence=0.4)
        self.assertEqual(rec.summary().get("n_causal_links"), 2)

    def test_link_cause_confidence_boundaries_accepted(self):
        rec = self._recorder_with_two_events()
        rec.link_cause(2, 1, "causes", confidence=0.0)   # 下边界合法
        rec.link_cause(1, 2, "explains", confidence=1.0)  # 上边界合法
        self.assertEqual(rec.summary().get("n_causal_links"), 2)

    def test_unknown_effect_event_raises_keyerror(self):
        rec = self._recorder_with_two_events()
        with self.assertRaises(KeyError):
            rec.link_cause(999, 1, "causes", confidence=0.9)

    def test_unknown_cause_event_raises_keyerror(self):
        rec = self._recorder_with_two_events()
        with self.assertRaises(KeyError):
            rec.link_cause(2, 999, "causes", confidence=0.9)

    def test_confidence_below_zero_raises_valueerror(self):
        rec = self._recorder_with_two_events()
        with self.assertRaises(ValueError):
            rec.link_cause(2, 1, "causes", confidence=-0.01)

    def test_confidence_above_one_raises_valueerror(self):
        rec = self._recorder_with_two_events()
        with self.assertRaises(ValueError):
            rec.link_cause(2, 1, "causes", confidence=1.01)

    def test_invalid_link_not_counted(self):
        """异常路径不得污染 n_causal_links 计数。"""
        rec = self._recorder_with_two_events()
        for call in (
            lambda: rec.link_cause(999, 1, "causes", confidence=0.9),
            lambda: rec.link_cause(2, 1, "causes", confidence=1.5),
        ):
            with self.assertRaises((KeyError, ValueError)):
                call()
        self.assertEqual(rec.summary().get("n_causal_links"), 0)


class TestSummary(RecorderTestCase):
    """summary()：键完整性与混合操作后的计数正确性。"""

    REQUIRED_KEYS = ("scenario_id", "n_states", "n_events", "n_causal_links")

    def test_summary_contains_required_keys(self):
        summary = self.make_recorder("SC-KEYS").summary()
        for key in self.REQUIRED_KEYS:
            self.assertIn(key, summary, "summary() 缺少必需键 %r" % key)

    def test_summary_counts_after_mixed_operations(self):
        rec = self.make_recorder("SC-MIX")
        for i in range(4):
            rec.add_state(i * 0.1, float(i), 0.0, 25.5, 0.0)
        rec.add_event(0.2, "OBSTACLE_DETECTED")       # ID 1
        rec.add_event(0.4, "EMERGENCY_BRAKE")         # ID 2
        rec.add_event(0.6, "TAKEOVER_REQUEST")        # ID 3
        rec.link_cause(2, 1, "causes", confidence=0.9)
        rec.link_cause(3, 1, "triggers", confidence=0.7)

        summary = rec.summary()
        self.assertEqual(summary.get("scenario_id"), "SC-MIX")
        self.assertEqual(summary.get("n_states"), 4)
        self.assertEqual(summary.get("n_events"), 3)
        self.assertEqual(summary.get("n_causal_links"), 2)


class TestJsonRoundtrip(RecorderTestCase):
    """to_json / from_json：roundtrip 一致性与 extra 字段保留。"""

    def _build_rich_recorder(self):
        rec = self.make_recorder("SC-ROUNDTRIP", sampling_hz=20.0)
        rec.add_state(0.0, 0.0, 0.0, 25.5, 0.0, lane_id="L2", accel=1.5)
        rec.add_state(0.1, 2.55, 0.0, 25.6, 0.01, lane_id="L2", accel=-0.3)
        rec.add_event(0.08, "OBSTACLE_DETECTED",
                      description="前方 30m 出现锥桶", severity=2)   # ID 1
        rec.add_event(0.15, "EMERGENCY_BRAKE", severity=3)           # ID 2
        rec.link_cause(2, 1, "causes", confidence=0.87)
        return rec

    def test_roundtrip_summary_consistency(self):
        rec = self._build_rich_recorder()
        rec.to_json(self.json_path)
        restored = DrivingEvidenceRecorder.from_json(self.json_path)
        self.assertEqual(rec.summary(), restored.summary())

    def test_from_json_is_classmethod_like(self):
        """from_json 通过类调用并返回本类实例（classmethod 约定）。"""
        rec = self._build_rich_recorder()
        rec.to_json(self.json_path)
        restored = DrivingEvidenceRecorder.from_json(self.json_path)
        self.assertIsInstance(restored, DrivingEvidenceRecorder)

    def test_roundtrip_preserves_extra_fields(self):
        """add_state 的 **extra 键值在 to_json -> from_json -> to_json 全链路保留。"""
        rec = self._build_rich_recorder()
        rec.to_json(self.json_path)
        restored = DrivingEvidenceRecorder.from_json(self.json_path)

        second_path = str(Path(self._tmpdir.name) / "restored.json")
        restored.to_json(second_path)

        for path in (self.json_path, second_path):
            pairs = self.dump_pairs(path)
            self.assertIn(("lane_id", "L2"), pairs,
                          "extra 字段 lane_id 未在 %s 中保留" % path)
            self.assertIn(("accel", 1.5), pairs,
                          "extra 字段 accel 未在 %s 中保留" % path)

    def test_roundtrip_preserves_event_metadata(self):
        """事件 description / severity / event_type 在 roundtrip 后保留。"""
        rec = self._build_rich_recorder()
        rec.to_json(self.json_path)
        pairs = self.dump_pairs(self.json_path)
        self.assertIn(("event_type", "OBSTACLE_DETECTED"), pairs)
        self.assertIn(("description", "前方 30m 出现锥桶"), pairs)
        self.assertIn(("severity", 2), pairs)
        self.assertIn(("severity", 3), pairs)

    def test_json_output_is_valid_json_document(self):
        rec = self._build_rich_recorder()
        rec.to_json(self.json_path)
        with open(self.json_path, "r", encoding="utf-8") as fh:
            doc = json.load(fh)  # 非法 JSON 会直接抛异常使测试失败
        self.assertIsInstance(doc, (dict, list))


if __name__ == "__main__":
    unittest.main(verbosity=2)
