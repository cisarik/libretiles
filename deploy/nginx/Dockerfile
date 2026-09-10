FROM nginx:1.30.4-alpine3.24@sha256:dc5069ad14f19660b141b21236140b91656bf89bbc3e2417c70ae650cd66104c

RUN addgroup -g 10001 -S libretiles \
    && adduser -u 10002 -S -D -H -G libretiles edge \
    && mkdir -p /run/libretiles /run/nginx-master \
        /var/cache/nginx/client-body /var/cache/nginx/proxy \
        /var/cache/nginx/fastcgi /var/cache/nginx/uwsgi /var/cache/nginx/scgi \
        /etc/letsencrypt /var/www/certbot /var/run/libretiles-certbot \
    && chown -R 10002:10001 /run/libretiles /etc/letsencrypt /var/www/certbot /var/run/libretiles-certbot \
    && chown -R 10002:10001 /var/cache/nginx \
    && chown 0:10001 /run/nginx-master \
    && chmod 0770 /run/libretiles /var/run/libretiles-certbot \
    && chmod 0750 /run/nginx-master /etc/letsencrypt /var/www/certbot \
    && chmod 0770 /var/cache/nginx/client-body /var/cache/nginx/proxy \
        /var/cache/nginx/fastcgi /var/cache/nginx/uwsgi /var/cache/nginx/scgi \
    && rm -f /etc/nginx/conf.d/default.conf
COPY --chown=10002:10001 nginx.conf.template /opt/libretiles/nginx.conf.template
COPY --chown=10002:10001 entrypoint.sh /usr/local/bin/libretiles-nginx
RUN chmod 0555 /usr/local/bin/libretiles-nginx

# Master process runs as root (UID 0) so Docker supplies the single
# NET_BIND_SERVICE effective capability needed to bind 80/443/444.
# Request workers drop to the unprivileged edge identity via the
# "user edge libretiles;" directive in nginx.conf.template.
USER 0:10001

ENTRYPOINT ["/usr/local/bin/libretiles-nginx"]
