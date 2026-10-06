#!/bin/bash

# The current docker-compose.yml uses build:, network_mode: host and cap_add,
# which `docker stack deploy` (Swarm) silently drops or rejects. The supported
# path is plain Compose.
set -a
source .env
set +a
docker compose up -d --build
