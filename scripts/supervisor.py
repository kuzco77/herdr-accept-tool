#!/usr/bin/env python3
"""Long-running supervisor: answers prompts on every armed pane and terminal.

Runs outside herdr (launchd on macOS, see install-launchd.sh) so it survives
herdr restarts and reboots. Two sources are polled each cycle: herdr TUI panes
armed in armed.json, and herdr-core terminals armed with the `accept` label.
For each, it drops entries that closed or whose TTL expired, skips targets
whose foreground process is not a known agent (a pane restored as a plain
shell gets no key presses), and answers whatever dialog the rest show.

When a source is unreachable it backs off on its own and retries; the other
source keeps running, and state is never touched for the unreachable one.

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
from typing import Callable, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

import accept_state as state  # noqa: E402
import core_api  # noqa: E402
import herdr_api as herdr  # noqa: E402
from herdr_accept_tool import (  # noqa: E402
    DEFAULT_PREFER,
    Answerer,
    Backend,
    CoreBackend,
    HerdrError,
    TuiBackend,
    log,
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


Snapshot = Tuple[Dict[str, state.Armed], Dict[str, dict], Callable[[str], Optional[str]]]


class TuiSource:
    """herdr TUI panes armed through the plugin actions (armed.json)."""

    name = "tui"

    def __init__(self) -> None:
        self.backend: Backend = TuiBackend()

    def snapshot(self) -> Snapshot:
        armed = state.load_state()
        if not armed:
            return {}, {}, lambda _pane: None
        return armed, herdr.list_panes(), herdr.pane_process_name

    def disarm(self, target: str, reason: str, live: bool) -> None:
        entry = state.remove_panes([target]).get(target)
        if live and entry is not None:
            try:
                herdr.rename_pane(target, state.unmarked_label(entry.label_before))
            except HerdrError:
                pass
            herdr.notify("auto-accept OFF", "pane %s · %s" % (target, reason))


class CoreSource:
    """herdr-core terminals armed with the `accept` label (herdr-app header mod)."""

    name = "core"

    def __init__(self) -> None:
        self.backend: Backend = CoreBackend()

    def snapshot(self) -> Snapshot:
        records = core_api.armed_terminals()
        armed = {address: core_api.armed_entry(address, record) for address, record in records.items()}
        return armed, records, lambda address: core_api.process_name(records.get(address))

    def disarm(self, target: str, reason: str, live: bool) -> None:
        if not live:
            return
        try:
            core_api.disarm(target)
        except HerdrError as error:
            log("%s disarm failed: %s" % (target, error))


class Supervisor:
    def __init__(self, args: argparse.Namespace, sources: Optional[list] = None) -> None:
        self.args = args
        self.prefer = re.compile(args.prefer)
        self.answerers: Dict[str, Answerer] = {}
        self.idle_reported: Dict[str, str] = {}
        self.sources = sources if sources is not None else [TuiSource(), CoreSource()]
        self.retry: Dict[str, Tuple[float, float]] = {}

    def answerer_for(self, pane_id: str, mode: str, backend: Optional[Backend] = None) -> Answerer:
        """One Answerer per target; replaced when it is re-armed in another mode."""
        answerer = self.answerers.get(pane_id)
        if answerer is None or answerer.mode != mode:
            answerer = Answerer(
                pane_id=pane_id,
                prefer=self.prefer,
                cooldown=self.args.cooldown,
                dry_run=self.args.dry_run,
                mode=mode,
                backend=backend or TuiBackend(),
            )
            self.answerers[pane_id] = answerer
        return answerer

    def drop(self, source, pane_id: str, reason: str, live: bool) -> None:
        source.disarm(pane_id, reason, live)
        self.answerers.pop(pane_id, None)
        self.idle_reported.pop(pane_id, None)
        log("%s disarmed: %s" % (pane_id, reason))

    def back_off(self, source, now: float, problem: str) -> None:
        _retry_at, backoff = self.retry.get(source.name, (0.0, BACKOFF_MIN))
        log("%s %s, retry in %.0fs" % (source.name, problem, backoff))
        self.retry[source.name] = (now + backoff, min(backoff * 2, BACKOFF_MAX))

    def run_source(self, source, now: float) -> bool:
        """One pass over one source. Returns True when any of its targets is active."""
        armed, live, process_of = source.snapshot()
        if not armed:
            return False
        plan = plan_cycle(armed, live, now, process_of)
        for pane_id, reason in plan.dropped.items():
            self.drop(source, pane_id, reason, live=pane_id in live)
        for pane_id, process in plan.idle.items():
            if self.idle_reported.get(pane_id) != process:
                log("%s idle: foreground is %s, waiting for an agent" % (pane_id, process))
                self.idle_reported[pane_id] = process
        for pane_id in plan.active:
            self.idle_reported.pop(pane_id, None)
            try:
                screen = source.backend.read_screen(pane_id, SCREEN_LINES)
                answerer = self.answerer_for(pane_id, armed[pane_id].mode, source.backend)
                if answerer.answer(screen):
                    time.sleep(self.args.settle)
            except HerdrError as error:
                log("%s read or answer failed: %s" % (pane_id, error))
        return bool(plan.active)

    def cycle(self) -> bool:
        """One pass over every source. Returns True when any target is active.

        A source that raises is put into backoff; the others still run.
        """
        state.touch_heartbeat()
        now = time.time()
        any_active = False
        for source in self.sources:
            retry_at, _backoff = self.retry.get(source.name, (0.0, BACKOFF_MIN))
            if now < retry_at:
                continue
            try:
                any_active = self.run_source(source, now) or any_active
            except HerdrError as error:
                self.back_off(source, now, "unavailable (%s)" % error)
            except Exception as error:
                self.back_off(source, now, "failed (%s: %s)" % (type(error).__name__, error))
            else:
                self.retry.pop(source.name, None)
        return any_active

    def run(self) -> int:
        log("supervisor started, sources %s, state %s" % (
            ", ".join(source.name for source in self.sources), state.STATE_FILE))
        while True:
            active = self.cycle()
            if self.args.once:
                return 0
            time.sleep(self.args.interval if active else self.args.idle_interval)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Answer prompts on every armed herdr pane and herdr-core terminal.")
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
