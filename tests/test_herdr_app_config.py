"""keys.json merging and layout header edits for the herdr-app install."""

from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import herdr_app_config as config  # noqa: E402

LAYOUT = {
    "type": "row",
    "children": [
        {"type": "block", "content": {"mod": "spaces"}},
        {
            "id": "main",
            "type": "block",
            "content": {
                "tab": "active",
                "pane": {"gap": 8, "header": {"content": {"mod": "pane"}, "height": 30, "position": "top", "reveal": "always"}},
            },
        },
    ],
}


class KeysTest(unittest.TestCase):
    def test_add_keys_merges_into_global(self) -> None:
        keys = {"global": {"ctrl-a t": "tab.new"}, "terminal": {}}
        self.assertEqual(config.add_keys(keys), [])
        self.assertEqual(keys["global"]["ctrl-a y"], "accept-header.toggle")
        self.assertEqual(keys["global"]["ctrl-a u"], "accept-header.toggle-permissions")
        self.assertEqual(keys["global"]["ctrl-a shift-y"], "accept-header.disarm-all")
        self.assertEqual(keys["global"]["ctrl-a t"], "tab.new")

    def test_add_keys_refuses_conflicts_and_changes_nothing(self) -> None:
        keys = {"global": {"ctrl-a y": "tab.new"}}
        self.assertEqual(config.add_keys(keys), ["ctrl-a y"])
        self.assertEqual(keys, {"global": {"ctrl-a y": "tab.new"}})

    def test_add_keys_is_idempotent(self) -> None:
        keys = {}
        config.add_keys(keys)
        self.assertEqual(config.add_keys(keys), [])

    def test_remove_keys_only_removes_ours(self) -> None:
        keys = {"global": {"ctrl-a t": "tab.new"}}
        config.add_keys(keys)
        keys["global"]["ctrl-a u"] = "something.else"
        config.remove_keys(keys)
        self.assertEqual(keys["global"], {"ctrl-a t": "tab.new", "ctrl-a u": "something.else"})


class HeaderTest(unittest.TestCase):
    def test_set_header_points_tab_block_at_mod(self) -> None:
        layout = {"children": [dict(LAYOUT["children"][0]), {"content": {"tab": "active", "pane": {"gap": 8, "header": {"content": {"mod": "pane"}, "height": 30}}}}]}
        self.assertTrue(config.set_header(layout, "accept-header"))
        self.assertEqual(layout["children"][1]["content"]["pane"]["header"]["content"]["mod"], "accept-header")
        self.assertEqual(layout["children"][1]["content"]["pane"]["header"]["height"], 30)

    def test_set_header_adds_header_when_missing(self) -> None:
        layout = {"content": {"tab": "active", "pane": {"gap": 8}}}
        self.assertTrue(config.set_header(layout, "accept-header"))
        self.assertEqual(
            layout["content"]["pane"]["header"],
            {"content": {"mod": "accept-header"}, "height": 30, "position": "top", "reveal": "always"},
        )

    def test_set_header_without_tab_block(self) -> None:
        self.assertFalse(config.set_header({"content": {"mod": "spaces"}}, "accept-header"))


def run_cli(*argv: str, stdin: str = "") -> "tuple[int, str, str]":
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err), mock.patch("sys.stdin", io.StringIO(stdin)):
        code = config.main(list(argv))
    return code, out.getvalue(), err.getvalue()


class CheckKeysTest(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.path = Path(self.dir.name) / "keys.json"

    def test_passes_without_touching_the_file(self) -> None:
        self.path.write_text('{"global": {"ctrl-a t": "tab.new"}}')
        before = self.path.read_bytes()
        self.assertEqual(run_cli("check-keys", str(self.path))[0], 0)
        self.assertEqual(self.path.read_bytes(), before)

    def test_lists_conflicting_keys(self) -> None:
        self.path.write_text('{"global": {"ctrl-a y": "tab.new", "ctrl-a u": "x"}}')
        code, _, err = run_cli("check-keys", str(self.path))
        self.assertEqual(code, 1)
        self.assertIn("ctrl-a y", err)
        self.assertIn("ctrl-a u", err)

    def test_invalid_json_exits_1_with_message(self) -> None:
        self.path.write_text("{not json")
        code, _, err = run_cli("check-keys", str(self.path))
        self.assertEqual(code, 1)
        self.assertIn("not valid JSON", err)
        self.assertIn(str(self.path), err)

    def test_missing_file_exits_1(self) -> None:
        code, _, err = run_cli("check-keys", str(self.path))
        self.assertEqual(code, 1)
        self.assertIn("no such file", err)

    def test_global_section_must_be_an_object(self) -> None:
        self.path.write_text('{"global": null}')
        code, _, err = run_cli("check-keys", str(self.path))
        self.assertEqual(code, 1)
        self.assertIn('"global"', err)

    def test_top_level_must_be_an_object(self) -> None:
        self.path.write_text("[]")
        self.assertEqual(run_cli("check-keys", str(self.path))[0], 1)


class WriteCommandsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.keys = Path(self.dir.name) / "keys.json"
        self.backup = Path(self.dir.name) / "keys.json.accept-backup"
        self.original = '{"global": {"ctrl-a t": "tab.new"}}'
        self.keys.write_text(self.original)

    def test_add_keys_backs_up_once_before_first_write(self) -> None:
        self.assertEqual(run_cli("add-keys", str(self.keys))[0], 0)
        self.assertEqual(self.backup.read_text(), self.original)
        self.assertIn("accept-header.toggle", self.keys.read_text())
        self.keys.write_text('{"global": {"ctrl-a t": "changed"}}')
        run_cli("remove-keys", str(self.keys))
        self.assertEqual(self.backup.read_text(), self.original)

    def test_add_keys_conflict_writes_nothing_and_makes_no_backup(self) -> None:
        self.keys.write_text('{"global": {"ctrl-a y": "tab.new"}}')
        before = self.keys.read_bytes()
        self.assertEqual(run_cli("add-keys", str(self.keys))[0], 1)
        self.assertEqual(self.keys.read_bytes(), before)
        self.assertFalse(self.backup.exists())

    def test_add_keys_twice_is_a_noop_the_second_time(self) -> None:
        run_cli("add-keys", str(self.keys))
        after_first = self.keys.read_bytes()
        self.assertEqual(run_cli("add-keys", str(self.keys))[0], 0)
        self.assertEqual(self.keys.read_bytes(), after_first)

    def test_remove_keys_restores_original_bindings(self) -> None:
        run_cli("add-keys", str(self.keys))
        self.assertEqual(run_cli("remove-keys", str(self.keys))[0], 0)
        self.assertEqual(json.loads(self.keys.read_text()), {"global": {"ctrl-a t": "tab.new"}})

    def test_missing_keys_file_fails_and_is_not_created(self) -> None:
        self.keys.unlink()
        for command in ("add-keys", "remove-keys"):
            code, _, err = run_cli(command, str(self.keys))
            self.assertEqual(code, 1)
            self.assertIn("no such file", err)
        self.assertFalse(self.keys.exists())
        self.assertFalse(self.backup.exists())

    def test_invalid_json_fails_and_leaves_file(self) -> None:
        self.keys.write_text("{oops")
        code, _, err = run_cli("add-keys", str(self.keys))
        self.assertEqual(code, 1)
        self.assertIn("not valid JSON", err)
        self.assertEqual(self.keys.read_text(), "{oops")

    def test_set_header_missing_layout_fails_and_is_not_created(self) -> None:
        layout = Path(self.dir.name) / "main-accept.json"
        code, _, err = run_cli("set-header", str(layout), "accept-header")
        self.assertEqual(code, 1)
        self.assertIn("no such file", err)
        self.assertFalse(layout.exists())

    def test_set_header_rewrites_layout_file(self) -> None:
        layout = Path(self.dir.name) / "main-accept.json"
        layout.write_text('{"content": {"tab": "active", "pane": {}}}')
        self.assertEqual(run_cli("set-header", str(layout), "accept-header")[0], 0)
        self.assertEqual(json.loads(layout.read_text())["content"]["pane"]["header"]["content"], {"mod": "accept-header"})


class StatusTest(unittest.TestCase):
    def test_status_layout_prints_layout(self) -> None:
        code, out, _ = run_cli("status-layout", stdin='{"layout": "main", "errors": []}')
        self.assertEqual((code, out), (0, "main\n"))

    def test_status_layout_rejects_bad_input(self) -> None:
        for stdin in ("", "not json", "[]", '{"errors": []}', '{"layout": 3}'):
            code, out, err = run_cli("status-layout", stdin=stdin)
            self.assertEqual(code, 1, stdin)
            self.assertEqual(out, "")
            self.assertTrue(err, stdin)

    def test_status_errors_silent_when_empty(self) -> None:
        self.assertEqual(run_cli("status-errors", stdin='{"layout": "main", "errors": []}'), (0, "", ""))

    def test_status_errors_prints_each_error_and_exits_1(self) -> None:
        code, out, _ = run_cli("status-errors", stdin='{"errors": ["keys.json: bad", {"file": "x"}]}')
        self.assertEqual(code, 1)
        self.assertIn("keys.json: bad", out)
        self.assertIn('"file": "x"', out)

    def test_status_errors_rejects_invalid_json(self) -> None:
        self.assertEqual(run_cli("status-errors", stdin="nope")[0], 1)


if __name__ == "__main__":
    unittest.main()
