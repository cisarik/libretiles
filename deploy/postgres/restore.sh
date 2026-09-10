#!/bin/sh
set -eu

case "${1:-}" in
    restore) ;;
    *) printf '%s\n' 'usage: restore.sh restore --confirm-disposable NAME.dump' >&2; exit 2 ;;
esac
[ "${2:-}" = "--confirm-disposable" ] || {
    printf '%s\n' 'restore requires --confirm-disposable' >&2
    exit 2
}
name=${3:-}
case "$name" in
    *.dump) ;;
    *) printf '%s\n' 'restore source must end in .dump' >&2; exit 2 ;;
esac
case "$name" in
    ''|.*|*/*|*[!A-Za-z0-9._-]*)
        printf '%s\n' 'restore source contains unsafe characters' >&2
        exit 2
        ;;
esac
[ "${RESTORE_DISPOSABLE:-}" = "1" ] || {
    printf '%s\n' 'RESTORE_DISPOSABLE=1 is required' >&2
    exit 1
}
[ -n "${RESTORE_DB_HOST:-}" ] && [ "$RESTORE_DB_HOST" != "${DB_HOST:-}" ] || {
    printf '%s\n' 'restore target must differ from the source database host' >&2
    exit 1
}
[ -f "/backups/$name" ] && [ ! -L "/backups/$name" ] || {
    printf '%s\n' 'restore source is not a regular file' >&2
    exit 1
}
path=${DB_PASSWORD_FILE:-}
[ -n "$path" ] && [ -f "$path" ] && [ ! -L "$path" ] || exit 1
IFS= read -r PGPASSWORD <"$path" || [ -n "${PGPASSWORD:-}" ]
[ -n "${PGPASSWORD:-}" ] || exit 1
export PGPASSWORD

tables=$(psql -h "$RESTORE_DB_HOST" -U "$RESTORE_DB_USER" -d "$RESTORE_DB_NAME" \
    -Atqc "select count(*) from pg_catalog.pg_tables where schemaname = 'public'")
[ "$tables" = "0" ] || {
    printf '%s\n' 'restore target is not empty' >&2
    exit 1
}
pg_restore -h "$RESTORE_DB_HOST" -U "$RESTORE_DB_USER" -d "$RESTORE_DB_NAME" \
    --exit-on-error --no-owner --no-acl "/backups/$name"
printf '%s\n' "restore completed into disposable target: $name"
