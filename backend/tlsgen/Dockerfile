FROM debian:bookworm-slim

# rabbitmq/tls-gen needs git (to fetch itself), make, openssl and python3.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates git make openssl python3 \
    && rm -rf /var/lib/apt/lists/*

# Certificate generator for the MQTT CA, server and client certificates.
RUN git clone --depth 1 https://github.com/rabbitmq/tls-gen.git /tls-gen

COPY generate.sh /generate.sh
RUN chmod +x /generate.sh

WORKDIR /tls-gen/basic
