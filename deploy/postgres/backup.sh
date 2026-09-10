#!/bin/sh
set -eu

load_password() {
    path=${DB_PASSWORD_FILE:-}
    [ -n "$path" ] && [ -f "$path" ] && [ ! -L "$path" ] || {
        printf '%s\n' 'DB_PASSWORD_FILE must name a regular file' >&2
        exit 1
    }
    [ "$(wc -c <"$path")" -le 8192 ] || {
        printf '%s\n' 'database password file is too large' >&2
        exit 1
    }
    IFS= read -r PGPASSWORD <"$path" || [ -n "${PGPASSWORD:-}" ]
    [ -n "${PGPASSWORD:-}" ] || {
        printf '%s\n' 'database password is empty' >&2
        exit 1
    }
    export PGPASSWORD
}

validate_name() {
    case "$1" in
        *.dump) ;;
        *) printf '%s\n' 'backup name must end in .dump' >&2; exit 2 ;;
    esac
    case "$1" in
        ''|.*|*/*|*[!A-Za-z0-9._-]*)
            printf '%s\n' 'backup name contains unsafe characters' >&2
            exit 2
            ;;
    esac
}

case "${1:-}" in
    backup)
        name=${2:-}
        validate_name "$name"
        load_password
        destination="/backups/$name"
        temporary="/backups/.${name}.tmp.$$"
        [ ! -e "$destination" ] || {
            printf '%s\n' 'backup destination already exists' >&2
            exit 1
        }
        trap 'rm -f -- "$temporary"' EXIT HUP INT TERM
        pg_dump -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" \
            --format=custom --no-owner --no-acl --file="$temporary"
        pg_restore --list "$temporary" >/dev/null
        chmod 0600 "$temporary"
        mv "$temporary" "$destination"
        trap - EXIT HUP INT TERM
        printf '%s\n' "backup verified: $name"
        ;;
    verify)
        name=${2:-}
        validate_name "$name"
        [ -f "/backups/$name" ] && [ ! -L "/backups/$name" ] || exit 1
        pg_restore --list "/backups/$name" >/dev/null
        printf '%s\n' "backup verified: $name"
        ;;
    *)
        printf '%s\n' 'usage: backup.sh backup|verify NAME.dump' >&2
        exit 2
        ;;
esac
