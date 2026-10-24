#!/usr/bin/env python3
"""Plugin action entrypoint: arm or disarm auto-accept on the focused pane.

usage: toggle.py [toggle|arm|disarm|disarm-all|status|prune]

The action only edits the armed-pane state file and the pane label. Answering
is done by scripts/supervisor.py, which is reported in the toast when it is
not running.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import accept_state as state  # noqa: E402
import herdr_api as herdr  # noqa: E402
from herdr_accept_tool import HerdrError  # noqa: E402

SUPERVISOR_HINT = "supervisor not running: run scripts/install-launchd.sh"


def arm(pane_id: str) -> None:
    pane = herdr.get_pane(pane_id)
    label_before = pane.get("label")
    entry = state.Armed(
        pane_id=pane_id,
        cwd=pane.get("cwd") or "",
        armed_at=time.time(),
        ttl=state.DEFAULT_TTL_SECONDS,
        label_before=label_before,
    )
    state.arm_pane(entry)
    herdr.rename_pane(pane_id, state.marked_label(label_before, pane.get("agent") or "auto"))
    until = time.strftime("%H:%M", time.localtime(entry.expires_at))
    body = "pane %s · until %s" % (pane_id, until)
    if not state.supervisor_alive():
        body += "\n" + SUPERVISOR_HINT
    herdr.notify("auto-accept ON", body)


def disarm(pane_id: str, reason: str = "") -> None:
    removed = state.remove_panes([pane_id])
    entry = removed.get(pane_id)
    if entry is not None:
        try:
            herdr.rename_pane(pane_id, state.unmarked_label(entry.label_before))
        except HerdrError:
            pass
    body = "pane %s" % pane_id + (" · " + reason if reason else "")
    herdr.notify("auto-accept OFF", body)


def disarm_all() -> None:
    armed = state.load_state()
    for pane_id in list(armed):
        disarm(pane_id)
    if not armed:
        herdr.notify("auto-accept", "no armed panes")


def status() -> None:
    armed = state.load_state()
    if not armed:
        herdr.notify("auto-accept", "no armed panes")
        return
    lines = [
        "%s until %s" % (pane_id, time.strftime("%H:%M", time.localtime(entry.expires_at)))
        for pane_id, entry in sorted(armed.items())
    ]
    if not state.supervisor_alive():
        lines.append(SUPERVISOR_HINT)
    herdr.notify("auto-accept: %d armed" % len(armed), "\n".join(lines))


def prune() -> None:
    """Drop armed panes that no longer exist (pane.closed event hook)."""
    armed = state.load_state()
    if not armed:
        return
    live = herdr.list_panes()
    state.remove_panes([pane_id for pane_id in armed if pane_id not in live])


def main(argv: list) -> int:
    action = argv[0] if argv else "toggle"
    if action == "disarm-all":
        disarm_all()
        return 0
    if action == "status":
        status()
        return 0
    if action == "prune":
        prune()
        return 0
    pane_id = herdr.current_pane_id()
    armed = pane_id in state.load_state()
    if action == "arm" or (action == "toggle" and not armed):
        arm(pane_id)
    elif action == "disarm" or (action == "toggle" and armed):
        disarm(pane_id)
    else:
        sys.stderr.write("unknown action %r\n" % action)
        return 2
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except HerdrError as error:
        herdr.notify("auto-accept error", str(error))
        sys.stderr.write("error: %s\n" % error)
        sys.exit(2)
