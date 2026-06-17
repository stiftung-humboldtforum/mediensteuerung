#!/bin/bash

docker compose -f docker-compose-certs.yml build
# HTTPS certificates (mkcert) served by the API
docker compose -f docker-compose-certs.yml run --rm mkcert
# MQTT CA + server + client certificates (rabbitmq/tls-gen) for the broker
docker compose -f docker-compose-certs.yml run --rm tls-gen
