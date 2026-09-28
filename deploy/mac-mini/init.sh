#!/bin/sh
set -eu
cd "$(dirname "$0")"
domain=${1:-}
if [ -z "$domain" ] || [ "$domain" = postiz.example.com ]; then
  echo 'Usage: ./init.sh postiz.yourdomain.com' >&2
  exit 1
fi
if [ -e .env ]; then
  echo '.env already exists; refusing to replace credentials.' >&2
  exit 1
fi
case "$domain" in
  *[!a-zA-Z0-9.-]*|.*|*..*|*.) echo 'Invalid domain.' >&2; exit 1 ;;
  *.*) ;;
  *) echo 'Use a full domain name.' >&2; exit 1 ;;
esac
umask 077
jwt=$(openssl rand -hex 48)
postiz_db=$(openssl rand -hex 32)
temporal_db=$(openssl rand -hex 32)
cat > .env <<EOF
POSTIZ_DOMAIN=$domain
JWT_SECRET=$jwt
POSTIZ_DB_PASSWORD=$postiz_db
TEMPORAL_DB_PASSWORD=$temporal_db
DISABLE_REGISTRATION=true
FACEBOOK_APP_ID=
FACEBOOK_APP_SECRET=
YOUTUBE_CLIENT_ID=
YOUTUBE_CLIENT_SECRET=
TIKTOK_CLIENT_ID=
TIKTOK_CLIENT_SECRET=
API_LIMIT=30
EOF
echo "Created private .env for $domain"
