#!/usr/bin/env python3
"""Auto-answer interactive prompts in a herdr-managed agent pane.

Usage:
    herdr-accept-tool <agent-name|pane-id> [options]

Polls the pane screen through the herdr CLI. When a numbered choice dialog
is on screen (Claude Code permission prompt, AskUserQuestion, plan approval,
submit confirmation), it picks one option and presses Enter:

    1. the first option whose label matches --prefer (default: Recommended /
       Khuyến nghị / Đề xuất / Nên chọn)
    2. otherwise the first option whose label starts with Yes / Có / Đồng ý /
       Tiếp tục / Chấp nhận / OK
    3. otherwise option 1

Only the herdr CLI is used; no agent internals are touched. Verified against
herdr 0.9.x and Claude Code 2.1.301 on 2026-10-17.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import List, Optional, Sequence

HERDR = "herdr"
PANE_ID_PATTERN = re.compile(r"[A-Za-z0-9]+:[A-Za-z0-9]+")
OPTION_PATTERN = re.compile(r"^\s*(?P<cursor>❯)?\s*(?P<number>\d+)\.\s+(?P<label>\S.*?)\s*$")
CHECKBOX_PATTERN = re.compile(r"^\[(?P<mark>[ xX✔✓●])\]\s*(?P<text>.*)$")
CURSOR_ONLY_PATTERN = re.compile(r"^\s*❯\s*$")
DEFAULT_PREFER = r"(?i)recommended|khuyến nghị|đề xuất|nên (chọn|dùng)"
YES_PATTERN = re.compile(r"(?i)^(yes|có|đồng ý|tiếp tục|chấp nhận|ok)\b")


@dataclass(frozen=True)
class Option:
    number: int
    label: str
    has_cursor: bool

    @property
    def checkbox(self) -> Optional[bool]:
        """True/False for a multi-select checkbox, None for a plain option."""
        match = CHECKBOX_PATTERN.match(self.label)
        if not match:
            return None
        return match.group("mark") != " "

    @property
    def text(self) -> str:
        match = CHECKBOX_PATTERN.match(self.label)
        return match.group("text") if match else self.label


@dataclass(frozen=True)
class Prompt:
    question: str
    options: Sequence[Option]

    @property
    def cursor_index(self) -> int:
        for index, option in enumerate(self.options):
            if option.has_cursor:
                return index
        return 0

    def fingerprint(self) -> str:
        return self.question + "|" + "|".join(option.label for option in self.options)


class HerdrError(RuntimeError):
    """The herdr CLI refused or failed a request."""


def run_herdr(args: List[str], timeout: float = 5.0) -> str:
    try:
        result = subprocess.run(
            [HERDR] + args, capture_output=True, text=True, timeout=timeout
        )
    except OSError as error:
        raise HerdrError("cannot run herdr: %s" % error) from error
    except subprocess.TimeoutExpired as error:
        raise HerdrError("herdr timed out: %s" % " ".join(args)) from error
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().splitlines()
        raise HerdrError(detail[0] if detail else "herdr exit %d" % result.returncode)
    return result.stdout


def resolve_pane(target: str) -> str:
    """Map an agent name or pane id to the pane id herdr knows right now."""
    try:
        raw = run_herdr(["agent", "get", target])
        pane_id = json.loads(raw)["result"]["agent"]["pane_id"]
        if isinstance(pane_id, str) and PANE_ID_PATTERN.fullmatch(pane_id):
            return pane_id
    except (HerdrError, ValueError, KeyError, TypeError):
        pass
    if PANE_ID_PATTERN.fullmatch(target):
        run_herdr(["pane", "get", target])
        return target
    raise HerdrError("no agent or pane named %r" % target)


def read_screen(pane_id: str, lines: int) -> str:
    return run_herdr(
        ["pane", "read", pane_id, "--source", "visible", "--lines", str(lines)]
    )


def send_keys(pane_id: str, keys: Sequence[str]) -> None:
    run_herdr(["pane", "send-keys", pane_id] + list(keys))


def parse_prompt(screen: str) -> Optional[Prompt]:
    """Find a pending choice dialog at the bottom of the screen.

    A dialog is a numbered list 1..N (N >= 2) whose last item is on screen,
    with the ❯ cursor on one of its items. Description lines and rule lines
    between items are tolerated. A plain numbered list in assistant output has
    no cursor, so it never matches. The input box cursor (❯ alone) is ignored.
    """
    lines = screen.splitlines()
    options: List[Option] = []
    question_cutoff = 0
    expected = None
    for index in range(len(lines) - 1, -1, -1):
        match = OPTION_PATTERN.match(lines[index])
        if not match:
            if options and CURSOR_ONLY_PATTERN.match(lines[index]):
                break
            continue
        number = int(match.group("number"))
        if expected is None:
            expected = number
        if number != expected:
            if options:
                break
            expected = number
        options.insert(
            0,
            Option(number, match.group("label"), match.group("cursor") is not None),
        )
        question_cutoff = index
        expected = number - 1
        if number == 1:
            break
    if len(options) < 2 or options[0].number != 1:
        return None
    if not any(option.has_cursor for option in options):
        return None
    question = ""
    for line in reversed(lines[:question_cutoff]):
        stripped = line.strip()
        if stripped and not set(stripped) <= set("─╌━═-"):
            question = stripped
            break
    return Prompt(question=question, options=tuple(options))


def choose_option(prompt: Prompt, prefer: re.Pattern[str]) -> int:
    for index, option in enumerate(prompt.options):
        if prefer.search(option.text):
            return index
    for index, option in enumerate(prompt.options):
        if YES_PATTERN.match(option.text):
            return index
    return 0


def keys_for(prompt: Prompt, target_index: int) -> List[str]:
    """Keys that confirm the target option.

    Single-select: move the cursor onto it and press Enter. Multi-select
    (checkbox options): Enter only toggles, so tick it when unticked and press
    Tab to advance once it is ticked. Each state has its own fingerprint, so
    the two steps run on consecutive polls.
    """
    target = prompt.options[target_index]
    if target.checkbox is True:
        return ["Tab"]
    delta = target_index - prompt.cursor_index
    moves = ["Down"] * delta if delta > 0 else ["Up"] * (-delta)
    return moves + ["Enter"]


def log(message: str, quiet: bool = False) -> None:
    if quiet:
        return
    stamp = time.strftime("%H:%M:%S")
    sys.stderr.write("[%s] %s\n" % (stamp, message))
    sys.stderr.flush()


def watch(args: argparse.Namespace) -> int:
    prefer = re.compile(args.prefer)
    pane_id = resolve_pane(args.target)
    log("watching pane %s (target %s)" % (pane_id, args.target), args.quiet)
    answered: dict[str, float] = {}
    started = time.monotonic()
    while True:
        if args.timeout and time.monotonic() - started > args.timeout:
            log("timeout reached", args.quiet)
            return 0
        try:
            screen = read_screen(pane_id, args.lines)
        except HerdrError as error:
            log("pane gone: %s" % error, args.quiet)
            return 0
        prompt = parse_prompt(screen)
        if prompt is not None:
            key = prompt.fingerprint()
            last = answered.get(key)
            if last is None or time.monotonic() - last >= args.cooldown:
                index = choose_option(prompt, prefer)
                label = prompt.options[index].label
                keys = keys_for(prompt, index)
                log(
                    "prompt %r -> option %d %r (keys: %s)%s"
                    % (
                        prompt.question[:80],
                        index + 1,
                        label,
                        " ".join(keys),
                        " [dry-run]" if args.dry_run else "",
                    ),
                    args.quiet,
                )
                if not args.dry_run:
                    send_keys(pane_id, keys)
                answered[key] = time.monotonic()
                if args.once:
                    return 0
                time.sleep(args.settle)
                continue
        time.sleep(args.interval)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="herdr-accept-tool",
        description="Auto-answer Yes / Recommended / first option in a herdr agent pane.",
    )
    parser.add_argument("target", help="herdr agent name or pane id (e.g. w26:p42)")
    parser.add_argument("--interval", type=float, default=1.0, help="poll seconds (1.0)")
    parser.add_argument("--settle", type=float, default=1.5, help="pause after answering (1.5)")
    parser.add_argument("--cooldown", type=float, default=10.0, help="seconds before re-answering an identical prompt (10)")
    parser.add_argument("--lines", type=int, default=80, help="screen lines to read (80)")
    parser.add_argument("--timeout", type=float, default=0, help="stop after N seconds, 0 = run until pane closes")
    parser.add_argument("--prefer", default=DEFAULT_PREFER, help="regex for preferred option label")
    parser.add_argument("--once", action="store_true", help="answer one prompt then exit")
    parser.add_argument("--dry-run", action="store_true", help="detect and log, send nothing")
    parser.add_argument("-q", "--quiet", action="store_true", help="no log output")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return watch(args)
    except HerdrError as error:
        sys.stderr.write("error: %s\n" % error)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
