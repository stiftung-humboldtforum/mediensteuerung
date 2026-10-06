FROM debian:trixie-slim

# rabbitmq/tls-gen needs git (to fetch itself), make, openssl and python3.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates git make openssl python3 \
    && rm -rf /var/lib/apt/lists/*

# Certificate generator for the MQTT CA, server and client certificates.
# Pinned to a commit for reproducible certs (HEAD would silently change key/algo/filenames).
RUN git clone https://github.com/rabbitmq/tls-gen.git /tls-gen \
    && git -C /tls-gen checkout 8152e35b98160c37c9c7a6a43279c30e6dc5cb40

COPY generate.sh /generate.sh
RUN chmod +x /generate.sh

WORKDIR /tls-gen/basic
