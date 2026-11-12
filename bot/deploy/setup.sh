#!/usr/bin/env bash
# GuildLedger bot: install or update on the server (Ubuntu/Debian, systemd). Idempotent: run it again
# to update. Run as root from an unpacked copy of the repository (tools/deploy.ps1 does all of this):
#
#   sudo bash bot/deploy/setup.sh [--config FILE] [--archive FILE]
#
#   --config FILE   install FILE as /etc/guildledger/config.toml (mode 600), replacing the old one
#   --archive FILE  install FILE as the archive database, only if the server has none yet
#
# Leaves SSH, ufw and unattended-upgrades alone (server-baseline.sh owns them); it only reports them.
set -euo pipefail

APP=/opt/guildledger
DATA=/var/lib/guildledger
ETC=/etc/guildledger
USER_=guildledger
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"   # repo root: companion/ and bot/

CONFIG_IN=""
ARCHIVE_IN=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --config) CONFIG_IN="$2"; shift 2 ;;
    --archive) ARCHIVE_IN="$2"; shift 2 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done

say() { printf '\033[1;32m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m!!\033[0m %s\n' "$*"; }

[[ $EUID -eq 0 ]] || { echo "run with sudo" >&2; exit 1; }
[[ -d "$SRC/companion/guildledger" && -d "$SRC/bot/guildledger_bot" ]] || { echo "not a GuildLedger source tree: $SRC" >&2; exit 1; }

say "packages"
need=()
for p in python3 python3-venv sqlite3; do dpkg -s "$p" >/dev/null 2>&1 || need+=("$p"); done
if ((${#need[@]})); then apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "${need[@]}"; fi

say "system user $USER_"
id "$USER_" >/dev/null 2>&1 || useradd --system --home-dir "$DATA" --no-create-home --shell /usr/sbin/nologin "$USER_"

say "folders"
install -d -m 755 -o root -g root "$APP" "$ETC"
install -d -m 700 -o "$USER_" -g "$USER_" "$DATA" "$DATA/backups"

say "code -> $APP/src"
rm -rf "$APP/src.new"
mkdir -p "$APP/src.new"
cp -r "$SRC/companion" "$SRC/bot" "$APP/src.new/"
find "$APP/src.new" -name '__pycache__' -prune -exec rm -rf {} + \
  -o \( -name 'config.toml' -o -name '*.db' -o -name '*.db-wal' -o -name '*.db-shm' -o -name '*.log' \) -exec rm -f {} +
rm -rf "$APP/src.old"
[[ -d "$APP/src" ]] && mv "$APP/src" "$APP/src.old"
mv "$APP/src.new" "$APP/src"
chown -R root:root "$APP/src"

say "python venv"
[[ -x "$APP/venv/bin/python" ]] || python3 -m venv "$APP/venv"
"$APP/venv/bin/pip" install -q --upgrade pip
"$APP/venv/bin/pip" install -q --upgrade "$APP/src/companion" "$APP/src/bot"
rm -rf "$APP/src.old"

say "config $ETC/config.toml"
if [[ -n "$CONFIG_IN" ]]; then
  install -m 600 -o "$USER_" -g "$USER_" "$CONFIG_IN" "$ETC/config.toml"
  shred -u "$CONFIG_IN" 2>/dev/null || rm -f "$CONFIG_IN"   # it holds the token: no copy left behind
elif [[ ! -f "$ETC/config.toml" ]]; then
  install -m 600 -o "$USER_" -g "$USER_" "$APP/src/bot/config.example.toml" "$ETC/config.toml"
  warn "new config from the example: fill in $ETC/config.toml (sudo nano $ETC/config.toml), then run setup again"
fi
chown "$USER_:$USER_" "$ETC/config.toml"
chmod 600 "$ETC/config.toml"

DB="$DATA/guildledger.db"
if [[ -n "$ARCHIVE_IN" ]]; then
  if [[ -f "$DB" ]]; then
    warn "server already has an archive; NOT replacing it with $ARCHIVE_IN"
  else
    say "archive from your PC -> $DB"
    install -m 600 -o "$USER_" -g "$USER_" "$ARCHIVE_IN" "$DB"
  fi
  rm -f "$ARCHIVE_IN"
fi

say "systemd units"
install -m 644 "$APP/src/bot/deploy/guildledger-bot.service" /etc/systemd/system/
install -m 644 "$APP/src/bot/deploy/guildledger-backup.service" /etc/systemd/system/
install -m 644 "$APP/src/bot/deploy/guildledger-backup.timer" /etc/systemd/system/
systemctl daemon-reload
systemctl enable -q guildledger-bot.service
systemctl enable -q --now guildledger-backup.timer

say "config check"
if sudo -u "$USER_" "$APP/venv/bin/python" -m guildledger_bot --config "$ETC/config.toml" check; then
  systemctl restart guildledger-bot.service
  sleep 5
  systemctl --no-pager --lines=0 status guildledger-bot.service || true
  journalctl -u guildledger-bot.service -n 8 --no-pager -o cat || true
else
  warn "config not complete yet: the bot is installed but not started"
fi

say "baseline (report only)"
grep -qs '^PasswordAuthentication no' /etc/ssh/sshd_config.d/*.conf && echo "ssh: password login off" || warn "ssh: password login NOT disabled"
command -v ufw >/dev/null && ufw status | head -1 || warn "ufw not installed"
systemctl is-enabled -q unattended-upgrades 2>/dev/null && echo "unattended-upgrades: on" || warn "unattended-upgrades: off"
echo "listening TCP ports (only sshd expected):"
ss -tlnH | awk '{print "  " $4}'
say "done"
