# pg_dump 16 (matches the db container) + the AWS CLI for R2's S3 API.
FROM postgres:16-alpine
RUN apk add --no-cache aws-cli
COPY backup.sh restore.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/backup.sh /usr/local/bin/restore.sh
CMD ["backup.sh", "--daily"]
