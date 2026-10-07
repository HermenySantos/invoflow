#!/bin/sh
# Bring up the production stack locally and leave it running on https://localhost.
set -eu
cd "$(dirname "$0")"
cp rehearsal.env ../.env
dc() { docker compose -p invoflow-rehearsal -f ../docker-compose.prod.yml -f docker-compose.rehearsal.yml --env-file ../.env "$@"; }
dc build
dc up -d db s3
dc run --rm api alembic upgrade head
dc up -d
echo "Up: https://localhost  (stop with: docker compose -p invoflow-rehearsal down -v)"
