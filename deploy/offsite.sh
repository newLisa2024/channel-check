#!/bin/sh
# Копирует свежие дампы из /backups в S3 (Timeweb) и чистит в S3 копии старше KEEP_DAYS_REMOTE дней.
# Копирование только в одну сторону: удаление на сервере НЕ удаляет копии в S3.
# Если ключи S3 не заданы, контейнер не падает, а ждёт и пишет об этом в лог (деплой остаётся зелёным).
set -u

INTERVAL="${OFFSITE_INTERVAL_SECONDS:-3600}"
KEEP="${KEEP_DAYS_REMOTE:-30}"
DEST="s3:${S3_BUCKET:-}/db"

log() { echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) offsite: $*"; }

while true; do
  if [ -z "${RCLONE_CONFIG_S3_ACCESS_KEY_ID:-}" ] || [ -z "${RCLONE_CONFIG_S3_SECRET_ACCESS_KEY:-}" ] || [ -z "${S3_BUCKET:-}" ]; then
    log "S3 не настроен: задайте S3_ACCESS_KEY, S3_SECRET_KEY и S3_BUCKET в .env и выполните docker compose up -d offsite"
  else
    # --min-age 5m: не трогаем дамп, который прямо сейчас пишется; --max-age 72h: смотрим только свежие файлы.
    if rclone copy /backups "$DEST" --min-age 5m --max-age 72h --stats-one-line --stats-log-level NOTICE; then
      count="$(rclone lsf "$DEST" --files-only 2>/dev/null | wc -l)"
      log "ok: копирование завершено, файлов в S3: $count"
    else
      log "ОШИБКА копирования в S3 (проверьте ключи, имя бакета и сеть)"
    fi
    if ! rclone delete "$DEST" --min-age "${KEEP}d"; then
      log "ОШИБКА очистки старых копий в S3"
    fi
  fi
  sleep "$INTERVAL"
done
