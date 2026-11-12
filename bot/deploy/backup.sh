#!/usr/bin/env bash
# Daily backup (run by guildledger-backup.timer as user guildledger; also fine by hand):
#   sudo -u guildledger /opt/guildledger/src/bot/deploy/backup.sh
# SQLite online backup -> /var/lib/guildledger/backups/guildledger-<date>.db.gz, keep 14 days,
# restore check, and (if [backup] webhook is set) a copy to the private #gl-backup channel.
set -euo pipefail
exec /opt/guildledger/venv/bin/python -m guildledger_bot --config /etc/guildledger/config.toml \
  backup --dir /var/lib/guildledger/backups --keep-days 14
