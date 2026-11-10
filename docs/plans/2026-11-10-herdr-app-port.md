# herdr-app Port Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use `subagent-parallel-execution` (recommended) or inline execution via `finishing-execution` to implement task-by-task. Steps use `- [ ]` checkboxes.

**Goal:** Arm herdr-core terminals for auto-accept from the Herdr desktop app (`ctrl-a y` / `ctrl-a u` / `ctrl-a shift-y`, a `⚡` / `🔐` marker and the terminal address in each pane header) and answer their prompts from the existing launchd supervisor, while herdr TUI panes keep working as today.

**Architecture:** The prompt parser stays in Python. Screen reads and key presses go through a `Backend` (`TuiBackend` for `herdr`, `CoreBackend` for `hc`). Arming state for herdr-core lives on the terminal as labels `accept` / `accept.at`; the supervisor polls a TUI source (`armed.json`) and a core source (`hc ls --label`) with independent backoff. A herdr-app mod `accept-header`, a clone of the shipped `pane` header, writes the labels and draws the marker.

**Tech Stack:** Python 3.9+ stdlib (`unittest`), herdr-app mods (gpui-kit JavaScript, ES modules), Node 26 `node:test` for the mod's pure logic, bash.

Spec: `docs/specs/2026-11-10-herdr-app-port-design.md` (approved 2026-11-10, Plannotator `pn-f35b21`).

## Global Constraints

- Python: stdlib only, 3.9+ syntax (`from __future__ import annotations`, `typing.Dict/List/Optional`). No new dependencies.
- JavaScript: no dependencies. `state.js` imports nothing so Node can test it; only `main.js` imports `gpui-kit`, `gpui-base`, `herdr`.
- herdr TUI behaviour must not change: same `armed.json` format, same `⚡ ` / `🔐 ` pane-label prefixes, same plugin actions.
- All 49 existing tests stay green after every task: `python3 -m unittest discover -s tests` → `OK`.
- Core labels: `accept` = `all` | `permissions`; `accept.at` = integer epoch seconds. Remove with `hc label <t> accept= accept.at=`.
- TTL: `HERDR_ACCEPT_TTL` seconds, default `12 * 3600`; applied by the supervisor only.
- Heartbeat: `~/.local/state/herdr-accept-tool/supervisor.heartbeat`; content is epoch seconds; stale after 15 s.
- herdr-core CLI: `HERDR_CORE_BIN`, else `hc` on `PATH`, else `herdr-core`. `hc` errors are JSON on stdout `{"error": {"message": …}}` with a nonzero exit.
- Keys (`~/.config/herdr-app/keys.json`, section `global`): `ctrl-a y` → `accept-header.toggle`, `ctrl-a u` → `accept-header.toggle-permissions`, `ctrl-a shift-y` → `accept-header.disarm-all`.
- Known agent processes: `claude`, `agy`, `antigravity` (`HERDR_ACCEPT_AGENTS`). For core, the process is the basename of `foreground.argv[0]` (`foreground.name` is the Claude version string, e.g. `2.1.321`, so do not use it).
- Commits: Angular convention `type(scope): description`, imperative, one logical change each.
- Work on branch `feat/herdr-app-port` in `/Users/chunamanh/Developer/Personal/herdr-accept-tool` (no worktree: launchd and the mod symlink must point at this stable path; `wtp` is not installed).

## Verified facts (2026-11-10, herdr-core 0.1.19)

- `hc keys <t>` accepts `down`, `up`, `enter`, `tab`, `space`, `y`, and also `Down` / `Space` (case-insensitive).
- `hc read --json <t>` → `{"complete": true, "how": "screen", "text": "…"}`.
- `hc get <t>` → one JSON object with `address`, `cwd`, `labels`, `foreground: {argv, name, cwd, pid}`, `state`.
- `hc ls --json --label accept=all` → `{"terminals": [{"address", "agent", "cwd", "state", …}], "machines": […]}` (no labels in the list).
- `hc get nosuch` exits 3 with `{"error":{"hint":…,"kind":"not_found","message":"no terminal \"nosuch\""}}`.
- `herdr-app check` passes on a mod folder that is a symlink under `mods/`.
- The `main` layout's tab block has `pane.header = {content: {mod: "pane"}, height: 30, position: "top", reveal: "always"}`.

## Deviations from the spec (decided while planning)

- Core targets are not namespaced (`core:`) inside the supervisor: TUI ids always contain `:` (`w26:p4D`), core addresses never do (`t17`, `mac-mini-tvf/t1`), so they cannot collide. Each source keeps its own entries. The CLI still takes `core:t17`.
- `CoreBackend` and `run_hc` live in `herdr_accept_tool.py` next to `TuiBackend`, so the CLI stays a single symlinkable file; supervisor-only core calls go to `scripts/core_api.py` (mirrors `scripts/herdr_api.py`).
- The layout is cloned as `main-accept` with `layout.clone` rather than relying on an implicit `main-edited`, so uninstall can switch back to `main` and delete one file.

## File map

| File | Responsibility |
|---|---|
| `herdr_accept_tool.py` (modify) | `run_hc`, `Backend`, `TuiBackend`, `CoreBackend`, `Answerer.backend`, CLI `core:` target |
| `scripts/core_api.py` (create) | Find armed core terminals, build `Armed` entries from labels, process name, disarm |
| `scripts/accept_state.py` (modify) | Heartbeat writes epoch content |
| `scripts/supervisor.py` (modify) | `TuiSource`, `CoreSource`, per-source backoff, cycle over sources |
| `herdr-app/accept-header/state.js` (create) | Pure arming rules: `nextMode`, `labelArgs`, `modeOf`, `heartbeatStale`, `MARKERS` |
| `herdr-app/accept-header/main.js` (create) | Pane header view, key commands, `hc` label writes, toasts |
| `herdr-app/accept-header/mod.json` (create) | Mod manifest (`place: none`) |
| `scripts/herdr_app_config.py` (create) | Merge/remove keys in `keys.json`, point a layout's pane header at a mod |
| `scripts/install-herdr-app.sh` (create) | Symlink mod, clone layout, set header, add keys, check; `--uninstall` |
| `scripts/install-launchd.sh` (modify) | Pass `HERDR_CORE_BIN` to the supervisor |
| `tests/test_core.py` (create) | Backends, `run_hc`, CLI target, `core_api`, heartbeat, supervisor sources |
| `tests/test_herdr_app_config.py` (create) | Key merge/removal and header edit |
| `tests/js/accept_state.test.mjs` (create) | `state.js` rules |
| `.gitignore` (modify) | Ignore files the app writes into the mod folder |
| `README.md` (modify) | herdr-app section |

---

### Task 1: Backend seam and `CoreBackend`

**Files:**

- Modify: `herdr_accept_tool.py` (imports at top; `run_herdr` block ~lines 127-139; `read_screen`/`send_keys` ~157-164; `Answerer` ~357-410)
- Test: `tests/test_core.py` (create)

**Interfaces:**

- Consumes: existing `HerdrError`, `run_herdr`, `read_screen(pane_id, lines)`, `send_keys(pane_id, keys)`, `Answerer`.
- Produces:
  - `HC: str` — herdr-core binary.
  - `run_hc(args: List[str], timeout: float = 5.0) -> str` — raises `HerdrError(message)`.
  - `class Backend(Protocol)`: `read_screen(self, target: str, lines: int) -> str`; `send_keys(self, target: str, keys: Sequence[str]) -> None`.
  - `class TuiBackend` — delegates to module `read_screen` / `send_keys` (looked up at call time, so `mock.patch("herdr_accept_tool.send_keys")` in existing tests still works).
  - `class CoreBackend` — `hc read --json`, `hc keys` with lowercased names.
  - `Answerer.backend: Backend` (default `TuiBackend()`); `Answerer.answer` sends keys through it.

- [ ] **Step 1: Write the failing test** — create `tests/test_core.py`:

```python
"""herdr-core (hc) support: backends, CLI targets, core_api and supervisor sources."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("HERDR_ACCEPT_STATE_DIR", tempfile.mkdtemp(prefix="herdr-accept-test-"))

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

import herdr_accept_tool as tool  # noqa: E402
import test_parse as cc  # noqa: E402
from herdr_accept_tool import (  # noqa: E402
    DEFAULT_PREFER,
    MODE_ALL,
    Answerer,
    CoreBackend,
    HerdrError,
    TuiBackend,
)

PREFER = re.compile(DEFAULT_PREFER)


class RecordingBackend:
    def __init__(self, screen: str = "") -> None:
        self.screen = screen
        self.sent = []

    def read_screen(self, target: str, lines: int) -> str:
        return self.screen

    def send_keys(self, target: str, keys) -> None:
        self.sent.append((target, list(keys)))


class RunHcTest(unittest.TestCase):
    def test_error_message_comes_from_json_stdout(self) -> None:
        failed = subprocess.CompletedProcess(
            args=[], returncode=3,
            stdout='{"error":{"kind":"not_found","message":"no terminal \\"x\\""}}', stderr="",
        )
        with mock.patch("herdr_accept_tool.subprocess.run", return_value=failed):
            with self.assertRaisesRegex(HerdrError, 'no terminal "x"'):
                tool.run_hc(["get", "x"])

    def test_missing_binary_is_herdr_error(self) -> None:
        with mock.patch("herdr_accept_tool.subprocess.run", side_effect=OSError("nope")):
            with self.assertRaisesRegex(HerdrError, "cannot run hc"):
                tool.run_hc(["ls"])


class CoreBackendTest(unittest.TestCase):
    def test_read_screen_returns_text(self) -> None:
        raw = json.dumps({"complete": True, "how": "screen", "text": "hello\n❯ 1. Yes"})
        with mock.patch("herdr_accept_tool.run_hc", return_value=raw) as run:
            self.assertEqual(CoreBackend().read_screen("t17", 80), "hello\n❯ 1. Yes")
        run.assert_called_once_with(["read", "--json", "t17"])

    def test_read_screen_rejects_unexpected_output(self) -> None:
        with mock.patch("herdr_accept_tool.run_hc", return_value="not json"):
            with self.assertRaises(HerdrError):
                CoreBackend().read_screen("t17", 80)

    def test_send_keys_lowercases_names(self) -> None:
        with mock.patch("herdr_accept_tool.run_hc") as run:
            CoreBackend().send_keys("t17", ["Down", "Space", "Enter", "y"])
        run.assert_called_once_with(["keys", "t17", "down", "space", "enter", "y"])


class AnswererBackendTest(unittest.TestCase):
    def test_answer_sends_through_backend(self) -> None:
        backend = RecordingBackend()
        answerer = Answerer(pane_id="t17", prefer=PREFER, quiet=True, mode=MODE_ALL, backend=backend)
        self.assertTrue(answerer.answer(cc.PERMISSION))
        self.assertEqual(backend.sent, [("t17", ["Enter"])])

    def test_default_backend_is_tui(self) -> None:
        self.assertIsInstance(Answerer(pane_id="w1:p1", prefer=PREFER).backend, TuiBackend)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test, verify it fails** — Run: `python3 -m unittest tests.test_core -v` Expected: FAIL / ERROR with `ImportError: cannot import name 'CoreBackend' from 'herdr_accept_tool'`.

- [ ] **Step 3: Write minimal implementation** — in `herdr_accept_tool.py`:

Add `import shutil` to the imports and change the typing import to:

```python
from typing import List, Optional, Protocol, Sequence
```

Below `HERDR = …` add:

```python
HC = os.environ.get("HERDR_CORE_BIN") or shutil.which("hc") or "herdr-core"
```

Replace the whole `run_herdr` function with:

```python
def _run(binary: str, name: str, args: List[str], timeout: float) -> str:
    try:
        result = subprocess.run(
            [binary] + args, capture_output=True, text=True, timeout=timeout
        )
    except OSError as error:
        raise HerdrError("cannot run %s: %s" % (name, error)) from error
    except subprocess.TimeoutExpired as error:
        raise HerdrError("%s timed out: %s" % (name, " ".join(args))) from error
    if result.returncode != 0:
        raise HerdrError(_failure_detail(name, result))
    return result.stdout


def _failure_detail(name: str, result: "subprocess.CompletedProcess[str]") -> str:
    try:
        message = json.loads(result.stdout)["error"]["message"]
        if isinstance(message, str) and message:
            return message
    except (ValueError, KeyError, TypeError):
        pass
    detail = (result.stderr or result.stdout).strip().splitlines()
    return detail[0] if detail else "%s exit %d" % (name, result.returncode)


def run_herdr(args: List[str], timeout: float = 5.0) -> str:
    return _run(HERDR, "herdr", args, timeout)


def run_hc(args: List[str], timeout: float = 5.0) -> str:
    return _run(HC, "hc", args, timeout)
```

Below `send_keys` add:

```python
class Backend(Protocol):
    """Where a target's screen comes from and where its key presses go."""

    def read_screen(self, target: str, lines: int) -> str: ...

    def send_keys(self, target: str, keys: Sequence[str]) -> None: ...


class TuiBackend:
    """herdr TUI panes (`w26:p4D`) through the herdr CLI."""

    def read_screen(self, target: str, lines: int) -> str:
        return read_screen(target, lines)

    def send_keys(self, target: str, keys: Sequence[str]) -> None:
        send_keys(target, keys)


class CoreBackend:
    """herdr-core terminals (`t17`) through hc. Reads the visible screen only."""

    def read_screen(self, target: str, lines: int) -> str:
        raw = run_hc(["read", "--json", target])
        try:
            text = json.loads(raw)["text"]
        except (ValueError, KeyError, TypeError) as error:
            raise HerdrError("unexpected hc read output: %s" % raw[:80]) from error
        if not isinstance(text, str):
            raise HerdrError("unexpected hc read output: %s" % raw[:80])
        return text

    def send_keys(self, target: str, keys: Sequence[str]) -> None:
        run_hc(["keys", target] + [key.lower() for key in keys])
```

In `Answerer`, add the field after `mode` (before `answered`):

```python
    backend: Backend = field(default_factory=TuiBackend)
```

and in `Answerer.answer` replace `send_keys(self.pane_id, keys)` with:

```python
            self.backend.send_keys(self.pane_id, keys)
```

- [ ] **Step 4: Run test, verify pass** — Run: `python3 -m unittest discover -s tests` Expected: `OK` (49 existing + 7 new = 56 tests).

- [ ] **Step 5: Commit** — `git add herdr_accept_tool.py tests/test_core.py && git commit -m "feat(core): add hc backend behind a backend seam"`

---

### Task 2: CLI `core:` target

**Files:**

- Modify: `herdr_accept_tool.py` (`resolve_pane` area, `watch`, `build_parser`)
- Test: `tests/test_core.py` (append class)

**Interfaces:**

- Consumes: `run_hc`, `CoreBackend`, `TuiBackend`, `resolve_pane` (Task 1 / existing).
- Produces: `CORE_PREFIX = "core:"`; `resolve_target(target: str) -> Tuple[str, Backend]`; `watch` reads through the resolved backend.

- [ ] **Step 1: Write the failing test** — append to `tests/test_core.py` before `if __name__ == "__main__":`:

```python
class ResolveTargetTest(unittest.TestCase):
    def test_core_prefix_checks_terminal_and_uses_core_backend(self) -> None:
        with mock.patch("herdr_accept_tool.run_hc", return_value="{}") as run:
            target, backend = tool.resolve_target("core:t17")
        run.assert_called_once_with(["get", "t17"])
        self.assertEqual(target, "t17")
        self.assertIsInstance(backend, CoreBackend)

    def test_other_targets_use_tui(self) -> None:
        with mock.patch("herdr_accept_tool.resolve_pane", return_value="w26:p4D"):
            target, backend = tool.resolve_target("my-agent")
        self.assertEqual(target, "w26:p4D")
        self.assertIsInstance(backend, TuiBackend)

    def test_unknown_core_terminal_raises(self) -> None:
        with mock.patch("herdr_accept_tool.run_hc", side_effect=HerdrError('no terminal "t99"')):
            with self.assertRaises(HerdrError):
                tool.resolve_target("core:t99")
```

- [ ] **Step 2: Run test, verify it fails** — Run: `python3 -m unittest tests.test_core.ResolveTargetTest -v` Expected: ERROR with `AttributeError: module 'herdr_accept_tool' has no attribute 'resolve_target'`.

- [ ] **Step 3: Write minimal implementation** — in `herdr_accept_tool.py`:

Change the typing import to `from typing import List, Optional, Protocol, Sequence, Tuple`. Below `PANE_ID_PATTERN` add:

```python
CORE_PREFIX = "core:"
```

After the `CoreBackend` class add:

```python
def resolve_target(target: str) -> Tuple[str, Backend]:
    """`core:t17` is a herdr-core terminal; anything else a herdr TUI agent or pane."""
    if target.startswith(CORE_PREFIX):
        address = target[len(CORE_PREFIX):]
        run_hc(["get", address])
        return address, CoreBackend()
    return resolve_pane(target), TuiBackend()
```

In `watch`, replace the first two lines and the `Answerer(...)` call and the read with:

```python
def watch(args: argparse.Namespace) -> int:
    pane_id, backend = resolve_target(args.target)
    log("watching %s (target %s, mode %s)" % (pane_id, args.target, args.mode), args.quiet)
    answerer = Answerer(
        pane_id=pane_id,
        prefer=re.compile(args.prefer),
        cooldown=args.cooldown,
        dry_run=args.dry_run,
        quiet=args.quiet,
        mode=args.mode,
        backend=backend,
    )
```

and inside the loop replace `screen = read_screen(pane_id, args.lines)` with:

```python
            screen = backend.read_screen(pane_id, args.lines)
```

In `build_parser`, change the target help to:

```python
    parser.add_argument("target", help="herdr agent name or pane id (w26:p42), or a herdr-core terminal (core:t17)")
```

In the module docstring `Usage:` block, change the usage line to:

```
    herdr-accept-tool <agent-name|pane-id|core:terminal> [options]
```

- [ ] **Step 4: Run test, verify pass** — Run: `python3 -m unittest discover -s tests` Expected: `OK` (59 tests).

- [ ] **Step 5: Commit** — `git add herdr_accept_tool.py tests/test_core.py && git commit -m "feat(cli): accept core:<terminal> targets"`

---

### Task 3: `core_api` and epoch heartbeat

**Files:**

- Create: `scripts/core_api.py`
- Modify: `scripts/accept_state.py` (`touch_heartbeat`)
- Test: `tests/test_core.py` (append classes)

**Interfaces:**

- Consumes: `run_hc`, `HerdrError`, `MODES` from `herdr_accept_tool`; `state.Armed`, `state.DEFAULT_TTL_SECONDS`.
- Produces (module `core_api`):
  - `LABEL_MODE = "accept"`, `LABEL_AT = "accept.at"`
  - `armed_terminals() -> Dict[str, dict]` — address → `hc get` record, for every live terminal labelled `accept=all` or `accept=permissions`.
  - `armed_entry(address: str, record: dict, ttl: float = state.DEFAULT_TTL_SECONDS) -> state.Armed` — unparsable `accept.at` gives `armed_at=0.0` (expires at once).
  - `process_name(record: Optional[dict]) -> Optional[str]`
  - `disarm(address: str) -> None`
- Produces (`accept_state`): `touch_heartbeat()` writes `"%d" % time.time()` into the heartbeat file.

- [ ] **Step 1: Write the failing test** — append to `tests/test_core.py` before `if __name__ == "__main__":`:

```python
import accept_state as state  # noqa: E402
import core_api  # noqa: E402

T17 = {
    "address": "t17",
    "cwd": "/Users/x/Developer/Personal",
    "foreground": {"argv": ["claude", "--resume", "abc"], "name": "2.1.321"},
    "labels": {"accept": "all", "accept.at": "1000", "herdr.space": "sp1"},
    "state": "live",
}


def fake_hc(records):
    """run_hc stand-in: `ls --label accept=<mode>` and `get <address>` over records."""

    def run(args):
        if args[0] == "ls":
            mode = args[-1].split("=", 1)[1]
            hits = [{"address": a} for a, r in records.items() if r["labels"].get("accept") == mode]
            return json.dumps({"terminals": hits, "machines": []})
        if args[0] == "get":
            return json.dumps(records[args[1]])
        raise AssertionError("unexpected hc call %r" % (args,))

    return run


class CoreApiTest(unittest.TestCase):
    def test_armed_terminals_lists_both_modes(self) -> None:
        t18 = dict(T17, address="t18", labels={"accept": "permissions", "accept.at": "1000"})
        with mock.patch("core_api.run_hc", side_effect=fake_hc({"t17": T17, "t18": t18})):
            found = core_api.armed_terminals()
        self.assertEqual(sorted(found), ["t17", "t18"])
        self.assertEqual(found["t18"]["labels"]["accept"], "permissions")

    def test_terminal_gone_between_ls_and_get_is_skipped(self) -> None:
        listed = fake_hc({"t17": T17})

        def run(args):
            if args[0] == "get":
                raise HerdrError('no terminal "t17"')
            return listed(args)

        with mock.patch("core_api.run_hc", side_effect=run):
            self.assertEqual(core_api.armed_terminals(), {})

    def test_armed_entry_reads_labels(self) -> None:
        entry = core_api.armed_entry("t17", T17, ttl=60.0)
        self.assertEqual((entry.pane_id, entry.mode, entry.armed_at, entry.ttl), ("t17", MODE_ALL, 1000.0, 60.0))
        self.assertTrue(entry.expired(now=1060.0))

    def test_bad_armed_at_expires_at_once(self) -> None:
        record = dict(T17, labels={"accept": "all", "accept.at": "soon"})
        self.assertTrue(core_api.armed_entry("t17", record, ttl=60.0).expired(now=61.0))

    def test_process_name_uses_argv_not_version_name(self) -> None:
        self.assertEqual(core_api.process_name(T17), "claude")
        self.assertEqual(core_api.process_name({"foreground": {"argv": ["/bin/zsh", "-l"]}}), "zsh")
        self.assertEqual(core_api.process_name({"foreground": {"argv": ["-zsh"]}}), "zsh")
        self.assertIsNone(core_api.process_name({"foreground": None}))
        self.assertIsNone(core_api.process_name(None))

    def test_disarm_removes_both_labels(self) -> None:
        with mock.patch("core_api.run_hc") as run:
            core_api.disarm("t17")
        run.assert_called_once_with(["label", "t17", "accept=", "accept.at="])


class HeartbeatTest(unittest.TestCase):
    def test_heartbeat_holds_epoch(self) -> None:
        with mock.patch("accept_state.time.time", return_value=1234.9):
            state.touch_heartbeat()
        self.assertEqual(state.HEARTBEAT_FILE.read_text(), "1234")
```

- [ ] **Step 2: Run test, verify it fails** — Run: `python3 -m unittest tests.test_core -v` Expected: ERROR with `ModuleNotFoundError: No module named 'core_api'`.

- [ ] **Step 3: Write minimal implementation** — create `scripts/core_api.py`:

```python
"""herdr-core (hc) calls the supervisor needs beyond reading screens and pressing keys.

A herdr-core terminal is armed by two labels on the terminal itself:
`accept` (`all` or `permissions`) and `accept.at` (epoch seconds). The labels
go away with the terminal, so there is nothing to prune.
"""

from __future__ import annotations

import json
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
            address = terminal.get("address")
            if not isinstance(address, str):
                continue
            try:
                found[address] = _json(run_hc(["get", address]))
            except HerdrError:
                continue  # ended between ls and get; it is gone with its labels
    return found


def armed_entry(address: str, record: dict, ttl: float = state.DEFAULT_TTL_SECONDS) -> state.Armed:
    labels = record.get("labels") or {}
    try:
        armed_at = float(labels.get(LABEL_AT, ""))
    except ValueError:
        armed_at = 0.0
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
```

In `scripts/accept_state.py` replace `touch_heartbeat` with:

```python
def touch_heartbeat() -> None:
    """Epoch seconds as content: the herdr-app mod reads it (mods cannot stat)."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    HEARTBEAT_FILE.write_text("%d" % time.time())
```

- [ ] **Step 4: Run test, verify pass** — Run: `python3 -m unittest discover -s tests` Expected: `OK` (66 tests).

- [ ] **Step 5: Commit** — `git add scripts/core_api.py scripts/accept_state.py tests/test_core.py && git commit -m "feat(core): read and clear arming labels on herdr-core terminals"`

---

### Task 4: Supervisor sources with independent backoff

**Files:**

- Modify: `scripts/supervisor.py` (imports; replace `Supervisor` class; module docstring)
- Test: `tests/test_core.py` (append class)

**Interfaces:**

- Consumes: `TuiBackend`, `CoreBackend`, `Backend`, `HerdrError`, `Answerer` (Task 1); `core_api.*` (Task 3); `state.*`, `herdr.*` (existing); `plan_cycle` (unchanged).
- Produces:
  - `Snapshot = Tuple[Dict[str, state.Armed], Dict[str, dict], Callable[[str], Optional[str]]]`
  - `class TuiSource` / `class CoreSource`: attributes `name: str`, `backend: Backend`; methods `snapshot() -> Snapshot`, `disarm(target: str, reason: str, live: bool) -> None`.
  - `Supervisor(args, sources: Optional[list] = None)`; `answerer_for(pane_id, mode, backend=None)`; `cycle() -> bool`.

- [ ] **Step 1: Write the failing test** — append to `tests/test_core.py` before `if __name__ == "__main__":`:

```python
from supervisor import CoreSource, Supervisor, TuiSource, build_parser  # noqa: E402


class FakeSource:
    def __init__(self, name, armed=None, live=None, process=None, screen="", error=None):
        self.name = name
        self.backend = RecordingBackend(screen)
        self.armed = armed or {}
        self.live = live or {}
        self.process = process or {}
        self.error = error
        self.snapshots = 0
        self.disarmed = []

    def snapshot(self):
        self.snapshots += 1
        if self.error:
            raise HerdrError(self.error)
        return self.armed, self.live, self.process.get

    def disarm(self, target, reason, live):
        self.disarmed.append((target, reason, live))


def core_armed(address, armed_at=1e12, mode=MODE_ALL):
    return state.Armed(pane_id=address, cwd="/tmp", armed_at=armed_at, ttl=3600.0, label_before=None, mode=mode)


class SupervisorSourcesTest(unittest.TestCase):
    def supervisor(self, *sources):
        return Supervisor(build_parser().parse_args(["--settle", "0"]), sources=list(sources))

    def test_default_sources_are_tui_then_core(self) -> None:
        supervisor = Supervisor(build_parser().parse_args([]))
        self.assertEqual([type(s) for s in supervisor.sources], [TuiSource, CoreSource])

    def test_core_prompt_answered_through_core_backend(self) -> None:
        core = FakeSource("core", {"t17": core_armed("t17")}, {"t17": {}}, {"t17": "claude"}, screen=cc.PERMISSION)
        self.assertTrue(self.supervisor(core).cycle())
        self.assertEqual(core.backend.sent, [("t17", ["Enter"])])

    def test_down_source_backs_off_alone(self) -> None:
        tui = FakeSource("tui", error="socket gone")
        core = FakeSource("core", {"t17": core_armed("t17")}, {"t17": {}}, {"t17": "claude"}, screen=cc.PERMISSION)
        supervisor = self.supervisor(tui, core)
        self.assertTrue(supervisor.cycle())
        self.assertTrue(supervisor.cycle())
        self.assertEqual(tui.snapshots, 1)
        self.assertEqual(core.snapshots, 2)

    def test_expired_core_terminal_is_disarmed(self) -> None:
        core = FakeSource("core", {"t17": core_armed("t17", armed_at=0.0)}, {"t17": {}}, {"t17": "claude"})
        self.assertFalse(self.supervisor(core).cycle())
        self.assertEqual(core.disarmed, [("t17", "ttl expired", True)])

    def test_core_shell_stays_idle(self) -> None:
        core = FakeSource("core", {"t17": core_armed("t17")}, {"t17": {}}, {"t17": "zsh"}, screen=cc.PERMISSION)
        self.assertFalse(self.supervisor(core).cycle())
        self.assertEqual(core.backend.sent, [])
        self.assertEqual(core.disarmed, [])

    def test_core_source_snapshot_from_labels(self) -> None:
        with mock.patch("core_api.run_hc", side_effect=fake_hc({"t17": T17})):
            armed, live, process_of = CoreSource().snapshot()
        self.assertEqual(list(armed), ["t17"])
        self.assertEqual(armed["t17"].mode, MODE_ALL)
        self.assertIn("t17", live)
        self.assertEqual(process_of("t17"), "claude")
```

- [ ] **Step 2: Run test, verify it fails** — Run: `python3 -m unittest tests.test_core -v` Expected: ERROR with `ImportError: cannot import name 'CoreSource' from 'supervisor'`.

- [ ] **Step 3: Write minimal implementation** — in `scripts/supervisor.py`:

Replace the module docstring's first paragraph with:

```python
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
```

Change the imports block to:

```python
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
```

(`read_screen` is no longer imported; `re`, `time`, `argparse`, `os`, dataclass imports stay.)

After `plan_cycle`, add the sources and replace the whole `Supervisor` class with:

```python
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

    def snapshot(self, source, now: float) -> Optional[Snapshot]:
        """The source's armed targets, or None while it is backing off."""
        retry_at, backoff = self.retry.get(source.name, (0.0, BACKOFF_MIN))
        if now < retry_at:
            return None
        try:
            snap = source.snapshot()
        except HerdrError as error:
            log("%s unavailable (%s), retry in %.0fs" % (source.name, error, backoff))
            self.retry[source.name] = (now + backoff, min(backoff * 2, BACKOFF_MAX))
            return None
        self.retry.pop(source.name, None)
        return snap

    def cycle(self) -> bool:
        """One pass over every source. Returns True when any target is active."""
        state.touch_heartbeat()
        now = time.time()
        any_active = False
        for source in self.sources:
            snap = self.snapshot(source, now)
            if not snap or not snap[0]:
                continue
            armed, live, process_of = snap
            plan = plan_cycle(armed, live, now, process_of)
            for pane_id, reason in plan.dropped.items():
                self.drop(source, pane_id, reason, live=pane_id in live)
            for pane_id, process in plan.idle.items():
                if self.idle_reported.get(pane_id) != process:
                    log("%s idle: foreground is %s, waiting for an agent" % (pane_id, process))
                    self.idle_reported[pane_id] = process
            for pane_id in plan.active:
                any_active = True
                self.idle_reported.pop(pane_id, None)
                try:
                    screen = source.backend.read_screen(pane_id, SCREEN_LINES)
                except HerdrError as error:
                    log("%s read failed: %s" % (pane_id, error))
                    continue
                answerer = self.answerer_for(pane_id, armed[pane_id].mode, source.backend)
                if answerer.answer(screen):
                    time.sleep(self.args.settle)
        return any_active

    def run(self) -> int:
        log("supervisor started, sources %s, state %s" % (
            ", ".join(source.name for source in self.sources), state.STATE_FILE))
        while True:
            active = self.cycle()
            if self.args.once:
                return 0
            time.sleep(self.args.interval if active else self.args.idle_interval)
```

Update the parser description to `"Answer prompts on every armed herdr pane and herdr-core terminal."`.

- [ ] **Step 4: Run test, verify pass** — Run: `python3 -m unittest discover -s tests` Expected: `OK` (72 tests; `AnswererModeSwitchTest` in `test_supervisor.py` still passes through the `backend=None` default).

- [ ] **Step 5: Commit** — `git add scripts/supervisor.py tests/test_core.py && git commit -m "feat(supervisor): poll herdr-core terminals next to TUI panes"`

---

### Task 5: `accept-header` herdr-app mod

**Files:**

- Create: `herdr-app/accept-header/state.js`, `herdr-app/accept-header/main.js`, `herdr-app/accept-header/mod.json`
- Modify: `.gitignore`
- Test: `tests/js/accept_state.test.mjs`

**Interfaces:**

- Consumes: labels `accept` / `accept.at` (Global Constraints); `herdr` module `panes, props, run, theme, home, terminals, focused, hc, notify, nextCommand, readTextFile`; shipped icons `mods/pane/{split-right,split-down,zoom,unzoom,close}.svg` and `mods/workspace-chrome/spinner.svg`.
- Produces: mod name `accept-header` answering commands `toggle`, `toggle-permissions`, `disarm-all` (bound in Task 6); `state.js` exports `MODE_ALL`, `MODE_PERMISSIONS`, `MARKERS`, `nextMode(current, command)`, `labelArgs(address, mode, nowSeconds)`, `modeOf(terminal)`, `heartbeatStale(text, nowSeconds, maxAge = 15)`.

- [ ] **Step 1: Write the failing test** — create `tests/js/accept_state.test.mjs`:

```js
import { test } from "node:test";
import assert from "node:assert/strict";
import {
  MARKERS,
  heartbeatStale,
  labelArgs,
  modeOf,
  nextMode,
} from "../../herdr-app/accept-header/state.js";

test("toggle arms all, disarms all, switches permissions to all", () => {
  assert.equal(nextMode(null, "toggle"), "all");
  assert.equal(nextMode("all", "toggle"), null);
  assert.equal(nextMode("permissions", "toggle"), "all");
});

test("toggle-permissions mirrors toggle", () => {
  assert.equal(nextMode(null, "toggle-permissions"), "permissions");
  assert.equal(nextMode("permissions", "toggle-permissions"), null);
  assert.equal(nextMode("all", "toggle-permissions"), "permissions");
});

test("a click cycles off, all, permissions, off", () => {
  assert.equal(nextMode(null, "cycle"), "all");
  assert.equal(nextMode("all", "cycle"), "permissions");
  assert.equal(nextMode("permissions", "cycle"), null);
});

test("an unknown command keeps the mode", () => {
  assert.equal(nextMode("all", "focus"), "all");
  assert.equal(nextMode(null, "focus"), null);
});

test("labelArgs arms with a whole-second timestamp and disarms both labels", () => {
  assert.deepEqual(labelArgs("t17", "all", 1000.7), ["label", "t17", "accept=all", "accept.at=1000"]);
  assert.deepEqual(labelArgs("t17", null, 1000), ["label", "t17", "accept=", "accept.at="]);
});

test("modeOf only trusts known modes", () => {
  assert.equal(modeOf({ labels: { accept: "all" } }), "all");
  assert.equal(modeOf({ labels: { accept: "permissions" } }), "permissions");
  assert.equal(modeOf({ labels: { accept: "yes" } }), null);
  assert.equal(modeOf({ labels: {} }), null);
  assert.equal(modeOf(null), null);
});

test("heartbeatStale", () => {
  assert.equal(heartbeatStale("1000", 1010), false);
  assert.equal(heartbeatStale("1000", 1016), true);
  assert.equal(heartbeatStale(null, 1000), true);
  assert.equal(heartbeatStale("", 1000), true);
});

test("markers match the TUI plugin", () => {
  assert.deepEqual(MARKERS, { all: "⚡", permissions: "🔐" });
});
```

- [ ] **Step 2: Run test, verify it fails** — Run: `node --test tests/js/` Expected: FAIL with `Cannot find module …/herdr-app/accept-header/state.js`.

- [ ] **Step 3: Write minimal implementation**

Create `herdr-app/accept-header/state.js`:

```js
// Arming rules for the accept-header mod. No imports, so Node can test it.
// A herdr-core terminal is armed by two labels: accept=all|permissions and
// accept.at=<epoch seconds>. The supervisor applies the TTL.

export const MODE_ALL = "all";
export const MODE_PERMISSIONS = "permissions";
export const MARKERS = { [MODE_ALL]: "⚡", [MODE_PERMISSIONS]: "🔐" };

/** The mode after `command`: null is off. Same switching rules as the TUI plugin. */
export function nextMode(current, command) {
  switch (command) {
    case "toggle":
      return current === MODE_ALL ? null : MODE_ALL;
    case "toggle-permissions":
      return current === MODE_PERMISSIONS ? null : MODE_PERMISSIONS;
    case "cycle":
      if (current === null) return MODE_ALL;
      return current === MODE_ALL ? MODE_PERMISSIONS : null;
    default:
      return current;
  }
}

/** `hc` arguments that put `address` into `mode` (null: off). */
export function labelArgs(address, mode, nowSeconds) {
  if (!mode) return ["label", address, "accept=", "accept.at="];
  return ["label", address, `accept=${mode}`, `accept.at=${Math.floor(nowSeconds)}`];
}

/** A terminal's mode from its labels, or null when not armed. */
export function modeOf(terminal) {
  const mode = terminal?.labels?.accept;
  return mode === MODE_ALL || mode === MODE_PERMISSIONS ? mode : null;
}

/** True when the supervisor heartbeat (epoch seconds as text) is missing or old. */
export function heartbeatStale(text, nowSeconds, maxAge = 15) {
  const beat = Number.parseFloat(text ?? "");
  return !Number.isFinite(beat) || nowSeconds - beat > maxAge;
}
```

Create `herdr-app/accept-header/mod.json`:

```json
{ "place": "none", "title": "Pane header (auto-accept)" }
```

Create `herdr-app/accept-header/main.js`:

```js
// The shipped pane header plus herdr-accept-tool: after the name it shows the
// herdr-core terminal address and ⚡ (answer every dialog) or 🔐 (permissions
// only). Clicking the marker cycles off → ⚡ → 🔐 → off. Key commands from
// keys.json (accept-header.toggle, .toggle-permissions, .disarm-all) reach every
// copy; only the copy of the focused pane acts. Props: { pane, terminal }.

import { View, div, svg, image } from "gpui-kit";
import { h_flex } from "gpui-base";
import { focused, hc, home, nextCommand, notify, panes, props, readTextFile, run, terminals, theme } from "herdr";
import { MARKERS, MODE_ALL, heartbeatStale, labelArgs, modeOf, nextMode } from "./state.js";

const HEARTBEAT = "/.local/state/herdr-accept-tool/supervisor.heartbeat";

function icon(p, size, color) {
  if (!p?.icon) return null;
  return p.tint ? svg(p.icon).size(size).flex_none().text_color(color) : image(p.icon).w(size).h(size).flex_none();
}

function folder(cwd) {
  if (!cwd) return "";
  const h = home();
  return cwd === h ? "~" : cwd.startsWith(h + "/") ? "~" + cwd.slice(h.length) : cwd;
}

function nowSeconds() {
  return Date.now() / 1000;
}

export default class AcceptHeader extends View {
  init(_props, cx) {
    this.hovered = false;
    cx.spawn(async (cx) => {
      for (;;) {
        const command = await nextCommand();
        if (focused()?.pane !== props()?.pane) continue;
        if (command === "disarm-all") await this.disarmAll();
        else await this.apply(command);
        cx.notify();
      }
    });
  }

  me() {
    return panes().find((p) => p.pane === props()?.pane);
  }

  terminal() {
    const address = props()?.terminal;
    return address ? terminals().find((t) => t.address === address) ?? null : null;
  }

  async apply(command) {
    const address = props()?.terminal;
    if (!address) return;
    const current = modeOf(this.terminal());
    const mode = nextMode(current, command);
    if (mode === current) return;
    const result = await hc(labelArgs(address, mode, nowSeconds()));
    if (result.code !== 0) {
      notify({ title: "auto-accept failed", body: (result.stdout || result.stderr).trim().slice(0, 200), level: "error" });
      return;
    }
    if (!mode) {
      notify({ title: "auto-accept OFF", body: address, level: "info" });
      return;
    }
    const stale = heartbeatStale(await readTextFile(home() + HEARTBEAT), nowSeconds());
    const what = mode === MODE_ALL ? "all dialogs" : "permissions only";
    notify({
      title: `auto-accept ${MARKERS[mode]} ON`,
      body: stale ? `${address} · ${what} · supervisor not running` : `${address} · ${what}`,
      level: stale ? "warning" : "success",
    });
  }

  async disarmAll() {
    const armed = terminals().filter((t) => modeOf(t));
    for (const t of armed) await hc(labelArgs(t.address, null, 0));
    notify({ title: "auto-accept OFF everywhere", body: `${armed.length} terminal(s)`, level: "info" });
  }

  button(t, id, iconName, command, args) {
    return div()
      .id(id)
      .p(3)
      .rounded(4)
      .text_color(t.dim)
      .hover((s) => s.bg(t.hover).text_color(t.foreground))
      .on_click((_e, cx) => {
        cx.stop_propagation();
        run(command, args);
      })
      .child(svg(`mods/pane/${iconName}.svg`).size(14));
  }

  marker(t, pane, mode) {
    return div()
      .id(`ph-a-${pane}`)
      .flex_none()
      .px(3)
      .rounded(4)
      .text_color(t.dim)
      .hover((s) => s.bg(t.hover))
      .on_click((_e, cx) => {
        cx.stop_propagation();
        cx.spawn(async (cx) => {
          await this.apply("cycle");
          cx.notify();
        });
      })
      .child(mode ? MARKERS[mode] : "○");
  }

  render(cx) {
    const t = theme();
    const p = this.me();
    if (!p) return div();
    const name = ((p.program?.agent || p.program?.shell) && p.program.name) || p.title || p.program?.name || "shell";
    const pic = icon(p.program, 14, t.dim);
    const st = p.status;
    const pane = p.pane;
    const address = props()?.terminal;
    const mode = modeOf(this.terminal());
    return h_flex()
      .id(`pane-head-${pane}`)
      .size_full()
      .px(10)
      .gap(8)
      .items_center()
      .bg(t.background)
      .border_b(1)
      .border_color(t.border)
      .text_size(12)
      .on_hover((hovered, cx) => { this.hovered = hovered; cx.notify(); })
      .on_click(() => run("pane.focus", { pane }))
      .when(Boolean(pic), (el) => el.child(pic))
      .child(div().flex_none().truncate().max_w(260).font_medium().text_color(t.foreground).child(name))
      .when(Boolean(address), (el) => el.child(div().flex_none().text_color(t.dim).child(`· ${address}`)))
      .when(Boolean(address) && (Boolean(mode) || this.hovered), (el) => el.child(this.marker(t, pane, mode)))
      .child(div().flex_1().truncate().text_color(t.dim).child(folder(p.cwd)))
      .when(st === "working", (el) => el.child(svg("mods/workspace-chrome/spinner.svg").size(12).flex_none().text_color(t.working).spin(900)))
      .when(st === "blocked", (el) => el.child(div().flex_none().px(6).h(18).flex().items_center().rounded(5).bg(t.blocked + "26").text_size(10.5).font_semibold().text_color(t.blocked).child("Needs you")))
      .when(st === "done", (el) => el.child(div().size(7).flex_none().rounded(4).bg(t.done)))
      .when(this.hovered, (el) => el
        .child(this.button(t, `ph-r-${pane}`, "split-right", "pane.split", { direction: "right", pane }))
        .child(this.button(t, `ph-d-${pane}`, "split-down", "pane.split", { direction: "down", pane }))
        .child(this.button(t, `ph-z-${pane}`, p.zoomed ? "unzoom" : "zoom", "pane.zoom", { pane }))
        .child(this.button(t, `ph-x-${pane}`, "close", "pane.close", { pane })));
  }
}
```

Append to `.gitignore`:

```
# Written into the mod folder by herdr-app on load.
herdr-app/accept-header/gpui-kit.d.ts
herdr-app/accept-header/jsconfig.json
```

- [ ] **Step 4: Run test, verify pass** — Run: `node --test tests/js/` Expected: `# pass 8`, `# fail 0`. Then check the mod loads (temporary link, removed right after; the real install is Task 6): `ln -s "$PWD/herdr-app/accept-header" ~/.config/herdr-app/mods/accept-header && herdr-app check ~/.config/herdr-app/mods/accept-header; rm ~/.config/herdr-app/mods/accept-header` Expected: `check passed: …/mods/accept-header`.

- [ ] **Step 5: Commit** — `git add herdr-app tests/js .gitignore && git commit -m "feat(herdr-app): add accept-header pane header mod"`

---

### Task 6: Install for herdr-app, launchd env, README

**Files:**

- Create: `scripts/herdr_app_config.py`, `scripts/install-herdr-app.sh`
- Modify: `scripts/install-launchd.sh` (EnvironmentVariables block, ~line 44-48; binary lookup ~line 27-29)
- Modify: `README.md` (new section after `## Plugin` … `### Safety rules in the supervisor`)
- Test: `tests/test_herdr_app_config.py`

**Interfaces:**

- Consumes: mod name `accept-header` and its commands (Task 5).
- Produces (`herdr_app_config`): `KEYS: Dict[str, str]`; `add_keys(keys: dict) -> List[str]` (returns conflicting key names, changes nothing when non-empty); `remove_keys(keys: dict) -> None`; `set_header(layout: dict, mod: str) -> bool`; CLI `python3 scripts/herdr_app_config.py add-keys|remove-keys <keys.json>` and `set-header <layout.json> <mod>`.

- [ ] **Step 1: Write the failing test** — create `tests/test_herdr_app_config.py`:

```python
"""keys.json merging and layout header edits for the herdr-app install."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import herdr_app_config as config  # noqa: E402

LAYOUT = {
    "type": "row",
    "children": [
        {"type": "block", "content": {"mod": "spaces"}},
        {
            "id": "main",
            "type": "block",
            "content": {
                "tab": "active",
                "pane": {"gap": 8, "header": {"content": {"mod": "pane"}, "height": 30, "position": "top", "reveal": "always"}},
            },
        },
    ],
}


class KeysTest(unittest.TestCase):
    def test_add_keys_merges_into_global(self) -> None:
        keys = {"global": {"ctrl-a t": "tab.new"}, "terminal": {}}
        self.assertEqual(config.add_keys(keys), [])
        self.assertEqual(keys["global"]["ctrl-a y"], "accept-header.toggle")
        self.assertEqual(keys["global"]["ctrl-a u"], "accept-header.toggle-permissions")
        self.assertEqual(keys["global"]["ctrl-a shift-y"], "accept-header.disarm-all")
        self.assertEqual(keys["global"]["ctrl-a t"], "tab.new")

    def test_add_keys_refuses_conflicts_and_changes_nothing(self) -> None:
        keys = {"global": {"ctrl-a y": "tab.new"}}
        self.assertEqual(config.add_keys(keys), ["ctrl-a y"])
        self.assertEqual(keys, {"global": {"ctrl-a y": "tab.new"}})

    def test_add_keys_is_idempotent(self) -> None:
        keys = {}
        config.add_keys(keys)
        self.assertEqual(config.add_keys(keys), [])

    def test_remove_keys_only_removes_ours(self) -> None:
        keys = {"global": {"ctrl-a t": "tab.new"}}
        config.add_keys(keys)
        keys["global"]["ctrl-a u"] = "something.else"
        config.remove_keys(keys)
        self.assertEqual(keys["global"], {"ctrl-a t": "tab.new", "ctrl-a u": "something.else"})


class HeaderTest(unittest.TestCase):
    def test_set_header_points_tab_block_at_mod(self) -> None:
        layout = {"children": [dict(LAYOUT["children"][0]), {"content": {"tab": "active", "pane": {"gap": 8, "header": {"content": {"mod": "pane"}, "height": 30}}}}]}
        self.assertTrue(config.set_header(layout, "accept-header"))
        self.assertEqual(layout["children"][1]["content"]["pane"]["header"]["content"]["mod"], "accept-header")
        self.assertEqual(layout["children"][1]["content"]["pane"]["header"]["height"], 30)

    def test_set_header_adds_header_when_missing(self) -> None:
        layout = {"content": {"tab": "active", "pane": {"gap": 8}}}
        self.assertTrue(config.set_header(layout, "accept-header"))
        self.assertEqual(
            layout["content"]["pane"]["header"],
            {"content": {"mod": "accept-header"}, "height": 30, "position": "top", "reveal": "always"},
        )

    def test_set_header_without_tab_block(self) -> None:
        self.assertFalse(config.set_header({"content": {"mod": "spaces"}}, "accept-header"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test, verify it fails** — Run: `python3 -m unittest tests.test_herdr_app_config -v` Expected: ERROR with `ModuleNotFoundError: No module named 'herdr_app_config'`.

- [ ] **Step 3: Write minimal implementation**

Create `scripts/herdr_app_config.py`:

```python
#!/usr/bin/env python3
"""Edit herdr-app config files for the accept-header mod.

usage:
  herdr_app_config.py add-keys <keys.json>      bind ctrl-a y / u / shift-y (refuses conflicts)
  herdr_app_config.py remove-keys <keys.json>   unbind them (only if still ours)
  herdr_app_config.py set-header <layout.json> <mod>   frame panes with <mod> as header
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Dict, List

KEYS: Dict[str, str] = {
    "ctrl-a y": "accept-header.toggle",
    "ctrl-a u": "accept-header.toggle-permissions",
    "ctrl-a shift-y": "accept-header.disarm-all",
}
DEFAULT_HEADER = {"height": 30, "position": "top", "reveal": "always"}


def add_keys(keys: dict) -> List[str]:
    bound = keys.setdefault("global", {})
    conflicts = [key for key, command in KEYS.items() if key in bound and bound[key] != command]
    if not conflicts:
        bound.update(KEYS)
    return conflicts


def remove_keys(keys: dict) -> None:
    bound = keys.get("global") or {}
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


def _load(path: Path) -> dict:
    return json.loads(path.read_text()) if path.exists() else {}


def _save(path: Path, data: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    os.replace(tmp, path)


def main(argv: List[str]) -> int:
    if len(argv) >= 2 and argv[0] in ("add-keys", "remove-keys"):
        path = Path(argv[1])
        keys = _load(path)
        if argv[0] == "remove-keys":
            remove_keys(keys)
        else:
            conflicts = add_keys(keys)
            if conflicts:
                sys.stderr.write("already bound to something else: %s\n" % ", ".join(conflicts))
                return 1
        _save(path, keys)
        return 0
    if len(argv) == 3 and argv[0] == "set-header":
        path = Path(argv[1])
        layout = _load(path)
        if not set_header(layout, argv[2]):
            sys.stderr.write("no tab block in %s\n" % path)
            return 1
        _save(path, layout)
        return 0
    sys.stderr.write(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

Create `scripts/install-herdr-app.sh`:

```bash
#!/usr/bin/env bash
# Install (or remove) auto-accept in the Herdr desktop app (herdr-app).
#
#   scripts/install-herdr-app.sh              install / reinstall
#   scripts/install-herdr-app.sh --uninstall
#
# Links the accept-header mod into the app, clones the main layout as
# main-accept with that mod as the pane header, and binds ctrl-a y / u / shift-y.
# The Herdr window must be open (layout commands go through it). Answering is
# done by the launchd supervisor: scripts/install-launchd.sh.
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
app_home="${HERDR_APP_HOME:-$HOME/.config/herdr-app}"
mod="accept-header"
mod_link="$app_home/mods/$mod"
layout_name="main-accept"
layout="$app_home/layouts/$layout_name.json"
keys="$app_home/keys.json"
config="$repo/scripts/herdr_app_config.py"

command -v herdr-app >/dev/null || { echo "herdr-app not on PATH" >&2; exit 1; }

if [ "${1:-}" = "--uninstall" ]; then
  python3 "$config" remove-keys "$keys"
  herdr-app do layout.switch --name main >/dev/null || true
  rm -f "$layout"
  [ -L "$mod_link" ] && rm "$mod_link"
  echo "removed $mod, $layout_name and its keys"
  exit 0
fi

if [ -e "$mod_link" ] && [ ! -L "$mod_link" ]; then
  echo "$mod_link exists and is not our link; move it away first" >&2
  exit 1
fi
ln -sfn "$repo/herdr-app/$mod" "$mod_link"
herdr-app check "$mod_link"

if [ ! -f "$layout" ]; then
  herdr-app do layout.clone --name main --as "$layout_name" >/dev/null
fi
python3 "$config" set-header "$layout" "$mod"
herdr-app do layout.switch --name "$layout_name" >/dev/null

python3 "$config" add-keys "$keys"

for f in "$app_home/keys.error" "$app_home/layouts/$layout_name.error" "$app_home/layout.error"; do
  if [ -f "$f" ]; then
    echo "herdr-app rejected a file: $f" >&2
    cat "$f" >&2
    exit 1
  fi
done

echo "installed $mod (layout $layout_name, keys ctrl-a y / u / shift-y)"
```

Make both executable: `chmod +x scripts/install-herdr-app.sh scripts/herdr_app_config.py`.

In `scripts/install-launchd.sh`, after the `herdr_bin=…` check add:

```bash
hc_bin="$(command -v hc || command -v herdr-core || true)"
```

and in the `EnvironmentVariables` dict, after the `HERDR_BIN_PATH` entry add:

```xml
    <key>HERDR_CORE_BIN</key><string>${hc_bin:-hc}</string>
```

In `README.md`, insert before `### Safety rules in the supervisor`:

````markdown
### Herdr app (herdr-core)

The same supervisor answers prompts in the Herdr desktop app. Its terminals run
in herdr-core (`hc`); a terminal is armed by two labels on the terminal itself,
`accept=all|permissions` and `accept.at=<epoch>`, so arming ends with the
terminal and there is nothing to prune.

```bash
bash scripts/install-launchd.sh      # once: the supervisor serves the TUI and herdr-core
bash scripts/install-herdr-app.sh    # with the Herdr window open
```

`install-herdr-app.sh` links `herdr-app/accept-header` into
`~/.config/herdr-app/mods`, clones the `main` layout as `main-accept` with that
mod as the pane header, and binds:

| key | effect |
|---|---|
| `ctrl-a y` | toggle all dialogs on the focused pane (`⚡`) |
| `ctrl-a u` | toggle permissions only (`🔐`) |
| `ctrl-a shift-y` | disarm every herdr-core terminal |

The header shows the terminal address after the name (`Claude Code · t17 ⚡`);
clicking the marker cycles off → `⚡` → `🔐` → off. `--uninstall` switches back
to `main` and removes the layout, the link and the keys. The CLI takes
herdr-core terminals too: `herdr-accept-tool core:t17`.
````

Also add one line to the README `## Tests` block after the Python command:

```bash
node --test tests/js/
```

- [ ] **Step 4: Run test, verify pass** — Run: `python3 -m unittest discover -s tests && node --test tests/js/ && bash -n scripts/install-herdr-app.sh scripts/install-launchd.sh` Expected: `OK` (79 tests), `# fail 0`, no output from `bash -n`.

- [ ] **Step 5: Commit** — `git add scripts/herdr_app_config.py scripts/install-herdr-app.sh scripts/install-launchd.sh README.md tests/test_herdr_app_config.py && git commit -m "feat(install): install auto-accept into herdr-app"`

---

### Task 7: Live verification and install

No new code; every step records evidence. Run from the repo root. Stop and report if any expected result differs.

- [ ] **Step 1: Full gates** — Run: `python3 -m unittest discover -s tests && node --test tests/js/` Expected: `OK`, `# fail 0`.

- [ ] **Step 2: Throwaway Claude terminal** — Run:

```bash
SPACE=$(herdr-app ls | python3 -c 'import sys,json; print(next(s["id"] for s in json.load(sys.stdin)["spaces"] if s["name"]=="Random Shiet"))')
herdr-app do tab.new --name "accept test" --space "$SPACE" --folder /tmp --argv '["claude","--permission-mode","default"]'
```

Note the returned `terminal` (call it `$T`). Wait until `hc read --json $T` shows the Claude prompt.

- [ ] **Step 3: CLI on a real permission prompt** — Run: `hc send $T "Run the shell command: ls /tmp"`, wait until `hc read --json $T` shows `Do you want to proceed?`, then `python3 herdr_accept_tool.py core:$T --once --dry-run` Expected log: `$T prompt '…' -> option 1 'Yes' (keys: Enter) [dry-run]`. Then `python3 herdr_accept_tool.py core:$T --once` Expected: same line without `[dry-run]`, and the prompt is gone from `hc read --json $T`.

- [ ] **Step 4: Install the mod and keys** — Run: `bash scripts/install-herdr-app.sh` Expected: `check passed: …` and `installed accept-header (layout main-accept, keys ctrl-a y / u / shift-y)`. Ask the user to look at the "accept test" tab: header shows `Claude Code · $T`.

- [ ] **Step 5: Reload the supervisor with the new code** — Run: `bash scripts/install-launchd.sh` Expected: `installed dev.kuzco77.herdr-accept-supervisor`; within 5 s `tail -3 ~/.local/state/herdr-accept-tool/supervisor.log` shows `supervisor started, sources tui, core`.

- [ ] **Step 6: Arm through the app and answer end to end** — Ask the user to focus the "accept test" pane and press `ctrl-a y`. Expected: `⚡` in the header, a success toast, and `hc get $T` labels include `accept: all` and `accept.at`. Run `hc send $T "Run the shell command: ls /"`. Expected within ~3 s: `supervisor.log` shows `$T prompt … -> option 1 'Yes' (keys: Enter)`.

- [ ] **Step 7: Permissions mode leaves questions** — Ask the user to press `ctrl-a u` (header switches to `🔐`). Run `hc send $T "Use AskUserQuestion to ask me whether to use tabs or spaces"`. Expected: `supervisor.log` shows `$T question … left for you (permissions mode)` and the question stays on screen.

- [ ] **Step 8: Click, disarm and clean up** — Ask the user to click the `🔐` marker twice. Expected: off (marker shown only on hover as `○`), then `⚡`. Then press `ctrl-a shift-y`. Expected: marker gone, `hc get $T` has no `accept` labels. Close the test tab: `herdr-app do tab.close --id <its tab id> --confirmed true`.

- [ ] **Step 9: TUI regression** — Run: `python3 scripts/supervisor.py --once --dry-run 2>&1 | tail -5` Expected: no traceback; any armed TUI pane is listed or the cycle is silent.
