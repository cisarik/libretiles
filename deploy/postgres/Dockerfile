FROM postgres:16.15-alpine3.24@sha256:cf78e76683b9ca8c5733cbbdce6c9262b45b6767934dd0a95e671f9a0fc20685

COPY --chown=70:70 backup.sh /usr/local/bin/backup.sh
COPY --chown=70:70 restore.sh /usr/local/bin/restore.sh
RUN mkdir -p /backups \
    && chown 70:70 /backups \
    && chmod 0700 /backups \
    && chmod 0555 /usr/local/bin/backup.sh /usr/local/bin/restore.sh
USER 70:70
