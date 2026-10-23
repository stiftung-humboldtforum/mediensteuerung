#!/bin/sh
set -eu

# CN for the MQTT leaf certificates. Passed as $1 by the compose service
# (interpolated from the host $HOSTNAME); falls back to the container hostname.
CN="${1:-${HOSTNAME:-$(hostname)}}"

# Mounted from ./backend/broker/tls — the broker and every MQTT client read this
# directory as /opt/tls.
OUT="/opt/tls-out"
mkdir -p "$OUT"

cd /tls-gen/basic

# Generate a fresh CA plus server and client key pairs (tls-gen names the leaf
# files server_<CN>_*.pem / client_<CN>_*.pem), then alias them to the generic
# names every consumer expects (server_certificate.pem, client_key.pem, ...).
make CN="$CN"
make CN="$CN" alias-leaf-artifacts

# Copy the canonical names into the shared TLS directory:
#   ca_certificate.pem      -> mosquitto.conf (cafile) + every MQTT client
#   server_certificate.pem  -> mosquitto.conf (certfile, broker listener)
#   server_key.pem          -> mosquitto.conf (keyfile, broker listener)
#   client_certificate.pem  -> api/manager/calendar/knx/fac MQTT clients
#   client_key.pem          -> api/manager/calendar/knx/fac MQTT clients
cp result/ca_certificate.pem     "$OUT/ca_certificate.pem"
cp result/server_certificate.pem "$OUT/server_certificate.pem"
cp result/server_key.pem         "$OUT/server_key.pem"
cp result/client_certificate.pem "$OUT/client_certificate.pem"
cp result/client_key.pem         "$OUT/client_key.pem"

# The broker and clients run as non-root users and must be able to read these.
chmod 0644 "$OUT/ca_certificate.pem" \
           "$OUT/server_certificate.pem" "$OUT/server_key.pem" \
           "$OUT/client_certificate.pem" "$OUT/client_key.pem"

# Fail loudly if anything expected is missing or empty.
for f in ca_certificate.pem server_certificate.pem server_key.pem \
         client_certificate.pem client_key.pem; do
  if [ ! -s "$OUT/$f" ]; then
    echo "tls-gen: expected $OUT/$f was not produced" >&2
    exit 1
  fi
done

echo "tls-gen: wrote MQTT certificates for CN=$CN to $OUT"
