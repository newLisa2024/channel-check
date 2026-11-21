#!/bin/sh
# Nightly pg_dump into ./backups on the server, keeping KEEP_DAYS days.
# Copy ./backups off the server (for example to Timeweb S3 with rclone) — see README.
set -eu
while true; do
  stamp=$(date -u +%Y-%m-%d_%H%M)
  pg_dump --format=custom --file="/backups/channelcheck_${stamp}.dump"
  find /backups -name 'channelcheck_*.dump' -mtime +"${KEEP_DAYS:-14}" -delete
  echo "backup done: ${stamp}"
  sleep 86400
done
