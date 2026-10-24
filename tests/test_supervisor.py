"""State file and supervisor cycle planning, without touching herdr."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

TMP_STATE = tempfile.mkdtemp(prefix="herdr-accept-test-")
os.environ["HERDR_ACCEPT_STATE_DIR"] = TMP_STATE

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import accept_state as state  # noqa: E402
from supervisor import plan_cycle  # noqa: E402


def armed(pane_id: str, armed_at: float = 1000.0, ttl: float = 3600.0) -> state.Armed:
    return state.Armed(pane_id=pane_id, cwd="/tmp", armed_at=armed_at, ttl=ttl, label_before=None)


class StateFileTest(unittest.TestCase):
    def setUp(self) -> None:
        state.save_state({})

    def test_roundtrip(self) -> None:
        state.arm_pane(armed("w1:p1"))
        state.arm_pane(armed("w1:p2"))
        loaded = state.load_state()
        self.assertEqual(sorted(loaded), ["w1:p1", "w1:p2"])
        self.assertEqual(loaded["w1:p1"].ttl, 3600.0)

    def test_remove_rereads_file_before_writing(self) -> None:
        state.arm_pane(armed("w1:p1"))
        stale = state.load_state()
        state.arm_pane(armed("w1:p2"))
        removed = state.remove_panes(["w1:p1"])
        self.assertEqual(list(removed), ["w1:p1"])
        self.assertEqual(list(state.load_state()), ["w1:p2"])
        self.assertEqual(list(stale), ["w1:p1"])

    def test_missing_file_is_empty(self) -> None:
        state.STATE_FILE.unlink()
        self.assertEqual(state.load_state(), {})

    def test_expiry(self) -> None:
        entry = armed("w1:p1", armed_at=1000.0, ttl=60.0)
        self.assertFalse(entry.expired(now=1059.0))
        self.assertTrue(entry.expired(now=1060.0))
        self.assertFalse(armed("w1:p1", ttl=0).expired(now=1e12))

    def test_label_marker(self) -> None:
        self.assertEqual(state.marked_label("claude - w1:p1", "auto"), "⚡ claude - w1:p1")
        self.assertEqual(state.marked_label(None, "claude"), "⚡ claude")
        self.assertEqual(state.marked_label("⚡ x", "auto"), "⚡ x")
        self.assertEqual(state.unmarked_label("⚡ x"), "x")
        self.assertIsNone(state.unmarked_label(None))


class PlanCycleTest(unittest.TestCase):
    def test_closed_pane_is_dropped(self) -> None:
        plan = plan_cycle({"w1:p1": armed("w1:p1")}, {}, now=2000.0, process_of=lambda _: "claude")
        self.assertEqual(plan.dropped, {"w1:p1": "pane closed"})

    def test_expired_pane_is_dropped(self) -> None:
        plan = plan_cycle(
            {"w1:p1": armed("w1:p1", armed_at=0.0, ttl=10.0)},
            {"w1:p1": {}},
            now=11.0,
            process_of=lambda _: "claude",
        )
        self.assertEqual(plan.dropped, {"w1:p1": "ttl expired"})

    def test_plain_shell_is_idle_not_dropped(self) -> None:
        plan = plan_cycle({"w1:p1": armed("w1:p1")}, {"w1:p1": {}}, now=2000.0, process_of=lambda _: "zsh")
        self.assertEqual(plan.idle, {"w1:p1": "zsh"})
        self.assertEqual(plan.active, [])
        self.assertEqual(plan.dropped, {})

    def test_agent_panes_are_active(self) -> None:
        procs = {"w1:p1": "claude", "w1:p2": "agy", "w1:p3": None}
        plan = plan_cycle(
            {pane: armed(pane) for pane in procs},
            {pane: {} for pane in procs},
            now=2000.0,
            process_of=procs.get,
        )
        self.assertEqual(plan.active, ["w1:p1", "w1:p2"])
        self.assertEqual(plan.idle, {"w1:p3": "no process"})


if __name__ == "__main__":
    unittest.main()
