#!/bin/bash
# Deploy or refresh the rektslug core runtime from the local repo checkout.

set -euo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PROJECT_DIR="$(CDPATH= cd -- "${SCRIPT_DIR}/.." && pwd)"
. "$SCRIPT_DIR/lib/runtime_env.sh"

lh_load_runtime_env host

cd "$PROJECT_DIR"

temp_env_link=0
if [ ! -f ".env" ]; then
    if [ -f "${SHARED_ENV_FILE}" ]; then
        ln -sf "${SHARED_ENV_FILE}" .env
        temp_env_link=1
    elif [ -f "${PROJECT_DIR}/.env.example" ]; then
        ln -sf "${PROJECT_DIR}/.env.example" .env
        temp_env_link=1
    else
        echo "Missing .env in ${PROJECT_DIR}, shared env file ${SHARED_ENV_FILE}, and .env.example fallback. Configure runtime values first." >&2
        exit 1
    fi
fi

cleanup() {
    if [ "$temp_env_link" -eq 1 ]; then
        rm -f "${PROJECT_DIR}/.env"
    fi
}

trap cleanup EXIT

docker compose config >/dev/null
docker compose pull rektslug-api rektslug-sync
docker compose up -d --force-recreate rektslug-api rektslug-sync

if ! docker inspect rektslug-api --format '{{range .Mounts}}{{println .Destination}}{{end}}' | grep -qx '/app/data'; then
    echo "rektslug-api is missing required /app/data runtime mount after deploy." >&2
    exit 1
fi

docker compose ps
