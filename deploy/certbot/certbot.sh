#!/bin/sh
set -eu

marker=/var/run/libretiles-certbot/reload-request
heartbeat=/var/run/libretiles-certbot/renewal-heartbeat

validate_inputs() {
    case "${DOMAIN:-}" in
        ''|example.invalid|.*|*.|*[!A-Za-z0-9.-]*)
            printf '%s\n' 'DOMAIN must be a concrete DNS hostname' >&2
            exit 1
            ;;
    esac
    case "${ACME_EMAIL:-}" in
        ''|*@example.invalid|*[!A-Za-z0-9@._+-]*)
            printf '%s\n' 'ACME_EMAIL must be a concrete address' >&2
            exit 1
            ;;
    esac
}

certbot_command() {
    certbot --config-dir /etc/letsencrypt --work-dir /tmp/certbot-work \
        --logs-dir /tmp/certbot-logs "$@"
}

normalize_certificate_permissions() {
    fullchain="/etc/letsencrypt/live/${DOMAIN}/fullchain.pem"
    privkey="/etc/letsencrypt/live/${DOMAIN}/privkey.pem"
    archive="/etc/letsencrypt/archive/${DOMAIN}"
    for directory in /etc/letsencrypt /etc/letsencrypt/live \
        /etc/letsencrypt/archive "/etc/letsencrypt/live/${DOMAIN}" "$archive"; do
        [ -d "$directory" ] || {
            printf '%s\n' "certificate directory is absent: $directory" >&2
            exit 1
        }
        [ "$(stat -c '%g' "$directory")" = "10001" ] || {
            printf '%s\n' "certificate directory has unexpected group: $directory" >&2
            exit 1
        }
        chmod 0750 "$directory"
    done
    for certificate in "$fullchain" "$privkey"; do
        [ -s "$certificate" ] || {
            printf '%s\n' "certificate file is absent: $certificate" >&2
            exit 1
        }
        [ "$(stat -c '%g' "$certificate")" = "10001" ] || {
            printf '%s\n' "certificate file has unexpected group: $certificate" >&2
            exit 1
        }
    done
    chmod 0640 "$fullchain" "$privkey"
}

case "${1:-}" in
    issue)
        validate_inputs
        [ ! -e "/etc/letsencrypt/live/${DOMAIN}" ] || {
            printf '%s\n' 'certificate state already exists; use renewal' >&2
            exit 1
        }
        certbot_command certonly --non-interactive --agree-tos --no-eff-email \
            --email "$ACME_EMAIL" --webroot -w /var/www/certbot -d "$DOMAIN"
        normalize_certificate_permissions
        touch "$marker"
        ;;
    renew-once)
        validate_inputs
        [ -s "/etc/letsencrypt/live/${DOMAIN}/fullchain.pem" ] || {
            printf '%s\n' 'initial certificate is absent' >&2
            exit 1
        }
        certbot_command renew --non-interactive --quiet \
            --deploy-hook "/usr/local/bin/certbot.sh signal-reload"
        touch "$heartbeat"
        ;;
    renew-loop)
        validate_inputs
        while :; do
            "$0" renew-once
            sleep 43200 &
            wait "$!"
        done
        ;;
    signal-reload)
        validate_inputs
        normalize_certificate_permissions
        touch "$marker"
        ;;
    health)
        find "$heartbeat" -mmin -1500 -print -quit 2>/dev/null | grep -q .
        ;;
    *)
        printf '%s\n' 'usage: certbot.sh issue|renew-once|renew-loop|health' >&2
        exit 2
        ;;
esac
