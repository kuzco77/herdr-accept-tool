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


if __name__ == "__main__":
    unittest.main()
