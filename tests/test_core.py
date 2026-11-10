"""herdr-core (hc) support: backends, CLI targets, core_api and supervisor sources."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("HERDR_ACCEPT_STATE_DIR", tempfile.mkdtemp(prefix="herdr-accept-test-"))

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

import herdr_accept_tool as tool  # noqa: E402
import test_parse as cc  # noqa: E402
from herdr_accept_tool import (  # noqa: E402
    DEFAULT_PREFER,
    MODE_ALL,
    Answerer,
    CoreBackend,
    HerdrError,
    TuiBackend,
)

PREFER = re.compile(DEFAULT_PREFER)


class RecordingBackend:
    def __init__(self, screen: str = "") -> None:
        self.screen = screen
        self.sent = []

    def read_screen(self, target: str, lines: int) -> str:
        return self.screen

    def send_keys(self, target: str, keys) -> None:
        self.sent.append((target, list(keys)))


class RunHcTest(unittest.TestCase):
    def test_error_message_comes_from_json_stdout(self) -> None:
        failed = subprocess.CompletedProcess(
            args=[], returncode=3,
            stdout='{"error":{"kind":"not_found","message":"no terminal \\"x\\""}}', stderr="",
        )
        with mock.patch("herdr_accept_tool.subprocess.run", return_value=failed):
            with self.assertRaisesRegex(HerdrError, 'no terminal "x"'):
                tool.run_hc(["get", "x"])

    def test_missing_binary_is_herdr_error(self) -> None:
        with mock.patch("herdr_accept_tool.subprocess.run", side_effect=OSError("nope")):
            with self.assertRaisesRegex(HerdrError, "cannot run hc"):
                tool.run_hc(["ls"])


class CoreBackendTest(unittest.TestCase):
    def test_read_screen_returns_text(self) -> None:
        raw = json.dumps({"complete": True, "how": "screen", "text": "hello\n❯ 1. Yes"})
        with mock.patch("herdr_accept_tool.run_hc", return_value=raw) as run:
            self.assertEqual(CoreBackend().read_screen("t17", 80), "hello\n❯ 1. Yes")
        run.assert_called_once_with(["read", "--json", "t17"])

    def test_read_screen_rejects_unexpected_output(self) -> None:
        with mock.patch("herdr_accept_tool.run_hc", return_value="not json"):
            with self.assertRaises(HerdrError):
                CoreBackend().read_screen("t17", 80)

    def test_send_keys_lowercases_names(self) -> None:
        with mock.patch("herdr_accept_tool.run_hc") as run:
            CoreBackend().send_keys("t17", ["Down", "Space", "Enter", "y"])
        run.assert_called_once_with(["keys", "t17", "down", "space", "enter", "y"])


class AnswererBackendTest(unittest.TestCase):
    def test_answer_sends_through_backend(self) -> None:
        backend = RecordingBackend()
        answerer = Answerer(pane_id="t17", prefer=PREFER, quiet=True, mode=MODE_ALL, backend=backend)
        self.assertTrue(answerer.answer(cc.PERMISSION))
        self.assertEqual(backend.sent, [("t17", ["Enter"])])

    def test_default_backend_is_tui(self) -> None:
        self.assertIsInstance(Answerer(pane_id="w1:p1", prefer=PREFER).backend, TuiBackend)


class ResolveTargetTest(unittest.TestCase):
    def test_core_prefix_checks_terminal_and_uses_core_backend(self) -> None:
        with mock.patch("herdr_accept_tool.run_hc", return_value="{}") as run:
            target, backend = tool.resolve_target("core:t17")
        run.assert_called_once_with(["get", "t17"])
        self.assertEqual(target, "t17")
        self.assertIsInstance(backend, CoreBackend)

    def test_other_targets_use_tui(self) -> None:
        with mock.patch("herdr_accept_tool.resolve_pane", return_value="w26:p4D"):
            target, backend = tool.resolve_target("my-agent")
        self.assertEqual(target, "w26:p4D")
        self.assertIsInstance(backend, TuiBackend)

    def test_unknown_core_terminal_raises(self) -> None:
        with mock.patch("herdr_accept_tool.run_hc", side_effect=HerdrError('no terminal "t99"')):
            with self.assertRaises(HerdrError):
                tool.resolve_target("core:t99")


import accept_state as state  # noqa: E402
import core_api  # noqa: E402

T17 = {
    "address": "t17",
    "cwd": "/Users/x/Developer/Personal",
    "foreground": {"argv": ["claude", "--resume", "abc"], "name": "2.1.321"},
    "labels": {"accept": "all", "accept.at": "1000", "herdr.space": "sp1"},
    "state": "live",
}


def fake_hc(records):
    """run_hc stand-in: `ls --label accept=<mode>` and `get <address>` over records."""

    def run(args):
        if args[0] == "ls":
            mode = args[-1].split("=", 1)[1]
            hits = [{"address": a} for a, r in records.items() if r["labels"].get("accept") == mode]
            return json.dumps({"terminals": hits, "machines": []})
        if args[0] == "get":
            return json.dumps(records[args[1]])
        raise AssertionError("unexpected hc call %r" % (args,))

    return run


class CoreApiTest(unittest.TestCase):
    def test_armed_terminals_lists_both_modes(self) -> None:
        t18 = dict(T17, address="t18", labels={"accept": "permissions", "accept.at": "1000"})
        with mock.patch("core_api.run_hc", side_effect=fake_hc({"t17": T17, "t18": t18})):
            found = core_api.armed_terminals()
        self.assertEqual(sorted(found), ["t17", "t18"])
        self.assertEqual(found["t18"]["labels"]["accept"], "permissions")

    def test_terminal_gone_between_ls_and_get_is_skipped(self) -> None:
        listed = fake_hc({"t17": T17})

        def run(args):
            if args[0] == "get":
                raise HerdrError('no terminal "t17"')
            return listed(args)

        with mock.patch("core_api.run_hc", side_effect=run):
            self.assertEqual(core_api.armed_terminals(), {})

    def test_armed_entry_reads_labels(self) -> None:
        entry = core_api.armed_entry("t17", T17, ttl=60.0)
        self.assertEqual((entry.pane_id, entry.mode, entry.armed_at, entry.ttl), ("t17", MODE_ALL, 1000.0, 60.0))
        self.assertTrue(entry.expired(now=1060.0))

    def test_bad_armed_at_expires_at_once(self) -> None:
        record = dict(T17, labels={"accept": "all", "accept.at": "soon"})
        self.assertTrue(core_api.armed_entry("t17", record, ttl=60.0).expired(now=61.0))

    def test_non_finite_or_missing_armed_at_expires_at_once(self) -> None:
        for raw in ("nan", "inf", "1e400", None):
            with self.subTest(armed_at=raw):
                record = dict(T17, labels={"accept": "all", "accept.at": raw})
                self.assertTrue(core_api.armed_entry("t17", record, ttl=60.0).expired(now=61.0))

    def test_non_dict_labels_are_treated_as_empty(self) -> None:
        record = dict(T17, labels=["accept"])
        entry = core_api.armed_entry("t17", record, ttl=60.0)
        self.assertEqual((entry.mode, entry.armed_at), (MODE_ALL, 0.0))
        self.assertTrue(entry.expired(now=61.0))

    def test_non_dict_listing_entry_is_skipped(self) -> None:
        def run(args):
            if args[0] == "ls":
                return json.dumps({"terminals": ["t99", None, {"address": "t17"}]})
            return json.dumps(T17)

        with mock.patch("core_api.run_hc", side_effect=run):
            self.assertEqual(sorted(core_api.armed_terminals()), ["t17"])

    def test_process_name_uses_argv_not_version_name(self) -> None:
        self.assertEqual(core_api.process_name(T17), "claude")
        self.assertEqual(core_api.process_name({"foreground": {"argv": ["/bin/zsh", "-l"]}}), "zsh")
        self.assertEqual(core_api.process_name({"foreground": {"argv": ["-zsh"]}}), "zsh")
        self.assertIsNone(core_api.process_name({"foreground": None}))
        self.assertIsNone(core_api.process_name(None))

    def test_disarm_removes_both_labels(self) -> None:
        with mock.patch("core_api.run_hc") as run:
            core_api.disarm("t17")
        run.assert_called_once_with(["label", "t17", "accept=", "accept.at="])


class HeartbeatTest(unittest.TestCase):
    def test_heartbeat_holds_epoch(self) -> None:
        with mock.patch("accept_state.time.time", return_value=1234.9):
            state.touch_heartbeat()
        self.assertEqual(state.HEARTBEAT_FILE.read_text(), "1234")


from supervisor import CoreSource, Supervisor, TuiSource, build_parser  # noqa: E402


class FakeSource:
    def __init__(self, name, armed=None, live=None, process=None, screen="", error=None, crash=None, backend=None):
        self.name = name
        self.backend = backend or RecordingBackend(screen)
        self.armed = armed or {}
        self.live = live or {}
        self.process = process or {}
        self.error = error
        self.crash = crash
        self.snapshots = 0
        self.disarmed = []

    def snapshot(self):
        self.snapshots += 1
        if self.crash:
            raise self.crash
        if self.error:
            raise HerdrError(self.error)
        return self.armed, self.live, self.process.get

    def disarm(self, target, reason, live):
        self.disarmed.append((target, reason, live))


def core_armed(address, armed_at=1e12, mode=MODE_ALL):
    return state.Armed(pane_id=address, cwd="/tmp", armed_at=armed_at, ttl=3600.0, label_before=None, mode=mode)


class SupervisorSourcesTest(unittest.TestCase):
    def supervisor(self, *sources):
        return Supervisor(build_parser().parse_args(["--settle", "0"]), sources=list(sources))

    def test_default_sources_are_tui_then_core(self) -> None:
        supervisor = Supervisor(build_parser().parse_args([]))
        self.assertEqual([type(s) for s in supervisor.sources], [TuiSource, CoreSource])

    def test_core_prompt_answered_through_core_backend(self) -> None:
        core = FakeSource("core", {"t17": core_armed("t17")}, {"t17": {}}, {"t17": "claude"}, screen=cc.PERMISSION)
        self.assertTrue(self.supervisor(core).cycle())
        self.assertEqual(core.backend.sent, [("t17", ["Enter"])])

    def test_down_source_backs_off_alone(self) -> None:
        tui = FakeSource("tui", error="socket gone")
        core = FakeSource("core", {"t17": core_armed("t17")}, {"t17": {}}, {"t17": "claude"}, screen=cc.PERMISSION)
        supervisor = self.supervisor(tui, core)
        self.assertTrue(supervisor.cycle())
        self.assertTrue(supervisor.cycle())
        self.assertEqual(tui.snapshots, 1)
        self.assertEqual(core.snapshots, 2)

    def test_expired_core_terminal_is_disarmed(self) -> None:
        core = FakeSource("core", {"t17": core_armed("t17", armed_at=0.0)}, {"t17": {}}, {"t17": "claude"})
        self.assertFalse(self.supervisor(core).cycle())
        self.assertEqual(core.disarmed, [("t17", "ttl expired", True)])

    def test_core_shell_stays_idle(self) -> None:
        core = FakeSource("core", {"t17": core_armed("t17")}, {"t17": {}}, {"t17": "zsh"}, screen=cc.PERMISSION)
        self.assertFalse(self.supervisor(core).cycle())
        self.assertEqual(core.backend.sent, [])
        self.assertEqual(core.disarmed, [])

    def test_core_source_snapshot_from_labels(self) -> None:
        with mock.patch("core_api.run_hc", side_effect=fake_hc({"t17": T17})):
            armed, live, process_of = CoreSource().snapshot()
        self.assertEqual(list(armed), ["t17"])
        self.assertEqual(armed["t17"].mode, MODE_ALL)
        self.assertIn("t17", live)
        self.assertEqual(process_of("t17"), "claude")


class SendFailsFor(RecordingBackend):
    def __init__(self, screen: str, failing_target: str) -> None:
        super().__init__(screen)
        self.failing_target = failing_target

    def send_keys(self, target: str, keys) -> None:
        if target == self.failing_target:
            raise HerdrError("pane %s closed" % target)
        super().send_keys(target, keys)


class UnreadableScreen(RecordingBackend):
    def read_screen(self, target: str, lines: int) -> str:
        raise TypeError("screen is not text")


class SourceFailureIsolationTest(unittest.TestCase):
    def supervisor(self, *sources):
        return Supervisor(build_parser().parse_args(["--settle", "0"]), sources=list(sources))

    def healthy_core(self):
        return FakeSource("core", {"t17": core_armed("t17")}, {"t17": {}}, {"t17": "claude"}, screen=cc.PERMISSION)

    def test_unexpected_snapshot_error_does_not_stop_other_source(self) -> None:
        bad = FakeSource("tui", crash=TypeError("malformed"))
        core = self.healthy_core()
        self.assertTrue(self.supervisor(bad, core).cycle())
        self.assertEqual(core.backend.sent, [("t17", ["Enter"])])

    def test_unexpected_snapshot_error_backs_off_the_source(self) -> None:
        bad = FakeSource("tui", crash=TypeError("malformed"))
        core = self.healthy_core()
        supervisor = self.supervisor(bad, core)
        supervisor.cycle()
        supervisor.cycle()
        self.assertEqual(bad.snapshots, 1)
        self.assertEqual(core.snapshots, 2)

    def test_error_is_logged_with_source_name_and_exception(self) -> None:
        bad = FakeSource("tui", crash=TypeError("malformed"))
        with mock.patch("supervisor.log") as log:
            self.supervisor(bad).cycle()
        message = log.call_args[0][0]
        self.assertIn("tui", message)
        self.assertIn("TypeError", message)
        self.assertIn("malformed", message)

    def test_keyboard_interrupt_still_stops_the_supervisor(self) -> None:
        interrupted = FakeSource("tui", crash=KeyboardInterrupt())
        with self.assertRaises(KeyboardInterrupt):
            self.supervisor(interrupted).cycle()

    def test_unexpected_error_while_reading_backs_off_the_source(self) -> None:
        core = FakeSource(
            "core", {"t17": core_armed("t17")}, {"t17": {}}, {"t17": "claude"}, backend=UnreadableScreen()
        )
        other = self.healthy_core()
        other.name = "other"
        supervisor = self.supervisor(core, other)
        self.assertTrue(supervisor.cycle())
        supervisor.cycle()
        self.assertEqual(core.snapshots, 1)
        self.assertEqual(other.backend.sent, [("t17", ["Enter"])])

    def test_failed_key_send_does_not_stop_other_targets(self) -> None:
        backend = SendFailsFor(cc.PERMISSION, failing_target="t17")
        armed = {"t17": core_armed("t17"), "t18": core_armed("t18")}
        core = FakeSource(
            "core", armed, {"t17": {}, "t18": {}}, {"t17": "claude", "t18": "claude"}, backend=backend
        )
        self.assertTrue(self.supervisor(core).cycle())
        self.assertEqual(backend.sent, [("t18", ["Enter"])])

    def test_failed_key_send_does_not_back_off_the_source(self) -> None:
        backend = SendFailsFor(cc.PERMISSION, failing_target="t17")
        core = FakeSource("core", {"t17": core_armed("t17")}, {"t17": {}}, {"t17": "claude"}, backend=backend)
        supervisor = self.supervisor(core)
        supervisor.cycle()
        supervisor.cycle()
        self.assertEqual(core.snapshots, 2)
        self.assertNotIn("core", supervisor.retry)


class TuiSourceTest(unittest.TestCase):
    PANE = "w1:p1"

    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        for name, value in (("STATE_DIR", Path(directory.name)), ("STATE_FILE", Path(directory.name) / "armed.json")):
            patcher = mock.patch.object(state, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        state.arm_pane(
            state.Armed(pane_id=self.PANE, cwd="/tmp", armed_at=1e12, ttl=3600.0, label_before="build", mode=MODE_ALL)
        )

    def test_live_disarm_removes_entry_renames_and_notifies(self) -> None:
        with mock.patch("supervisor.herdr.rename_pane") as rename, mock.patch("supervisor.herdr.notify") as notify:
            TuiSource().disarm(self.PANE, "ttl expired", live=True)
        self.assertEqual(state.load_state(), {})
        rename.assert_called_once_with(self.PANE, "build")
        notify.assert_called_once()

    def test_live_disarm_restores_label_without_marker(self) -> None:
        state.arm_pane(
            state.Armed(pane_id="w1:p2", cwd="/tmp", armed_at=1e12, ttl=3600.0, label_before=state.LABEL_MARKER + "api")
        )
        with mock.patch("supervisor.herdr.rename_pane") as rename, mock.patch("supervisor.herdr.notify"):
            TuiSource().disarm("w1:p2", "ttl expired", live=True)
        rename.assert_called_once_with("w1:p2", "api")

    def test_dead_disarm_removes_entry_without_rename_or_notify(self) -> None:
        with mock.patch("supervisor.herdr.rename_pane") as rename, mock.patch("supervisor.herdr.notify") as notify:
            TuiSource().disarm(self.PANE, "pane closed", live=False)
        self.assertEqual(state.load_state(), {})
        rename.assert_not_called()
        notify.assert_not_called()

    def test_empty_state_snapshot_makes_no_herdr_call(self) -> None:
        state.remove_panes([self.PANE])
        with mock.patch("supervisor.herdr.list_panes") as list_panes:
            armed, live, process_of = TuiSource().snapshot()
        self.assertEqual((armed, live), ({}, {}))
        self.assertIsNone(process_of(self.PANE))
        list_panes.assert_not_called()


class BackoffTest(unittest.TestCase):
    def setUp(self) -> None:
        patcher = mock.patch("supervisor.time.time")
        self.clock = patcher.start()
        self.addCleanup(patcher.stop)
        self.source = FakeSource("tui", error="socket gone")
        self.supervisor = Supervisor(build_parser().parse_args(["--settle", "0"]), sources=[self.source])

    def cycle_at(self, now: float) -> int:
        """Run one cycle at ``now``; return how many snapshots it took."""
        self.clock.return_value = now
        before = self.source.snapshots
        self.supervisor.cycle()
        return self.source.snapshots - before

    def test_failing_source_is_retried_only_after_its_window(self) -> None:
        self.assertEqual(self.cycle_at(100.0), 1)
        self.assertEqual(self.cycle_at(104.9), 0)
        self.assertEqual(self.cycle_at(105.0), 1)

    def test_consecutive_failures_double_the_wait_up_to_sixty_seconds(self) -> None:
        now = 100.0
        waits = []
        for _ in range(7):
            self.assertEqual(self.cycle_at(now), 1)
            retry_at, _next = self.supervisor.retry["tui"]
            waits.append(retry_at - now)
            self.assertEqual(self.cycle_at(retry_at - 0.1), 0)
            now = retry_at
        self.assertEqual(waits, [5.0, 10.0, 20.0, 40.0, 60.0, 60.0, 60.0])

    def test_success_resets_the_wait_to_five_seconds(self) -> None:
        self.cycle_at(100.0)
        self.cycle_at(105.0)
        self.assertEqual(self.supervisor.retry["tui"][0] - 105.0, 10.0)
        self.source.error = None
        self.assertEqual(self.cycle_at(115.0), 1)
        self.assertNotIn("tui", self.supervisor.retry)
        self.source.error = "socket gone"
        self.assertEqual(self.cycle_at(116.0), 1)
        self.assertEqual(self.supervisor.retry["tui"][0] - 116.0, 5.0)


if __name__ == "__main__":
    unittest.main()
