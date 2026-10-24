#!/usr/bin/env bash
# Plugin startup hook: runs once when the herdr server is up. Drops armed panes
# that did not survive the restore, then nudges the launchd supervisor so it
# is running if it was installed. Exits immediately; the supervisor itself is
# never a child of herdr.
set -uo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
label="dev.kuzco77.herdr-accept-supervisor"

python3 "$here/toggle.py" prune || true

if [ "$(uname)" = "Darwin" ] && [ -f "$HOME/Library/LaunchAgents/$label.plist" ]; then
  launchctl kickstart "gui/$(id -u)/$label" 2>/dev/null || true
fi
