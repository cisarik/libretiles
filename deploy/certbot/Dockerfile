FROM certbot/certbot:v5.8.0@sha256:f70ad0adbb7e117f0fe42a63c553f28ea451edabc0148757b6efcd9735acaa20

USER root
RUN mkdir -p /etc/letsencrypt /var/www/certbot /var/run/libretiles-certbot \
    && chown -R 10002:10001 /etc/letsencrypt /var/www/certbot /var/run/libretiles-certbot \
    && chmod 0770 /etc/letsencrypt /var/www/certbot /var/run/libretiles-certbot
COPY --chown=10002:10001 certbot.sh /usr/local/bin/certbot.sh
RUN chmod 0555 /usr/local/bin/certbot.sh
USER 10002:10001
ENV HOME=/tmp

ENTRYPOINT ["/usr/local/bin/certbot.sh"]
