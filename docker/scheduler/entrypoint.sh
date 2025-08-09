#!/usr/bin/env bash
set -euo pipefail

: "${SCHEDULE_NIGHTLY:=0 2 * * *}"

CRON_FILE=/etc/cron.d/library-data
LOGFILE=/var/log/cron.log

mkdir -p "$(dirname "$LOGFILE")"
touch "$LOGFILE"

echo "${SCHEDULE_NIGHTLY} library-data-nightly >> ${LOGFILE} 2>&1" > "$CRON_FILE"
chmod 0644 "$CRON_FILE"
crontab "$CRON_FILE"

echo "Installed crontab:" && cat "$CRON_FILE"
echo "Starting cron..."
exec cron -f

