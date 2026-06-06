#!/usr/bin/env bash
#
# Baby Buddy restore.
# Restores a backup (database + media) created by backup.sh.
# Run it from the directory that contains docker-compose.yml.
#
#   ./scripts/restore.sh            # restore the most recent backup
#   ./scripts/restore.sh 20260606-143000   # restore a specific backup (by name)
#   ./scripts/restore.sh ./backups/20260606-143000   # ...or by path
#   ./scripts/restore.sh --list     # list available backups and exit
#
# This OVERWRITES the current database and media. It prints the code revision
# the backup was taken at so you can `git checkout` it if needed (the schema
# must match the code).
#
set -euo pipefail

SERVICE="babybuddy"
BACKUP_ROOT="./backups"

list_backups() {
  ls -1dt "${BACKUP_ROOT}"/*/ 2>/dev/null | while read -r d; do
    d="${d%/}"
    info=""
    [ -f "${d}/git-commit-info.txt" ] && info="$(cat "${d}/git-commit-info.txt")"
    printf "  %s   %s\n" "$(basename "${d}")" "${info}"
  done
}

ARG="${1:-}"

# --list: show what's available, then exit.
if [ "${ARG}" = "-l" ] || [ "${ARG}" = "--list" ] || [ "${ARG}" = "list" ]; then
  echo "Available backups (newest first):"
  list_backups
  exit 0
fi

# Resolve which backup to restore.
if [ -n "${ARG}" ]; then
  if [ -d "${ARG}" ]; then
    SRC="${ARG}"
  elif [ -d "${BACKUP_ROOT}/${ARG}" ]; then
    SRC="${BACKUP_ROOT}/${ARG}"
  else
    echo "Backup not found: ${ARG}" >&2
    echo "Available backups (newest first):" >&2
    list_backups >&2
    exit 1
  fi
else
  SRC="$(ls -1dt "${BACKUP_ROOT}"/*/ 2>/dev/null | head -1 || true)"
  if [ -z "${SRC}" ]; then
    echo "No backups found in ${BACKUP_ROOT}." >&2
    exit 1
  fi
fi
SRC="${SRC%/}"

if [ ! -f "${SRC}/db.sqlite3" ]; then
  echo "No db.sqlite3 found in ${SRC} — not a valid backup." >&2
  exit 1
fi

echo "==> Restoring backup: ${SRC}"
[ -f "${SRC}/git-commit-info.txt" ] && \
  echo "    taken at code revision: $(cat "${SRC}/git-commit-info.txt")"

printf "Restore this backup? This OVERWRITES current data. [y/N] "
read -r ans
case "${ans}" in
  y | Y) ;;
  *) echo "Aborted."; exit 1 ;;
esac

echo "==> Stopping ${SERVICE}"
docker compose stop "${SERVICE}"

echo "==> Restoring database"
docker compose cp "${SRC}/db.sqlite3" "${SERVICE}:/app/data/db.sqlite3"

# Drop any stale SQLite WAL side-files so they can't shadow the restored DB.
# (Usually none exist; Baby Buddy's default journal mode isn't WAL.)
docker compose run --rm --no-deps --entrypoint sh "${SERVICE}" -c \
  "rm -f /app/data/db.sqlite3-wal /app/data/db.sqlite3-shm" >/dev/null 2>&1 || true

if [ -d "${SRC}/media" ]; then
  echo "==> Restoring media"
  docker compose cp "${SRC}/media/." "${SERVICE}:/app/media"
fi

echo "==> Starting ${SERVICE}"
docker compose up -d "${SERVICE}"

echo
echo "==> Restore complete from ${SRC}"
if [ -f "${SRC}/git-commit.txt" ]; then
  echo
  echo "IMPORTANT — match the code to this restored database:"
  echo "    git checkout $(cat "${SRC}/git-commit.txt")"
  echo "    docker compose up -d --build"
fi
