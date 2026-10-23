# Fire alarm panel (BMZ) → fac

`fac` receives SNMP traps from the fire alarm panel and forwards them to the manager over MQTT
(`backend/fac/app.py`, parsed in `backend/manager/app.py`).

## Contract

- **Transport:** SNMP v1/v2c trap (community based), UDP port 8080 on the host; `fac` runs with
  `network_mode: host`. If the panel can only send to port 162, forward 162 to 8080 on the host.
- **Community:** `FAC_COMMUNITYSTRING` in `.env`, passed to the container as `COMMUNITYSTRING`. It must equal
  the community configured in the panel. `fac` refuses to start when it is empty; a wrong value makes pysnmp
  drop the trap without any log line.
- **Payload:** the value of the last varbind is `<method>/<location ids>`, for example `scram/26` or
  `unscram/26,27`. `fac` publishes it as MQTT topic `fac/<payload>`.
- **Methods:** `scram` mutes, shuts down or cuts power of the AV devices of every element of the location;
  `unscram` wakes them again.
- **Location ids:** NetBox location ids, comma separated, without spaces.

## Before a rollout

1. Check that `FAC_COMMUNITYSTRING` in `.env` equals the community configured in the panel. Until June 2026 the
   live system used a value hardcoded in `app.py`; the variable is new there.
2. Send a test trap (panel test function or `snmptrap` against port 8080 with that community) and check the
   manager log for `BMZ Scram` and `BMZ Unscram`. The `#Payload:` line in `docker logs huffac` can appear late
   because the output is buffered.
