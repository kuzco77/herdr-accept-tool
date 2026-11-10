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
