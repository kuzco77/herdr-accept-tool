"""keys.json merging and layout header edits for the herdr-app install."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
