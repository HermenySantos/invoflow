#!/bin/sh
# Restore a backup into the database. DESTRUCTIVE: replaces current data.
#   restore.sh                       list available backups
#   restore.sh invoflow-YYYYmmdd-HHMMSS.dump --yes
set -eu

: "${BACKUP_BUCKET:?set BACKUP_BUCKET}"
export AWS_ACCESS_KEY_ID="${R2_ACCESS_KEY_ID:?}" AWS_SECRET_ACCESS_KEY="${R2_SECRET_ACCESS_KEY:?}" AWS_DEFAULT_REGION=auto
ENDPOINT="${BACKUP_ENDPOINT_URL:-https://${R2_ACCOUNT_ID}.r2.cloudflarestorage.com}"
s3() { aws --endpoint-url "$ENDPOINT" s3 "$@"; }

if [ $# -eq 0 ]; then
  s3 ls "s3://$BACKUP_BUCKET/"
  exit 0
fi
if [ "${2:-}" != "--yes" ]; then
  echo "This replaces the current database with $1. Re-run with --yes to confirm." >&2
  exit 1
fi

s3 cp --only-show-errors "s3://$BACKUP_BUCKET/$1" /tmp/restore.dump
pg_restore --clean --if-exists --no-owner --dbname "$PGDATABASE" /tmp/restore.dump
rm -f /tmp/restore.dump
echo "Restored $1"
