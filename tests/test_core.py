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


if __name__ == "__main__":
    unittest.main()
