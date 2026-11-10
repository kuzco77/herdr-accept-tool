#!/usr/bin/env python3
"""Edit herdr-app config files for the accept-header mod.

usage:
  herdr_app_config.py add-keys <keys.json>      bind ctrl-a y / u / shift-y (refuses conflicts)
  herdr_app_config.py remove-keys <keys.json>   unbind them (only if still ours)
  herdr_app_config.py set-header <layout.json> <mod>   frame panes with <mod> as header
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Dict, List

KEYS: Dict[str, str] = {
    "ctrl-a y": "accept-header.toggle",
    "ctrl-a u": "accept-header.toggle-permissions",
    "ctrl-a shift-y": "accept-header.disarm-all",
}
DEFAULT_HEADER = {"height": 30, "position": "top", "reveal": "always"}


def add_keys(keys: dict) -> List[str]:
    bound = keys.setdefault("global", {})
    conflicts = [key for key, command in KEYS.items() if key in bound and bound[key] != command]
    if not conflicts:
        bound.update(KEYS)
    return conflicts


def remove_keys(keys: dict) -> None:
    bound = keys.get("global") or {}
    for key, command in KEYS.items():
        if bound.get(key) == command:
            del bound[key]


def set_header(node, mod: str) -> bool:
    """Point every `"tab": "active"` block's pane header at `mod`. True when one was found."""
    found = False
    if isinstance(node, dict):
        if node.get("tab") == "active":
            pane = node.setdefault("pane", {})
            header = pane.setdefault("header", dict(DEFAULT_HEADER))
            header["content"] = {"mod": mod}
            found = True
        for value in node.values():
            found = set_header(value, mod) or found
    elif isinstance(node, list):
        for value in node:
            found = set_header(value, mod) or found
    return found


def _load(path: Path) -> dict:
    return json.loads(path.read_text()) if path.exists() else {}


def _save(path: Path, data: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    os.replace(tmp, path)


def main(argv: List[str]) -> int:
    if len(argv) >= 2 and argv[0] in ("add-keys", "remove-keys"):
        path = Path(argv[1])
        keys = _load(path)
        if argv[0] == "remove-keys":
            remove_keys(keys)
        else:
            conflicts = add_keys(keys)
            if conflicts:
                sys.stderr.write("already bound to something else: %s\n" % ", ".join(conflicts))
                return 1
        _save(path, keys)
        return 0
    if len(argv) == 3 and argv[0] == "set-header":
        path = Path(argv[1])
        layout = _load(path)
        if not set_header(layout, argv[2]):
            sys.stderr.write("no tab block in %s\n" % path)
            return 1
        _save(path, layout)
        return 0
    sys.stderr.write(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
