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
from herdr_accept_tool import MODES, HerdrError, log, run_hc  # noqa: E402

LABEL_MODE = "accept"
LABEL_AT = "accept.at"

# What was last logged per address ("remote" or the get error), so a condition that
# lasts is logged once, not on every cycle. Pruned to the addresses seen in a pass.
_reported: Dict[str, str] = {}


def remote_enabled() -> bool:
    return os.environ.get("HERDR_ACCEPT_REMOTE") == "1"


def is_remote(address: str) -> bool:
    """Remote herdr-core terminals are addressed `machine/tN`."""
    return "/" in address


def _log_once(address: str, key: str, message: str) -> None:
    if _reported.get(address) != key:
        _reported[address] = key
        log(message)


def _json(raw: str) -> dict:
    try:
        data = json.loads(raw)
    except ValueError as error:
        raise HerdrError("unexpected hc output: %s" % raw[:80]) from error
    if not isinstance(data, dict):
        raise HerdrError("unexpected hc output: %s" % raw[:80])
    return data


def armed_terminals() -> Dict[str, dict]:
    """Address -> `hc get` record for every live terminal armed in a known mode.

    Remote terminals (`machine/tN`) are skipped unless HERDR_ACCEPT_REMOTE=1. So is
    a terminal whose `accept` label is missing or not in MODES: it is never read as "all".
    """
    found: Dict[str, dict] = {}
    seen = set()
    for mode in MODES:
        listing = _json(run_hc(["ls", "--json", "--label", "%s=%s" % (LABEL_MODE, mode)]))
        for terminal in listing.get("terminals") or []:
            address = terminal.get("address") if isinstance(terminal, dict) else None
            if not isinstance(address, str):
                continue
            if is_remote(address) and not remote_enabled():
                seen.add(address)
                _log_once(address, "remote", "%s skipped: remote terminals are not supported (HERDR_ACCEPT_REMOTE=1 enables them)" % address)
                continue
            try:
                record = _json(run_hc(["get", address]))
            except HerdrError as error:
                seen.add(address)
                _log_once(address, "get: %s" % error, "%s get failed, skipped this cycle: %s" % (address, error))
                continue
            labels = record.get("labels")
            if not isinstance(labels, dict) or labels.get(LABEL_MODE) not in MODES:
                continue  # label gone since ls, or hand-set to something unknown
            found[address] = record
    for address in list(_reported):
        if address not in seen:
            del _reported[address]
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
        mode=labels.get(LABEL_MODE) or "",
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
