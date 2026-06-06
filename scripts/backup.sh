#!/usr/bin/env bash
#
# Baby Buddy backup.
# Creates a consistent snapshot of the SQLite database + uploaded media in
#   ./backups/<timestamp>/
# Run it from the directory that contains docker-compose.yml.
#
#   ./scripts/backup.sh
#
set -euo pipefail

SERVICE="babybuddy"          # docker compose service / container name
BACKUP_ROOT="./backups"
KEEP=14                      # how many backups to retain (older ones pruned)

TS="$(date +%Y%m%d-%H%M%S)"
DEST="${BACKUP_ROOT}/${TS}"
mkdir -p "${DEST}"

echo "==> Backing up to ${DEST}"

# 1) Database. Prefer SQLite's online backup API (transactionally consistent,
#    no downtime). Fall back to a cold file copy if the container isn't running.
RUNNING="$(docker inspect -f '{{.State.Running}}' "${SERVICE}" 2>/dev/null || echo false)"
if [ "${RUNNING}" = "true" ]; then
  echo "    - database (online snapshot)"
  docker compose exec -T "${SERVICE}" python -c \
"import sqlite3
s = sqlite3.connect('/app/data/db.sqlite3')
d = sqlite3.connect('/tmp/_bb_backup.sqlite3')
s.backup(d); d.close(); s.close()"
  docker compose cp "${SERVICE}:/tmp/_bb_backup.sqlite3" "${DEST}/db.sqlite3"
  docker compose exec -T "${SERVICE}" rm -f /tmp/_bb_backup.sqlite3
else
  echo "    - database (cold copy; container not running)"
  docker compose cp "${SERVICE}:/app/data/db.sqlite3" "${DEST}/db.sqlite3"
fi

# 2) Uploaded media (photos).
echo "    - media"
docker compose cp "${SERVICE}:/app/media" "${DEST}/media" 2>/dev/null \
  || echo "      (no media directory to copy)"

# 3) Record the exact code revision so a restore can be matched with a checkout.
if git rev-parse HEAD >/dev/null 2>&1; then
  git rev-parse HEAD > "${DEST}/git-commit.txt"
  git log -1 --pretty='%h %s' > "${DEST}/git-commit-info.txt" || true
fi

echo "==> Done: ${DEST}"
[ -f "${DEST}/git-commit-info.txt" ] && \
  echo "    code revision: $(cat "${DEST}/git-commit-info.txt")"

# 4) Prune old backups, keeping the most recent ${KEEP}.
( ls -1dt "${BACKUP_ROOT}"/*/ 2>/dev/null || true ) \
  | tail -n +"$((KEEP + 1))" \
  | while read -r old; do
      echo "==> Pruning old backup: ${old}"
      rm -rf "${old}"
    done
