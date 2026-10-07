#!/bin/sh
# Dump the Invoflow database to R2.
#   backup.sh          one backup now
#   backup.sh --daily  run forever, one backup a day at BACKUP_HOUR_UTC, pruning old ones
set -eu

: "${BACKUP_BUCKET:?set BACKUP_BUCKET}"
: "${R2_ACCOUNT_ID:?set R2_ACCOUNT_ID}"
export AWS_ACCESS_KEY_ID="${R2_ACCESS_KEY_ID:?set R2_ACCESS_KEY_ID}"
export AWS_SECRET_ACCESS_KEY="${R2_SECRET_ACCESS_KEY:?set R2_SECRET_ACCESS_KEY}"
export AWS_DEFAULT_REGION=auto
ENDPOINT="${BACKUP_ENDPOINT_URL:-https://${R2_ACCOUNT_ID}.r2.cloudflarestorage.com}"
KEEP_DAYS="${BACKUP_KEEP_DAYS:-30}"

s3() { aws --endpoint-url "$ENDPOINT" s3 "$@"; }

backup_once() {
  name="invoflow-$(date -u +%Y%m%d-%H%M%S).dump"
  # Custom format: compressed, and pg_restore can restore it table by table.
  pg_dump --format=custom --no-owner --file "/tmp/$name"
  s3 cp --only-show-errors "/tmp/$name" "s3://$BACKUP_BUCKET/$name"
  rm -f "/tmp/$name"
  echo "$(date -u +%FT%TZ) backup uploaded: $name"
}

prune() {
  cutoff=$(date -u -d "@$(( $(date -u +%s) - KEEP_DAYS * 86400 ))" +%Y%m%d)
  s3 ls "s3://$BACKUP_BUCKET/" | awk '{print $4}' | grep '^invoflow-[0-9]\{8\}-' | while read -r key; do
    day=$(echo "$key" | cut -d- -f2)
    if [ "$day" -lt "$cutoff" ]; then
      s3 rm --only-show-errors "s3://$BACKUP_BUCKET/$key" && echo "pruned $key"
    fi
  done
}

if [ "${1:-}" != "--daily" ]; then
  backup_once
  exit 0
fi

hour="${BACKUP_HOUR_UTC:-3}"
echo "Daily backups at ${hour}:00 UTC to s3://$BACKUP_BUCKET (keeping ${KEEP_DAYS} days)"
while true; do
  now=$(date -u +%s)
  next=$(date -u -d "$(date -u +%Y-%m-%d) ${hour}:00:00" +%s)
  [ "$next" -le "$now" ] && next=$(( next + 86400 ))
  sleep $(( next - now ))
  backup_once || echo "$(date -u +%FT%TZ) BACKUP FAILED" >&2
  prune || echo "$(date -u +%FT%TZ) prune failed" >&2
done
