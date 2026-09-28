#!/bin/sh
set -eu
cd "$(dirname "$0")"
test -f .env || { echo 'Run ./init.sh first.' >&2; exit 1; }
domain=$(sed -n 's/^POSTIZ_DOMAIN=//p' .env | head -1)
case "$domain" in
  ''|postiz.example.com) echo 'Set your real domain first.' >&2; exit 1 ;;
esac
docker compose --env-file .env -f compose.yaml config --quiet
echo 'Compose configuration: OK'
running=$(docker compose --env-file .env -f compose.yaml ps --status running --services | sort)
expected=$(printf '%s\n' postiz postiz-db redis temporal temporal-db temporal-search | sort)
if [ "$running" != "$expected" ]; then
  docker compose --env-file .env -f compose.yaml ps
  echo 'One or more services are not running.' >&2
  exit 1
fi
for service in postiz postiz-db redis temporal-db; do
  container=$(docker compose --env-file .env -f compose.yaml ps -q "$service")
  health=$(docker inspect --format '{{.State.Health.Status}}' "$container")
  if [ "$health" != healthy ]; then
    echo "$service health: $health" >&2
    exit 1
  fi
done
echo 'Containers: running and healthy'
curl --fail --silent --show-error --max-time 15 http://127.0.0.1:4007/api/monitor/queue/default >/dev/null
echo 'Local HTTP: OK'
curl --fail --silent --show-error --max-time 15 "https://$domain/api/monitor/queue/default" >/dev/null
echo 'Public HTTPS: OK'
