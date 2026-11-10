"""herdr-core (hc) calls the supervisor needs beyond reading screens and pressing keys.

A herdr-core terminal is armed by two labels on the terminal itself:
`accept` (`all` or `permissions`) and `accept.at` (epoch seconds). The labels
go away with the terminal, so there is nothing to prune.
"""

from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path
from typing import Dict, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import accept_state as state  # noqa: E402
from herdr_accept_tool import MODES, HerdrError, run_hc  # noqa: E402

LABEL_MODE = "accept"
LABEL_AT = "accept.at"


def _json(raw: str) -> dict:
    try:
        data = json.loads(raw)
    except ValueError as error:
        raise HerdrError("unexpected hc output: %s" % raw[:80]) from error
    if not isinstance(data, dict):
        raise HerdrError("unexpected hc output: %s" % raw[:80])
    return data


def armed_terminals() -> Dict[str, dict]:
    """Address -> `hc get` record for every live terminal armed in any mode."""
    found: Dict[str, dict] = {}
    for mode in MODES:
        listing = _json(run_hc(["ls", "--json", "--label", "%s=%s" % (LABEL_MODE, mode)]))
        for terminal in listing.get("terminals") or []:
            address = terminal.get("address") if isinstance(terminal, dict) else None
            if not isinstance(address, str):
                continue
            try:
                found[address] = _json(run_hc(["get", address]))
            except HerdrError:
                continue  # ended between ls and get; it is gone with its labels
    return found


def armed_entry(address: str, record: dict, ttl: float = state.DEFAULT_TTL_SECONDS) -> state.Armed:
    labels = record.get("labels")
    if not isinstance(labels, dict):
        labels = {}
    try:
        armed_at = float(labels.get(LABEL_AT, ""))
    except (ValueError, TypeError):
        armed_at = 0.0
    if not math.isfinite(armed_at):
        armed_at = 0.0  # nan/inf would never expire, leaving the terminal armed forever
    return state.Armed(
        pane_id=address,
        cwd=record.get("cwd") or "",
        armed_at=armed_at,
        ttl=ttl,
        label_before=None,
        mode=labels.get(LABEL_MODE) or MODES[0],
    )


def process_name(record: Optional[dict]) -> Optional[str]:
    """Basename of the foreground program, e.g. claude, agy, zsh."""
    foreground = (record or {}).get("foreground") or {}
    argv = foreground.get("argv") or []
    if not argv:
        return None
    return os.path.basename(argv[0]).lstrip("-") or None


def disarm(address: str) -> None:
    run_hc(["label", address, "%s=" % LABEL_MODE, "%s=" % LABEL_AT])
