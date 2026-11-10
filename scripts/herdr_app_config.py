#!/usr/bin/env python3
"""Edit herdr-app config files for the accept-header mod.

usage:
  herdr_app_config.py check-keys <keys.json>    exit 1 when keys.json is unreadable or a key is taken
  herdr_app_config.py add-keys <keys.json>      bind ctrl-a y / u / shift-y (refuses conflicts)
  herdr_app_config.py remove-keys <keys.json>   unbind them (only if still ours)
  herdr_app_config.py set-header <layout.json> <mod>   frame panes with <mod> as header
  herdr_app_config.py status-layout             print "layout" from `herdr-app status` JSON on stdin
  herdr_app_config.py status-errors             print "errors" from that JSON; exit 1 when any

keys.json is copied once to keys.json.accept-backup before the first write.
Missing files are an error: nothing is created.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path
from typing import Dict, List

KEYS: Dict[str, str] = {
    "ctrl-a y": "accept-header.toggle",
    "ctrl-a u": "accept-header.toggle-permissions",
    "ctrl-a shift-y": "accept-header.disarm-all",
}
DEFAULT_HEADER = {"height": 30, "position": "top", "reveal": "always"}


def _bound(keys: dict) -> dict:
    bound = keys.setdefault("global", {})
    if not isinstance(bound, dict):
        raise ValueError('"global" must be an object')
    return bound


def add_keys(keys: dict) -> List[str]:
    bound = _bound(keys)
    conflicts = [key for key, command in KEYS.items() if key in bound and bound[key] != command]
    if not conflicts:
        bound.update(KEYS)
    return conflicts


def remove_keys(keys: dict) -> None:
    bound = _bound(keys)
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


class ConfigError(Exception):
    """A file problem worth a one-line message, not a traceback."""


def _load(path: Path) -> dict:
    if not path.is_file():
        raise ConfigError("%s: no such file" % path)
    try:
        data = json.loads(path.read_text())
    except ValueError as exc:
        raise ConfigError("%s: not valid JSON (%s)" % (path, exc))
    if not isinstance(data, dict):
        raise ConfigError("%s: top level must be a JSON object" % path)
    return data


def _save(path: Path, data: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    os.replace(tmp, path)


def _save_keys(path: Path, before: dict, after: dict) -> None:
    if after == before:
        return
    backup = path.with_name(path.name + ".accept-backup")
    if not backup.exists():
        shutil.copy2(path, backup)
    _save(path, after)


def _stdin_json() -> dict:
    try:
        data = json.load(sys.stdin)
    except ValueError as exc:
        raise ConfigError("stdin: not valid JSON (%s)" % exc)
    if not isinstance(data, dict):
        raise ConfigError("stdin: expected a JSON object")
    return data


def _check_keys(path: Path) -> int:
    conflicts = add_keys(_load(path))
    if conflicts:
        sys.stderr.write("%s: already bound to something else: %s\n" % (path, ", ".join(conflicts)))
        return 1
    return 0


def _edit_keys(command: str, path: Path) -> int:
    before = _load(path)
    keys = json.loads(json.dumps(before))
    if command == "remove-keys":
        remove_keys(keys)
    else:
        conflicts = add_keys(keys)
        if conflicts:
            sys.stderr.write("%s: already bound to something else: %s\n" % (path, ", ".join(conflicts)))
            return 1
    _save_keys(path, before, keys)
    return 0


def _set_header(path: Path, mod: str) -> int:
    layout = _load(path)
    if not set_header(layout, mod):
        sys.stderr.write("no tab block in %s\n" % path)
        return 1
    _save(path, layout)
    return 0


def _status_layout() -> int:
    layout = _stdin_json().get("layout")
    if not isinstance(layout, str) or not layout:
        raise ConfigError("status has no layout name")
    print(layout)
    return 0


def _status_errors() -> int:
    errors = _stdin_json().get("errors") or []
    if not isinstance(errors, list):
        errors = [errors]
    for error in errors:
        print(error if isinstance(error, str) else json.dumps(error, ensure_ascii=False))
    return 1 if errors else 0


def main(argv: List[str]) -> int:
    try:
        if len(argv) == 2 and argv[0] == "check-keys":
            return _check_keys(Path(argv[1]))
        if len(argv) == 2 and argv[0] in ("add-keys", "remove-keys"):
            return _edit_keys(argv[0], Path(argv[1]))
        if len(argv) == 3 and argv[0] == "set-header":
            return _set_header(Path(argv[1]), argv[2])
        if argv == ["status-layout"]:
            return _status_layout()
        if argv == ["status-errors"]:
            return _status_errors()
    except (ConfigError, ValueError) as exc:
        sys.stderr.write("%s\n" % exc)
        return 1
    sys.stderr.write(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
