#!/bin/sh
set -e

# Replace environment variables in nginx config template
envsubst '${FASTAPI_BACKEND_URL}' < /etc/nginx/templates/default.conf.template > /etc/nginx/conf.d/default.conf

# Execute the main command
exec "$@"
