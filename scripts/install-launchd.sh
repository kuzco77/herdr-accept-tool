#!/usr/bin/env bash
# Install (or remove) the supervisor as a macOS launchd user agent.
#
#   scripts/install-launchd.sh            install / reinstall and start
#   scripts/install-launchd.sh --uninstall
#
# KeepAlive restarts the supervisor if it dies; RunAtLoad starts it at login.
# Logs: ~/.local/state/herdr-accept-tool/supervisor.log
set -euo pipefail

label="dev.kuzco77.herdr-accept-supervisor"
plist="$HOME/Library/LaunchAgents/$label.plist"
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
state_dir="${HERDR_ACCEPT_STATE_DIR:-$HOME/.local/state/herdr-accept-tool}"
domain="gui/$(id -u)"

if [ "${1:-}" = "--uninstall" ]; then
  launchctl bootout "$domain/$label" 2>/dev/null || true
  rm -f "$plist"
  echo "removed $label"
  exit 0
fi

[ "$(uname)" = "Darwin" ] || { echo "launchd is macOS only; run scripts/supervisor.py under systemd --user instead" >&2; exit 1; }

python3_bin="$(command -v python3)"
herdr_bin="$(command -v herdr || true)"
[ -n "$herdr_bin" ] || { echo "herdr not on PATH" >&2; exit 1; }

mkdir -p "$state_dir" "$(dirname "$plist")"

cat > "$plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$label</string>
  <key>ProgramArguments</key>
  <array>
    <string>$python3_bin</string>
    <string>$repo/scripts/supervisor.py</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key><string>$(dirname "$herdr_bin"):/usr/local/bin:/usr/bin:/bin</string>
    <key>HERDR_BIN_PATH</key><string>$herdr_bin</string>
    <key>HERDR_ACCEPT_STATE_DIR</key><string>$state_dir</string>
  </dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>5</integer>
  <key>StandardOutPath</key><string>$state_dir/supervisor.log</string>
  <key>StandardErrorPath</key><string>$state_dir/supervisor.log</string>
</dict>
</plist>
PLIST

launchctl bootout "$domain/$label" 2>/dev/null || true
launchctl bootstrap "$domain" "$plist"
launchctl kickstart -k "$domain/$label"
echo "installed $label"
echo "log: $state_dir/supervisor.log"
