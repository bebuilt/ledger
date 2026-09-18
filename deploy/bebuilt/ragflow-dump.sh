#!/usr/bin/env bash
# Nightly consistent dump of RAGFlow's MySQL onto this box's own disk, so every Hetzner backup holds one
# clean copy (Molzer backups ruling, 2026-09-18). Keeps the last three. The object store and the index are
# carried by the Hetzner backup itself.
#
# TODO(T22): pause the ingestion worker around the dump once it exists, so the dump and the object store
# share a point in time.
set -euo pipefail
DIR=/var/backups/ragflow
KEEP=3
OUT="$DIR/mysql-$(date -u +%Y%m%dT%H%MZ).sql.gz"

# The password stays inside the container: MYSQL_ROOT_PASSWORD is already in its environment.
MYSQL="$(docker ps -q -f label=com.docker.compose.project=ragflow -f label=com.docker.compose.service=mysql)"
[ -n "$MYSQL" ] || { echo "$(date -u +%FT%TZ) no running mysql container for project ragflow" >&2; exit 1; }
docker exec "$MYSQL" sh -c \
  'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysqldump -uroot --single-transaction --routines --events --triggers --all-databases' \
  | gzip -6 > "$OUT.tmp"
gzip -t "$OUT.tmp"
mv "$OUT.tmp" "$OUT"
ls -1t "$DIR"/mysql-*.sql.gz | tail -n +$((KEEP + 1)) | xargs -r rm -f
echo "$(date -u +%FT%TZ) dumped $(du -h "$OUT" | cut -f1) to $OUT; disk $(df -h / | awk 'NR==2{print $5}') used"
