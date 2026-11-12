#!/usr/bin/env bash
# Update the bot on the server.
#   - Repository cloned with git:   sudo bash update.sh /path/to/clone   (git pull, then reinstall)
#   - Code copied by tools/deploy.ps1: just run deploy.ps1 again; it calls setup.sh, which is the update.
# setup.sh copies the code, reinstalls it into the venv and restarts the service; data and config stay.
set -euo pipefail
REPO="${1:-}"
if [[ -z "$REPO" ]]; then
  echo "usage: sudo bash update.sh /path/to/git/clone   (or run tools/deploy.ps1 from your PC)" >&2
  exit 2
fi
[[ -d "$REPO/.git" ]] || { echo "$REPO is not a git clone" >&2; exit 1; }
owner="$(stat -c %U "$REPO")"
sudo -u "$owner" git -C "$REPO" pull --ff-only
exec bash "$REPO/bot/deploy/setup.sh"
