"""Thin wrappers over the herdr CLI calls the plugin needs beyond the core tool."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Dict, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from herdr_accept_tool import HerdrError, run_herdr  # noqa: E402


def _result(raw: str) -> dict:
    try:
        return json.loads(raw)["result"]
    except (ValueError, KeyError, TypeError) as error:
        raise HerdrError("unexpected herdr output: %s" % raw[:80]) from error


def list_panes() -> Dict[str, dict]:
    result = _result(run_herdr(["pane", "list"]))
    panes = result.get("panes") if isinstance(result, dict) else result
    return {pane["pane_id"]: pane for pane in panes or []}


def get_pane(pane_id: str) -> dict:
    return _result(run_herdr(["pane", "get", pane_id]))["pane"]


def current_pane_id() -> str:
    env_pane = os.environ.get("HERDR_PANE_ID")
    if env_pane:
        return env_pane
    context = os.environ.get("HERDR_PLUGIN_CONTEXT_JSON")
    if context:
        try:
            data = json.loads(context)
            pane = data.get("focused_pane_id") or data.get("pane_id") or (data.get("pane") or {}).get("pane_id")
            if pane:
                return pane
        except ValueError:
            pass
    return _result(run_herdr(["pane", "current"]))["pane"]["pane_id"]


def pane_process_name(pane_id: str) -> Optional[str]:
    """Basename of the foreground process group leader, e.g. claude, agy, zsh."""
    try:
        info = _result(run_herdr(["pane", "process-info", "--pane", pane_id]))["process_info"]
    except (HerdrError, KeyError):
        return None
    processes = info.get("foreground_processes") or []
    leader = next(
        (p for p in processes if p.get("pid") == info.get("foreground_process_group_id")),
        None,
    )
    process = leader or (processes[-1] if processes else None)
    if not process:
        return None
    argv0 = process.get("argv0") or process.get("name") or ""
    return os.path.basename(argv0).lstrip("-") or None


def rename_pane(pane_id: str, label: Optional[str]) -> None:
    if label:
        run_herdr(["pane", "rename", pane_id, label])
    else:
        run_herdr(["pane", "rename", pane_id, "--clear"])


def notify(title: str, body: str = "", sound: str = "none") -> None:
    try:
        run_herdr(
            ["notification", "show", title, "--body", body, "--position", "top-right", "--sound", sound]
        )
    except HerdrError:
        pass
