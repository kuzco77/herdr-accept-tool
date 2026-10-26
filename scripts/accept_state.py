"""Armed-pane state shared by the plugin actions and the supervisor.

State lives in one JSON file under ~/.local/state/herdr-accept-tool (override
with HERDR_ACCEPT_STATE_DIR). Both writers use atomic replace and re-read the
file before a partial update, so an action arming a pane cannot be lost by a
supervisor cycle dropping another one at the same time.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Iterable, Optional

STATE_DIR = Path(
    os.environ.get("HERDR_ACCEPT_STATE_DIR") or "~/.local/state/herdr-accept-tool"
).expanduser()
STATE_FILE = STATE_DIR / "armed.json"
HEARTBEAT_FILE = STATE_DIR / "supervisor.heartbeat"
LOG_FILE = STATE_DIR / "supervisor.log"
DEFAULT_TTL_SECONDS = float(os.environ.get("HERDR_ACCEPT_TTL") or 12 * 3600)
LABEL_MARKER = "⚡ "


@dataclass
class Armed:
    pane_id: str
    cwd: str
    armed_at: float
    ttl: float
    label_before: Optional[str]

    @property
    def expires_at(self) -> float:
        return self.armed_at + self.ttl

    def expired(self, now: Optional[float] = None) -> bool:
        return self.ttl > 0 and (now if now is not None else time.time()) >= self.expires_at


def load_state() -> Dict[str, Armed]:
    try:
        raw = json.loads(STATE_FILE.read_text())
    except (OSError, ValueError):
        return {}
    state: Dict[str, Armed] = {}
    for pane_id, entry in raw.items():
        try:
            state[pane_id] = Armed(**entry)
        except TypeError:
            continue
    return state


def save_state(state: Dict[str, Armed]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({k: asdict(v) for k, v in state.items()}, indent=1))
    os.replace(tmp, STATE_FILE)


def arm_pane(entry: Armed) -> None:
    state = load_state()
    state[entry.pane_id] = entry
    save_state(state)


def remove_panes(pane_ids: Iterable[str]) -> Dict[str, Armed]:
    """Remove the given panes, re-reading the file first. Returns what was removed."""
    state = load_state()
    removed = {pane_id: state.pop(pane_id) for pane_id in pane_ids if pane_id in state}
    if removed:
        save_state(state)
    return removed


def touch_heartbeat() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    HEARTBEAT_FILE.touch()


def supervisor_alive(max_age: float = 15.0) -> bool:
    try:
        return time.time() - HEARTBEAT_FILE.stat().st_mtime < max_age
    except OSError:
        return False


def marked_label(label: Optional[str], fallback: str) -> str:
    base = label or fallback
    return base if base.startswith(LABEL_MARKER) else LABEL_MARKER + base


def unmarked_label(label: Optional[str]) -> Optional[str]:
    if label and label.startswith(LABEL_MARKER):
        return label[len(LABEL_MARKER):]
    return label
