#!/bin/bash
# shellcheck disable=SC2046
# shellcheck disable=SC2164
WRK_DOCKER_DIR="$(dirname $(cd $(dirname "$0"); pwd))"
export WRK_DOCKER_DIR
ENV_FILE=${WRK_DOCKER_DIR}/.env

if [ ! -f "${ENV_FILE}" ]; then
    cp "${WRK_DOCKER_DIR}/.env.in" "${ENV_FILE}"
fi

# shellcheck disable=SC1090
source "$ENV_FILE"
# Export variables for docker compose
export CONTAINER_NAME IMAGE_NAME CONTAINER_USER CONTAINER_NETWORK PUID PGID UID_GID_DEFAULT INSTALL_FOLDER_CLIENT WRK_DOCKER_DIR

# Create user if doesn't exist (use PUID/PGID from .env.in if available)
if ! id -u "${CONTAINER_USER}" > /dev/null 2>&1; then
	sudo adduser "${CONTAINER_USER}" --disabled-password --gecos '' --no-create-home --uid "${PUID:-${UID_GID_DEFAULT}}"
	sudo usermod "${CONTAINER_USER}" -s /sbin/nologin
fi

docker stop "${CONTAINER_NAME}"
docker compose -f "${WRK_DOCKER_DIR}/docker-compose.yaml" down --remove-orphans
docker rmi "${IMAGE_NAME}"
docker network ls | grep "${CONTAINER_NETWORK}"
if [ $? -eq 1 ]; then
  docker network rm "${CONTAINER_NETWORK}"
fi

docker compose -f "${WRK_DOCKER_DIR}/docker-compose.yaml" up -d
