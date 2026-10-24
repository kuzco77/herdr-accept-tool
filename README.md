# herdr-accept-tool

Auto-answer interactive prompts in a herdr agent pane. Give it a herdr agent
name or pane id; whenever that pane shows a choice dialog it picks an option
and confirms it. Works with Claude Code and Antigravity CLI (`agy`).

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
| `--once` | off | exit after the first answer |
| `--dry-run` | off | detect and log only |
| `-q` | off | silence the log |

## How it works

Each poll runs `herdr pane read <pane> --source visible`, parses the bottom
choice list with its cursor (`❯` or `>`), picks an option, and sends
`Down`/`Up` to reach it plus `Enter` through `herdr pane send-keys`.
Multi-select takes two polls: Claude Code gets `Enter` to tick then `Tab` to
advance; Antigravity gets `Space` to tick then `Enter` to submit. A pending
Antigravity artifact gets `y`. A fingerprint of agent + question + option
labels stops the same dialog being answered twice within `--cooldown`.

## Caveats

- This approves whatever the agent asks, including shell commands. Use it only
  on panes whose work you are happy to let run unattended.
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
```
