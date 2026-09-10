#!/bin/sh
set -eu

case "${1:-}" in
    init)
        python manage.py check
        python manage.py migrate --noinput
        python manage.py seed_models
        python manage.py collectstatic --noinput
        ;;
    serve)
        socket=/run/libretiles/backend.sock
        rm -f -- "$socket"
        umask 0007
        exec daphne --endpoint "unix:${socket}:mode=0770" --proxy-headers \
            --access-log /dev/null --websocket-max-message-size 1048576 \
            config.asgi:application
        ;;
    *)
        printf '%s\n' 'usage: start.sh init|serve' >&2
        exit 2
        ;;
esac
