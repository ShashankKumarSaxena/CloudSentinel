#!/bin/sh
set -eu
# PostgreSQL requires server keys owned by its runtime user with private modes.
# Copy from read-only Compose secrets into a separate private named volume.
umask 077
mkdir -p /var/lib/postgresql/tls
cp /run/secrets/database.crt /var/lib/postgresql/tls/server.crt
cp /run/secrets/database.key /var/lib/postgresql/tls/server.key
chmod 600 /var/lib/postgresql/tls/server.*
chown -R postgres:postgres /var/lib/postgresql/tls
exec docker-entrypoint.sh postgres \
  -c ssl=on \
  -c ssl_cert_file=/var/lib/postgresql/tls/server.crt \
  -c ssl_key_file=/var/lib/postgresql/tls/server.key \
  -c hba_file=/etc/postgresql/cloudsentinel_hba.conf
