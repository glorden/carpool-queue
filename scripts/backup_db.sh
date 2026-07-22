#!/bin/bash
# Ежедневный бэкап carpool.db через "cron" на проде (см. ARCHITECTURE.md / DEPLOY.md).
#
# Хранение:
# - самая свежая копия хранится всегда, независимо от даты;
# - более старые копии переживают чистку, только если попадают в сетку
#   "раз в 10 дней" от фиксированной точки отсчёта (EPOCH) — так со временем
#   остаются срезы за все периоды, а не только последние N дней.
set -euo pipefail

cd "$(dirname "$0")/.."

DB_FILE="carpool.db"
BACKUP_DIR="backups"
EPOCH="2026-01-01"

mkdir -p "$BACKUP_DIR"

TODAY=$(date +%F)
BACKUP_FILE="$BACKUP_DIR/carpool-$TODAY.db"

sqlite3 "$DB_FILE" ".backup '$BACKUP_FILE'"

epoch_s=$(date -d "$EPOCH" +%s)

for f in "$BACKUP_DIR"/carpool-*.db; do
    [ -e "$f" ] || continue

    fdate=$(basename "$f" .db | sed 's/^carpool-//')
    [ "$fdate" = "$TODAY" ] && continue  # свежую копию не трогаем

    file_s=$(date -d "$fdate" +%s 2>/dev/null) || continue
    days_since_epoch=$(( (file_s - epoch_s) / 86400 ))

    if [ $(( days_since_epoch % 10 )) -ne 0 ]; then
        rm -f "$f"
    fi
done
