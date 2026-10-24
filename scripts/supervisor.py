#!/usr/bin/env python3
"""Long-running supervisor: answers prompts on every armed pane.

Runs outside herdr (launchd on macOS, see install-launchd.sh) so it survives
herdr restarts and reboots. Each cycle it re-reads the armed-pane state file,
drops panes that closed or whose TTL expired, skips panes whose foreground
process is not a known agent (a pane restored as a plain shell gets no key
presses), and answers whatever dialog the remaining panes show.

When the herdr socket is down it backs off and retries; state is never
touched in that case.

usage: supervisor.py [--interval S] [--idle-interval S] [--dry-run] [--once]
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

import accept_state as state  # noqa: E402
import herdr_api as herdr  # noqa: E402
from herdr_accept_tool import (  # noqa: E402
    DEFAULT_PREFER,
    Answerer,
    HerdrError,
    log,
    read_screen,
)

AGENT_PROCESSES = tuple(
    name.strip()
    for name in (os.environ.get("HERDR_ACCEPT_AGENTS") or "claude,agy,antigravity").split(",")
    if name.strip()
)
SCREEN_LINES = 80
BACKOFF_MIN = 5.0
BACKOFF_MAX = 60.0


@dataclass
class CyclePlan:
    active: List[str] = field(default_factory=list)
    idle: Dict[str, str] = field(default_factory=dict)
    dropped: Dict[str, str] = field(default_factory=dict)


def plan_cycle(
    armed: Dict[str, state.Armed],
    live_panes: Dict[str, dict],
    now: float,
    process_of: Callable[[str], Optional[str]],
    agents: tuple = AGENT_PROCESSES,
) -> CyclePlan:
    """Decide what to do with each armed pane this cycle. Pure, for tests."""
    plan = CyclePlan()
    for pane_id, entry in armed.items():
        if pane_id not in live_panes:
            plan.dropped[pane_id] = "pane closed"
        elif entry.expired(now):
            plan.dropped[pane_id] = "ttl expired"
        else:
            process = process_of(pane_id)
            if process in agents:
                plan.active.append(pane_id)
            else:
                plan.idle[pane_id] = process or "no process"
    return plan


class Supervisor:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.prefer = re.compile(args.prefer)
        self.answerers: Dict[str, Answerer] = {}
        self.idle_reported: Dict[str, str] = {}
        self.backoff = BACKOFF_MIN

    def answerer_for(self, pane_id: str) -> Answerer:
        answerer = self.answerers.get(pane_id)
        if answerer is None:
            answerer = Answerer(
                pane_id=pane_id,
                prefer=self.prefer,
                cooldown=self.args.cooldown,
                dry_run=self.args.dry_run,
            )
            self.answerers[pane_id] = answerer
        return answerer

    def drop(self, pane_id: str, reason: str, live: bool) -> None:
        removed = state.remove_panes([pane_id])
        self.answerers.pop(pane_id, None)
        self.idle_reported.pop(pane_id, None)
        log("%s disarmed: %s" % (pane_id, reason))
        entry = removed.get(pane_id)
        if live and entry is not None:
            try:
                herdr.rename_pane(pane_id, state.unmarked_label(entry.label_before))
            except HerdrError:
                pass
            herdr.notify("auto-accept OFF", "pane %s · %s" % (pane_id, reason))

    def cycle(self) -> bool:
        """One pass over the armed panes. Returns True when any pane is active."""
        state.touch_heartbeat()
        armed = state.load_state()
        if not armed:
            return False
        try:
            live = herdr.list_panes()
        except HerdrError as error:
            log("herdr unavailable (%s), retry in %.0fs" % (error, self.backoff))
            time.sleep(self.backoff)
            self.backoff = min(self.backoff * 2, BACKOFF_MAX)
            return False
        self.backoff = BACKOFF_MIN
        plan = plan_cycle(armed, live, time.time(), herdr.pane_process_name)
        for pane_id, reason in plan.dropped.items():
            self.drop(pane_id, reason, live=pane_id in live)
        for pane_id, process in plan.idle.items():
            if self.idle_reported.get(pane_id) != process:
                log("%s idle: foreground is %s, waiting for an agent" % (pane_id, process))
                self.idle_reported[pane_id] = process
        for pane_id in plan.active:
            self.idle_reported.pop(pane_id, None)
            try:
                screen = read_screen(pane_id, SCREEN_LINES)
            except HerdrError as error:
                log("%s read failed: %s" % (pane_id, error))
                continue
            if self.answerer_for(pane_id).answer(screen):
                time.sleep(self.args.settle)
        return bool(plan.active)

    def run(self) -> int:
        log("supervisor started, state %s" % state.STATE_FILE)
        while True:
            active = self.cycle()
            if self.args.once:
                return 0
            time.sleep(self.args.interval if active else self.args.idle_interval)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Answer prompts on every armed herdr pane.")
    parser.add_argument("--interval", type=float, default=1.0, help="poll seconds while a pane is active (1.0)")
    parser.add_argument("--idle-interval", type=float, default=3.0, help="poll seconds while nothing is armed (3.0)")
    parser.add_argument("--settle", type=float, default=1.5, help="pause after answering (1.5)")
    parser.add_argument("--cooldown", type=float, default=10.0, help="seconds before re-answering an identical prompt (10)")
    parser.add_argument("--prefer", default=DEFAULT_PREFER, help="regex for preferred option label")
    parser.add_argument("--once", action="store_true", help="run one cycle and exit")
    parser.add_argument("--dry-run", action="store_true", help="detect and log, send nothing")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return Supervisor(args).run()
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
