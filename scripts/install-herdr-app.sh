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
#
# Install records the layout shown before switching in
# $state_dir/herdr-app-prev-layout; uninstall switches back to it (else main).
# keys.json is copied once to keys.json.accept-backup before the first edit.
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
app_home="${HERDR_APP_HOME:-$HOME/.config/herdr-app}"
state_dir="${HERDR_ACCEPT_STATE_DIR:-$HOME/.local/state/herdr-accept-tool}"
prev_layout_file="$state_dir/herdr-app-prev-layout"
mod="accept-header"
mod_link="$app_home/mods/$mod"
layout_name="main-accept"
layout="$app_home/layouts/$layout_name.json"
keys="$app_home/keys.json"
config="$repo/scripts/herdr_app_config.py"

die() {
  echo "$*" >&2
  exit 1
}

# Sets $status; fails with a hint when the Herdr window is closed.
read_status() {
  status="$(herdr-app status 2>&1)" || {
    echo "herdr-app status failed; open the Herdr window and run this again:" >&2
    echo "$status" >&2
    exit 1
  }
}

# `herdr-app do` prints its error JSON on stdout, so keep the output and show it on failure.
app_do() {
  local output
  output="$(herdr-app "do" "$@" 2>&1)" || {
    echo "herdr-app do $* failed:" >&2
    echo "$output" >&2
    return 1
  }
}

current_layout() {
  python3 "$config" status-layout <<<"$status"
}

uninstall() {
  local current target switched=""
  read_status
  current="$(current_layout)"
  target=main
  if [ -s "$prev_layout_file" ]; then
    target="$(<"$prev_layout_file")"
  fi

  if [ "$current" = "$layout_name" ]; then
    app_do layout.switch --name "$target" || {
      echo "could not switch back to layout '$target'; $layout, the mod link and the keys are kept." >&2
      echo "Fix the cause above, or delete $prev_layout_file to fall back to 'main', then run --uninstall again." >&2
      exit 1
    }
    switched=" (layout shown: $target)"
  fi

  if [ -f "$keys" ]; then
    python3 "$config" remove-keys "$keys"
  else
    echo "no $keys; no keys to remove"
  fi
  rm -f "$layout" "$prev_layout_file"
  if [ -L "$mod_link" ]; then
    rm "$mod_link"
  fi
  echo "removed $mod, $layout_name and its keys$switched"
}

# Polls the app's own error list: it re-reads edited files live, so give it a moment.
wait_for_clean_status() {
  local _
  for _ in 1 2 3 4 5 6; do
    read_status
    python3 "$config" status-errors <<<"$status" >&2 || die "herdr-app reported errors after the install (above); run --uninstall to roll back"
    sleep 0.5
  done
}

install() {
  local current
  read_status
  # Fail before touching anything: a key conflict or bad keys.json must not leave a half-installed layout.
  python3 "$config" check-keys "$keys"

  if [ -e "$mod_link" ] && [ ! -L "$mod_link" ]; then
    die "$mod_link exists and is not our link; move it away first"
  fi
  ln -sfn "$repo/herdr-app/$mod" "$mod_link"
  herdr-app check "$mod_link"

  current="$(current_layout)"
  if [ "$current" != "$layout_name" ]; then
    mkdir -p "$state_dir"
    printf '%s\n' "$current" >"$prev_layout_file"
  fi

  if [ ! -f "$layout" ]; then
    app_do layout.clone --name main --as "$layout_name"
    [ -f "$layout" ] || die "layout.clone reported success but $layout does not exist"
  fi
  python3 "$config" set-header "$layout" "$mod"
  app_do layout.switch --name "$layout_name"

  python3 "$config" add-keys "$keys"
  wait_for_clean_status

  echo "installed $mod (layout $layout_name, keys ctrl-a y / u / shift-y)"
}

command -v herdr-app >/dev/null || die "herdr-app not on PATH"

if [ "${1:-}" = "--uninstall" ]; then
  uninstall
else
  install
fi
