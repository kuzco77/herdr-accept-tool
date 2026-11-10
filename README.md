# herdr-accept-tool

Auto-answer interactive prompts in a herdr agent pane. Works with Claude Code
and Antigravity CLI (`agy`). Two ways to use it:

- **CLI**: `herdr-accept-tool <agent-name|pane-id>` from any other pane
  watches that one pane until it closes.
- **herdr plugin**: a keybind (e.g. `prefix+y`) arms the pane you are in; a
  supervisor running under launchd answers prompts on every armed pane and
  survives herdr restarts and reboots. See [Plugin](#plugin).

Whenever a watched pane shows a choice dialog the tool picks an option and
confirms it. Two modes decide which dialogs it touches:

| mode | CLI | plugin action | label | answers |
|---|---|---|---|---|
| all (default) | `--mode all` | `toggle`, `arm` | `⚡` | every dialog |
| permissions only | `--mode permissions` | `toggle-permissions`, `arm-permissions` | `🔐` | permission and approval prompts; questions the agent asks you stay on screen |

A dialog counts as a *question* when it carries a marker only
`AskUserQuestion` / `ask_question` render: a `Type something`, `Chat about
this`, `Submit answers` or `Write-in...` option, checkboxes, or a
`Question n/m:` heading. A dialog counts as a *permission* when it is the
Antigravity artifact panel or has a Yes-style option and none of those
markers (tool permissions, folder trust, plan approval). Anything else is
treated as a question, so permissions mode never answers a dialog it cannot
classify. In permissions mode a skipped question is logged once per
`--cooldown`.

Choice order per dialog:

1. first option whose label matches `--prefer` (default: `Recommended`,
   `Khuyến nghị`, `Đề xuất`, `Nên chọn`)
2. first option whose label starts with `Yes`, `Có`, `Đồng ý`, `Tiếp tục`,
   `Chấp nhận` or `OK`
3. option 1

Vietnamese and English option labels are both supported out of the box.

Handled dialogs (verified with Claude Code 2.1.301 inside herdr):

- permission prompts (`Do you want to proceed?` → Yes)
- plan approval (`Yes, and auto-accept edits` → first Yes)
- `AskUserQuestion` single-select, including multi-question sets with the
  final `Submit answers` screen
- `AskUserQuestion` multi-select: ticks the chosen option, then presses Tab to
  move on

Handled dialogs (verified with Antigravity CLI 1.2.14 inside herdr):

- folder trust on startup (`Yes, I trust this folder`)
- tool permission prompts: shell (`Run this command?`), file create / edit
  (`Allow creation of this file?`) → first Yes
- `ask_question` single-select, multi-question sets (`Question 1/2 …`)
- `ask_question` multi-select: ticks the chosen option with Space, then
  presses Enter to submit
- `/artifact` review panel while an item shows `Action required`: presses
  `y` to approve the highlighted artifact (plan mode)

The agent is detected from the cursor glyph: Claude Code draws `❯`,
Antigravity draws `>` (and `›` in the artifact panel). Anything without a
cursor on a `1.` … `N.` list is ignored, so numbered lists in normal assistant
output never trigger a key press. Antigravity's un-numbered trust dialog is
only accepted when a `↑/↓ Navigate` hint follows it, which keeps echoed user
input (`> …`) and answered-question summaries from being treated as prompts.

## Requirements

- Python 3.9+ (stdlib only)
- `herdr` on `PATH`, run from a shell inside herdr (`HERDR_ENV=1`)
- a Claude Code or Antigravity CLI session running in the target pane

## Install (global command)

```bash
git clone https://github.com/kuzco77/herdr-accept-tool.git ~/Developer/Personal/herdr-accept-tool
ln -s ~/Developer/Personal/herdr-accept-tool/herdr_accept_tool.py ~/.local/bin/herdr-accept-tool
```

`~/.local/bin` must be on `PATH`. After that `herdr-accept-tool <target>` works
from any directory.

## Usage

```bash
# by pane id
./herdr_accept_tool.py w26:p42

# by agent name (set with: herdr agent rename <pane> my-agent)
./herdr_accept_tool.py my-agent

# answer permission prompts only, leave the agent's questions for me
./herdr_accept_tool.py my-agent --mode permissions

# answer one prompt and exit
./herdr_accept_tool.py my-agent --once

# only log what it would press
./herdr_accept_tool.py my-agent --dry-run

# stop after 30 minutes
./herdr_accept_tool.py my-agent --timeout 1800
```

Runs until the pane closes, `--timeout` elapses, or Ctrl-C. Exit code 2 means
the target could not be resolved.

Options:

| flag | default | meaning |
|---|---|---|
| `--interval` | 1.0 | seconds between screen polls |
| `--settle` | 1.5 | pause after sending keys |
| `--cooldown` | 10 | seconds before re-answering an identical dialog |
| `--lines` | 80 | screen lines read per poll |
| `--prefer` | `Recommended\|Khuyến nghị` | regex for the preferred option |
| `--mode` | `all` | `all` answers every dialog, `permissions` answers permission prompts only |
| `--once` | off | exit after the first answer |
| `--dry-run` | off | detect and log only |
| `-q` | off | silence the log |

## Plugin

The plugin adds keybind-driven arming on top of the same parser. It has three
parts:

| part | runs where | job |
|---|---|---|
| actions (`toggle`, `toggle-permissions`, `arm`, `arm-permissions`, `disarm`, `disarm-all`, `status`) | herdr, on keypress | edit `~/.local/state/herdr-accept-tool/armed.json`, prefix the pane label with `⚡` (all) or `🔐` (permissions only), show a toast |
| `scripts/supervisor.py` | launchd user agent (macOS) | poll every armed pane, answer prompts, drop panes that closed or expired |
| startup hook + `pane.closed` event | herdr | prune stale panes, kick the supervisor after a herdr restart |

The supervisor is deliberately not a herdr child process: herdr documents
startup hooks as one-shot and asks plugins to stop detached processes, so a
supervisor spawned from herdr would die with it. launchd `KeepAlive` restarts
it after a crash, after a reboot, and while herdr is down it backs off and
retries without touching state.

### Install the plugin

```bash
herdr plugin link ~/Developer/Personal/herdr-accept-tool   # or: herdr plugin install kuzco77/herdr-accept-tool
bash ~/Developer/Personal/herdr-accept-tool/scripts/install-launchd.sh
```

`install-launchd.sh` writes `~/Library/LaunchAgents/dev.kuzco77.herdr-accept-supervisor.plist`
and starts it. `--uninstall` removes it. Linux: run `scripts/supervisor.py`
under a `systemd --user` unit with `Restart=always`.

Bind the actions in `~/.config/herdr/config.toml`, then `herdr server reload-config`:

```toml
[[keys.command]]
key = "prefix+y"
type = "plugin_action"
command = "herdr-accept-tool.toggle"
description = "auto-accept: toggle this pane (all dialogs)"

[[keys.command]]
key = "prefix+u"
type = "plugin_action"
command = "herdr-accept-tool.toggle-permissions"
description = "auto-accept: toggle this pane (permissions only)"

[[keys.command]]
key = "prefix+shift+y"
type = "plugin_action"
command = "herdr-accept-tool.disarm-all"
description = "auto-accept: off everywhere"
```

A toggle on a pane armed in the *other* mode switches mode instead of
disarming, so `prefix+y` then `prefix+u` leaves the pane in permissions-only
mode; press `prefix+u` again to disarm. Switching resets the TTL.

The `⚡` / `🔐` marker lives on the pane border label. With herdr's default
`ui.pane_borders = "auto"` a tab with a single pane draws no border, so the
marker is invisible there. Show borders always to see it on every pane:

```toml
[ui]
pane_borders = "always"
```

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
clicking the marker cycles off → `⚡` → `🔐` → off. The CLI takes
herdr-core terminals too: `herdr-accept-tool core:t17`.

The installer needs `herdr-app` on `PATH` and the Herdr window open (it reads
`herdr-app status` and switches layouts through the window). It checks
`keys.json` first and stops before changing anything when the file is missing,
is not valid JSON, or already binds one of the three keys to something else.
`keys.json` is rewritten as 2-space JSON; the original is copied once to
`keys.json.accept-backup` (kept if it already exists). The layout shown before
the switch is saved in `~/.local/state/herdr-accept-tool/herdr-app-prev-layout`.
After the edits it polls `herdr-app status` for about 3 s and fails, printing
the errors, if the app rejects a file.

`bash scripts/install-herdr-app.sh --uninstall` (window open) switches back to
the saved layout (`main` when none is saved), then removes `main-accept`, the
link and our keys. If that switch fails it changes nothing, says so, and exits 1;
re-run it once the window works.

### Safety rules in the supervisor

- A pane only gets key presses while its foreground process is a known agent
  (`claude`, `agy`, `antigravity`; override with `HERDR_ACCEPT_AGENTS`). A
  pane that came back from a herdr restore as a plain shell stays armed but
  idle until an agent is running in it again.
- Each pane auto-disarms after a TTL (12 h, override `HERDR_ACCEPT_TTL` in
  seconds) with a toast, so a forgotten pane does not run unattended for days.
- Pane ids are never reused by herdr (the counter is persisted in
  `session.json`), so an armed id cannot silently point at a different pane.
- Everything the supervisor answers is logged to
  `~/.local/state/herdr-accept-tool/supervisor.log`.

The toast on arming warns when the supervisor heartbeat is stale, which means
launchd is not running it.

## How it works

Each poll runs `herdr pane read <pane> --source visible`, parses the bottom
choice list with its cursor (`❯` or `>`), picks an option, and sends
`Down`/`Up` to reach it plus `Enter` through `herdr pane send-keys`.
Multi-select takes two polls: Claude Code gets `Enter` to tick then `Tab` to
advance; Antigravity gets `Space` to tick then `Enter` to submit. A pending
Antigravity artifact gets `y`. A fingerprint of agent + question + option
labels stops the same dialog being answered twice within `--cooldown`.

## Caveats

- Both modes approve whatever permission the agent asks for, including shell
  commands. Use it only on panes whose work you are happy to let run
  unattended. Permissions mode only keeps the agent's *questions* for you.
- Question detection relies on the extra options Claude Code and Antigravity
  render in their question tools. A question rendered without any of them
  (no `Type something` / `Chat about this` / `Write-in...` option) is still
  left alone unless it offers a Yes-style option, in which case it is
  answered as a permission.
- Free-text questions (`Type something`) are never chosen; the agent still
  gets the first real option.
- Antigravity in plan mode writes the plan as an artifact and waits for
  approval through `/artifact`; the tool approves it only while that panel is
  open. It does not open the panel itself.
- Rendering changes in Claude Code or Antigravity may need the regexes in
  `herdr_accept_tool.py` updated. Sample screens live in `tests/test_parse.py`
  (Claude Code) and `tests/test_antigravity.py` (Antigravity CLI).

## Tests

```bash
python3 -m unittest discover -s tests -v
node --test tests/js/
```

`test_parse.py` and `test_antigravity.py` hold captured screens;
`test_modes.py` classifies every captured screen as permission or question
and checks permissions mode sends nothing for questions;
`test_supervisor.py` covers the state file, per-mode labels and the
supervisor's per-cycle decisions (drop closed / expired panes, idle on plain
shells, re-arm in another mode).
