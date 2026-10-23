#!/bin/bash

# Never overwrite an existing installation's .env: a new one would replace every
# internal secret (database user, JWT secret, system user) with fresh random values.
if [ -e .env ]; then
  echo ".env already exists, left unchanged. Move it away to create a new one."
  exit 0
fi

# Write a key with its value over the placeholder line "# <key>=..." from
# .env.example. The value is written literally (no sed escaping) and in single
# quotes, so Compose does not interpolate a $ in it; a single quote inside cannot
# be written that way.
setze() {
  case "$2" in *"'"*) echo "$1: the value must not contain a single quote" >&2; exit 1 ;; esac
  KEY="$1" VALUE="$2" awk 'BEGIN { k = ENVIRON["KEY"]; v = ENVIRON["VALUE"]; q = sprintf("%c", 39) }
    !done && index($0, "# " k "=") == 1 { print k "=" q v q; done = 1; next } { print }' .env > .env.tmp &&
    mv .env.tmp .env
}

# Generate a 32 character random string
generate_random_string() {
  cat /dev/urandom | tr -dc 'A-Za-z0-9' | head -c 32
}

# Get the FQDN of the system running the script
fqdn=$(hostname -f)

# Prompt user for specific values
read -r -p "Enter the URL of the NetBox instance (e.g., 'https://netbox.example.com'): " netbox_url
read -r -p "Enter your NetBox username: " username
read -rs -p "Enter your NetBox password: " password
echo
read -r -p "Enter KNX Gateway IP: " knx_gateway_ip
read -r -p "Enter path to knxkeys file (exported from ETS): " knxkeys_file_path
read -rs -p "Enter knxkeys password: " knxkeys_password
echo
read -rs -p "Enter PJLink password: " pjlink_password
echo
# Both communities must match the devices: the PDUs and the fire alarm panel (BMZ).
read -rs -p "Enter the SNMP community of the PDUs: " pdu_community
echo
read -rs -p "Enter the SNMP community configured in the fire alarm panel (BMZ): " fac_community
echo
if [ -z "$pdu_community" ] || [ -z "$fac_community" ]; then
  echo "Both SNMP communities are required." >&2
  exit 1
fi

# Provision NetBox API Token
response=$(curl -k -s -X POST \
  -H "Content-Type: application/json" \
  -H "Accept: application/json; indent=4" \
  -d "{\"username\": \"${username}\", \"password\": \"${password}\"}" \
  "${netbox_url}/api/users/tokens/provision/")

token=$(echo $response | jq -r '.key')

# Check the NetBox token provisioning result
if [ -n "$token" ] && [ "$token" != "null" ]; then
  echo "NetBox Token provisioned successfully."
else
  echo "Failed to provision NetBox token with provided credentials or to parse the token."
  echo $response
  exit 1
fi

# Create .env file from .env.example
cp .env.example .env

# Replace placeholders with actual values
setze MONGO_INITDB_HOSTNAME "${fqdn}"
setze MONGO_INITDB_DATABASE "avorus"
setze MONGO_INITDB_USERNAME "avorus"
setze MONGO_INITDB_PASSWORD "$(generate_random_string)"
setze MQTT_HOSTNAME "${fqdn}"
setze API_HOSTNAME "${fqdn}"
setze API_SECRET "$(generate_random_string)"
setze API_SYSTEM_USERNAME "system@${fqdn}"
setze API_SYSTEM_PASSWORD "$(generate_random_string)"
setze NETBOX_API_URL "${netbox_url}"
setze NETBOX_API_TOKEN "${token}"
setze KNX_GATEWAY_IP "${knx_gateway_ip}"
setze KNXKEYS_FILE_PATH "${knxkeys_file_path}"
setze KNXKEYS_PASSWORD "${knxkeys_password}"
setze PJLINK_PASSWORD "${pjlink_password}"
setze PDU_COMMUNITYSTRING "$pdu_community"
setze FAC_COMMUNITYSTRING "$fac_community"

# HOSTNAME (cert CN / compose ${HOSTNAME} interpolation) and API_ROOT_CA (mkcert
# rootCA path bind-mounted into manager/knx) have no safe default — write
# concrete values so the stack doesn't fail on an empty mount / cert mismatch.
setze HOSTNAME "${fqdn}"
setze API_ROOT_CA "$(pwd)/backend/mkcert/certs/.local/share/mkcert/rootCA.pem"

echo ".env file has been created."
