#!/usr/bin/env python3
"""Plugin action entrypoint: arm or disarm auto-accept on the focused pane.

usage: toggle.py [toggle|toggle-permissions|arm|arm-permissions|disarm|disarm-all|status|prune]

Two modes: `toggle` / `arm` answer every dialog (⚡), `toggle-permissions` /
`arm-permissions` answer permission prompts only and leave the agent's
questions on screen (🔐). A toggle on a pane armed in the other mode switches
mode instead of disarming.

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
from herdr_accept_tool import MODE_ALL, MODE_PERMISSIONS, HerdrError  # noqa: E402

SUPERVISOR_HINT = "supervisor not running: run scripts/install-launchd.sh"
ACTION_MODES = {
    "toggle": MODE_ALL,
    "arm": MODE_ALL,
    "toggle-permissions": MODE_PERMISSIONS,
    "arm-permissions": MODE_PERMISSIONS,
}


def arm(pane_id: str, mode: str) -> None:
    pane = herdr.get_pane(pane_id)
    # Re-arming (mode switch) must keep the label from before the first arm,
    # not the currently marked one.
    previous = state.load_state().get(pane_id)
    label_before = previous.label_before if previous else pane.get("label")
    entry = state.Armed(
        pane_id=pane_id,
        cwd=pane.get("cwd") or "",
        armed_at=time.time(),
        ttl=state.DEFAULT_TTL_SECONDS,
        label_before=label_before,
        mode=mode,
    )
    state.arm_pane(entry)
    herdr.rename_pane(pane_id, state.marked_label(label_before, pane.get("agent") or "auto", mode))
    until = time.strftime("%H:%M", time.localtime(entry.expires_at))
    body = "pane %s · until %s" % (pane_id, until)
    if not state.supervisor_alive():
        body += "\n" + SUPERVISOR_HINT
    herdr.notify("auto-accept ON (%s)" % state.MODE_TITLES[mode], body)


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
        "%s %s until %s"
        % (
            pane_id,
            state.MODE_TITLES.get(entry.mode, entry.mode),
            time.strftime("%H:%M", time.localtime(entry.expires_at)),
        )
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
    current = state.load_state().get(pane_id)
    mode = ACTION_MODES.get(action)
    if action == "disarm":
        disarm(pane_id)
    elif mode is None:
        sys.stderr.write("unknown action %r\n" % action)
        return 2
    elif action.startswith("toggle") and current is not None and current.mode == mode:
        disarm(pane_id)
    else:
        arm(pane_id, mode)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except HerdrError as error:
        herdr.notify("auto-accept error", str(error))
        sys.stderr.write("error: %s\n" % error)
        sys.exit(2)
