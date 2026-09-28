#!/bin/sh
# Consistent, cold backup. Expect a short publishing outage while services stop.
set -eu
cd "$(dirname "$0")"
test -f .env || { echo 'Run ./init.sh first.' >&2; exit 1; }
command -v docker >/dev/null
mkdir -p backups
stamp=$(date -u +%Y%m%dT%H%M%SZ)
archive="backups/postiz-$stamp.tar.gz"
tmp="$archive.partial"
[ ! -e "$archive" ] || { echo "Backup already exists: $archive" >&2; exit 1; }
volumes='postiz_config postiz_uploads postiz_db redis_data temporal_db temporal_search'
cleanup() {
  docker compose --env-file .env -f compose.yaml up -d >/dev/null 2>&1 || true
  rm -f "$tmp"
}
trap cleanup EXIT HUP INT TERM
docker compose --env-file .env -f compose.yaml stop
for name in $volumes; do
  docker volume inspect "postiz-mac-mini_$name" >/dev/null
done
docker run --rm \
  -v "$(pwd)/backups:/backup" \
  $(for name in $volumes; do printf ' -v postiz-mac-mini_%s:/data/%s:ro' "$name" "$name"; done) \
  alpine:3.21 sh -c "cd /data && tar -czf /backup/$(basename "$tmp") $volumes"
tar -tzf "$tmp" >/dev/null
mv "$tmp" "$archive"
trap - EXIT HUP INT TERM
docker compose --env-file .env -f compose.yaml up -d
echo "Backup: $archive"
echo 'Copy this archive and .env to encrypted storage outside the Mac mini.'
