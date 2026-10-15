#!/bin/sh
set -eu
# A dedicated application owner can migrate its own schema, but cannot create
# roles/databases or become a database superuser. Secrets never enter argv.
IFS= read -r app_db_password < /run/secrets/database_password
case "$app_db_password" in
  ''|*[!a-f0-9]*) printf 'Invalid generated application secret.\n' >&2; exit 1 ;;
esac
printf "CREATE ROLE cloudsentinel LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD '%s';\nALTER DATABASE cloudsentinel OWNER TO cloudsentinel;\n" "$app_db_password" | psql -v ON_ERROR_STOP=1 --username cloudsentinel_owner --dbname cloudsentinel
