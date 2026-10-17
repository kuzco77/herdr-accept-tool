# herdr-accept-tool

Auto-answer interactive prompts in a herdr agent pane. Give it a herdr agent
name or pane id; whenever that pane shows a numbered choice dialog it picks an
option and confirms it.

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

Anything without a `❯` cursor on a `1.` … `N.` list is ignored, so numbered
lists in normal assistant output never trigger a key press.

## Requirements

- Python 3.9+ (stdlib only)
- `herdr` on `PATH`, run from a shell inside herdr (`HERDR_ENV=1`)

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
numbered list with its `❯` cursor, picks an option, and sends `Down`/`Up` to
reach it plus `Enter` through `herdr pane send-keys`. For a ticked multi-select
checkbox it sends `Tab` instead. A fingerprint of question + option labels
stops the same dialog being answered twice within `--cooldown`.

## Caveats

- This approves whatever the agent asks, including shell commands. Use it only
  on panes whose work you are happy to let run unattended.
- Free-text questions (`Type something`) are never chosen; the agent still
  gets the first real option.
- Rendering changes in Claude Code or other agents may need the regexes in
  `herdr_accept_tool.py` updated. Sample screens live in `tests/test_parse.py`.

## Tests

```bash
python3 -m unittest discover -s tests -v
```
