#!/bin/sh
set -eu

template=/opt/libretiles/nginx.conf.template
config=/run/nginx-master/nginx.conf
proxy_headers=/run/nginx-master/nginx-proxy-headers.conf
callback_headers=/run/nginx-master/nginx-callback-headers.conf
reload_marker=/var/run/libretiles-certbot/reload-request

validate_domain() {
    case "${DOMAIN:-}" in
        ''|example.invalid|.*|*.|*[!A-Za-z0-9.-]*)
            printf '%s\n' 'DOMAIN must be a concrete DNS hostname' >&2
            exit 1
            ;;
    esac
}

write_headers() {
    cat >"$proxy_headers" <<'EOF'
proxy_http_version 1.1;
proxy_set_header Host $host;
proxy_set_header X-Forwarded-Host $host;
proxy_set_header X-Forwarded-Proto $scheme;
proxy_set_header X-Forwarded-Port 443;
proxy_set_header X-Forwarded-For $remote_addr;
proxy_set_header X-Real-IP $remote_addr;
proxy_set_header Forwarded "";
proxy_set_header Upgrade "";
proxy_set_header Connection "";
proxy_cache off;
EOF
    cat >"$callback_headers" <<EOF
proxy_http_version 1.1;
proxy_set_header Host ${DOMAIN};
proxy_set_header X-Forwarded-Host ${DOMAIN};
proxy_set_header X-Forwarded-Proto https;
proxy_set_header X-Forwarded-Port 443;
proxy_set_header X-Forwarded-For \$remote_addr;
proxy_set_header X-Real-IP \$remote_addr;
proxy_set_header Forwarded "";
proxy_set_header Upgrade "";
proxy_set_header Connection "";
proxy_cache off;
EOF
    chmod 0440 "$proxy_headers" "$callback_headers"
}

render_config() {
    fullchain="/etc/letsencrypt/live/${DOMAIN}/fullchain.pem"
    privkey="/etc/letsencrypt/live/${DOMAIN}/privkey.pem"
    if [ -s "$fullchain" ] && [ -s "$privkey" ]; then
        sed -e "s/__DOMAIN__/${DOMAIN}/g" \
            -e 's|__HTTP_FALLBACK__|301 https://'"${DOMAIN}"'$request_uri|' \
            -e '/# TLS_BEGIN/d' -e '/# TLS_END/d' "$template" >"$config.new"
    else
        sed -e "s/__DOMAIN__/${DOMAIN}/g" \
            -e 's/__HTTP_FALLBACK__/503/' \
            -e '/# TLS_BEGIN/,/# TLS_END/d' "$template" >"$config.new"
    fi
    chmod 0440 "$config.new"
    mv -f "$config.new" "$config"
}

watch_certificates() {
    while sleep 5; do
        [ -f "$reload_marker" ] || continue
        render_config
        if nginx -t -c "$config"; then
            nginx -s reload -c "$config"
            rm -f "$reload_marker"
        fi
    done
}

validate_domain
write_headers
render_config
nginx -t -c "$config"
watch_certificates &
exec nginx -c "$config" -g 'daemon off;'
