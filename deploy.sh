#!/bin/bash

# The current docker-compose.yml uses build:, network_mode: host and cap_add,
# which `docker stack deploy` (Swarm) silently drops or rejects. The supported
# path is plain Compose.
#
# Compose reads .env itself (sourcing it here broke values with spaces or special
# characters). Compose prefers the shell environment, though, and many shells
# export HOSTNAME as the short name: drop it so the .env value (FQDN, used for
# the certificate CN and the mounts) wins.
if grep -q '^HOSTNAME=' .env; then unset HOSTNAME; fi
docker compose up -d --build
