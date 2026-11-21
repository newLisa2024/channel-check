#!/usr/bin/env bash
# Запускается на сервере из /opt/channel-check ПОСЛЕ git merge --ff-only.
# Пересобирает и перезапускает контейнеры, проверяет, что все сервисы живы.
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/channel-check}"
EXPECTED_SHA="${1:-}"
SERVICES="postgres redis bot worker backup offsite"

cd "$APP_DIR"

exec 9>/tmp/channel-check-deploy.lock
flock -n 9 || { echo "Другой деплой уже идёт, выхожу"; exit 1; }

HEAD_SHA="$(git rev-parse HEAD)"
echo "Деплою коммит $HEAD_SHA"
if [ -n "$EXPECTED_SHA" ] && [ "$EXPECTED_SHA" != "$HEAD_SHA" ]; then
  echo "Внимание: ожидался $EXPECTED_SHA, на сервере $HEAD_SHA (вероятно, в main уже есть более новый коммит)"
fi

docker compose up -d --build --remove-orphans
docker image prune -f >/dev/null

echo "Жду запуска сервисов..."
sleep 20

failed=0
for s in $SERVICES; do
  state="$(docker compose ps --format '{{.State}}' "$s" 2>/dev/null || true)"
  if [ "$state" != "running" ]; then
    echo "ОШИБКА: сервис $s в состоянии '${state:-нет контейнера}'"
    docker compose logs --tail=50 "$s" || true
    failed=1
  else
    echo "ok: $s"
  fi
done

[ "$failed" -eq 0 ] || exit 1
echo "Деплой $HEAD_SHA завершён"
