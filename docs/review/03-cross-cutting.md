# Stage 3 — Cross-Cutting Backend Review

**Date:** 2026-05-27
**Scope:** Backend-Architektur (Service-übergreifende Patterns)
**Reviewer:** caveman:cavecrew-reviewer (Opus 4.7)
**Filter:** keine Wiederholung der Stage-1+2-Findings; ausschließlich Service-übergreifende Patterns

---

## Findings (Cross-Cutting)

### CRITICAL

| # | Location | Problem | Fix |
|---|----------|---------|-----|
| X1 | `manager/app.py:74` | 🚨 **Dead Topic:** Manager subscribes/handles `api/subscribe_devices` — KEIN Service publisht dorthin (grep: 1 Match repoweit) | Handler löschen oder Producer wiren |
| X2 | `api/routes/base.py:78` | 🚨 API publisht `api/{target}/{method_name}` qos=1 — aber via `mqtt.publish()` (gmqtt internal) **ohne await publish-ACK**. Broker-Drop mid-request → Command silent lost, HTTP 200 OK. Kein Back-Pressure | await + status |
| X3 | `api/mqtt.py:32-35` | 🚨 **QoS-Asymmetrie:** API publisht `api/*` qos=1, subscribed `manager/*_event` + `knx/#` qos=0; Manager publisht events ohne qos (aiomqtt default 0). API-down → Manager-Events permanent lost (qos 0 + non-retained) | qos=1 alle Channels |
| X4 | `calendar/calendar_service.py:65` + `manager/app.py:36-39` | 🚨 **Subscriber-Side QoS-Downgrade:** Calendar publisht `calendar/{edge}/{type}/{method}` qos=1, Manager subscribes `calendar/#` default qos=0 → Subscription-Downgrade. Plus non-retained → Manager-Restart misst in-flight `start`-Events | Manager-Subscribe qos=1 |
| X5 | `manager/app.py:36-39` | 🚨 Manager subscribes `api/#` qos=1, aber `calendar/#`, `knx/switch/#`, `fac/#`, `probe/#` ohne qos (default 0). Probe publisht command-ACKs qos=1 — Manager downgraded → missing ACKs unter Last | qos=1 alle Subscribes |
| X6 | `manager/devices/computer.py:50,79` + `manager/app.py:35-39` | 🚨 **Duplicate Subscriptions:** Manager subscribed `probe/#` global + `probe/<fqdn>/+` per Device → Broker liefert jede Probe-Message **zweimal** → Computer-Handler doppelt + Doppelte Publishes auf `manager/device_event` | nur eine Subscribe-Layer |
| X7 | `manager/mqtt_client.py` vs `calendar/mqtt_client.py` vs `knx/mqtt_client.py` | 🚨 **Drei near-identische `mqtt_client.py`** mit divergent Bug-State. Manager hat extra `_message_queue` (cross-thread race), Calendar/KNX byte-identische stripped Versionen. **Keiner re-subscribed bei Reconnect.** | Shared lib mit Reconnect/Resub |
| X8 | `manager/mqtt_client.py:7,30-39` | 🚨 paho-mqtt-Drift: Manager importiert `paho.mqtt.client.Properties, ReasonCodes` (1.x layout). aiomqtt 1.1.0 → paho 1.6.x. Probe pinned paho 2.x. `_on_connect` signature unterschiedlich → silent break wenn paho-2.x | sync deps |
| X9 | Alle Dockerfiles | 🚨 **Python-Version-Drift:** api/manager/calendar/knx `python:3.11-slim`, fac `python:3.7.17-slim` (EOL Juni 2023). Kein Service pinnt by Digest | digest pin + fac upgraden |
| X10 | manager/calendar/knx Dockerfiles | 🚨 **`anyio==3.6.2`** pinned in 3 Services; api **gar nicht** pinned (transitiv über fastapi). anyio 3.x EOL | anyio 4.x überall |
| X11 | manager/calendar/knx Dockerfiles | 🚨 **`aiomqtt==1.1.0`** in 3 Services; api benutzt gmqtt via fastapi-mqtt; fac raw paho 1.6.1. **3 MQTT-Libraries across 5 backend Services**, jeder mit eigener Reconnect-Semantik. Keiner hat MqttError-Wrapper | unify on aiomqtt 2.x |
| X12 | `docker-compose.yml:28,56,92,117,143,162` | 🚨 `./backend/mkcert/certs/mqtt:/opt/tls` mounted in **jeden** Service-Container. Cross-Check: jeder Service nutzt nur `ca_certificate.pem`, `client_certificate.pem`, `client_key.pem` (3 Files). `ca_key.pem` + `*.p12` + `testca/private/` von **keinem** Service referenziert | split mount: `/opt/tls/public/` (3 files) |
| X13 | `broker/mosquitto/config/mosquitto.conf` | 🚨 **Auth-Flow-Gap End-to-End:** UI → API JWT enforced. Manager publisht `manager/<fqdn>/<cmd>` zu Probes via Broker-mTLS — **kein further authz**. Mosquitto ohne ACL → jeder CA-signed Cert kann `manager/<any-fqdn>/shutdown` direkt publishen, bypass API JWT komplett. API-Auth-Layer = moot | broker-ACL |
| X14 | `api/app.py:46` + `api/routes/base.py:78` | 🚨 **Kein RBAC.** WS-Broadcast → alle WS-Clients alle Device-Events. POST `/api/{target}/{method}` nur `current_active_user` (nicht admin) → jeder active User kann jedes Device wake/shutdown | role-checks |
| X15 | `manager/app.py:35-39` + `calendar/app.py:32` + `knx/app.py:46` | 🚨 **Subscriptions issued einmalig** vor `messages()`-Context. aiomqtt 1.x Reconnect wiped Subs ohne Re-Issue → silent permanent message-loss. **Pattern in allen drei aiomqtt-1.x Services identisch broken** | shared reconnect-wrapper |
| X16 | calendar TZ-Stack vs Cross-Service | 🚨 **TZ-Inkonsistenz:** api/manager/calendar mounten Host-TZ, knx+fac **nicht**. Calendar `pytz.timezone('Europe/Berlin')` + `datetime.now()` (naive) → double-applied-tz wenn Container ≠ Berlin. Manager `time.time()*1000` ms-epoch. MongoDB ISO-Strings ohne tz-Coercion | zoneinfo + UTC durchgängig |
| X17 | `docker-compose.yml:55,91,116,142,161` | 🚨 **Source-Bind-Mount auf jedem Python-Service** `./backend/<svc>:/app`. Dockerfile `pip install` pinned Versionen, aber Runtime-Python-Code ist Host. Ein `git pull` swapped Prod-Verhalten ohne Container-Rebuild → Dep-Lock decorative | image-only deploy |

### HIGH

| # | Location | Problem | Fix |
|---|----------|---------|-----|
| Y1 | `manager/devices/computer.py:146,157` | ⚠️ `unsubscribe(probe_topic)` bei offline — Top-Level `probe/#` liefert weiter Messages. Unsubscribe nutzlos | Konsistenz |
| Y2 | `manager/requirements.txt` vs `manager/Dockerfile` | ⚠️ **requirements.txt dead** — pinned `asyncio-mqtt` (predecessor), `icmplib==3.0.3`, Dockerfile installiert `aiomqtt==1.1.0`, `icmplib==3.0.4`. requirements.txt nie installed → dead documentation widersprechend Reality | sync oder delete |
| Y3 | `fac/requirements.txt:2` vs probe lock | ⚠️ fac `paho-mqtt==1.6.1`, probe `paho-mqtt==2.1.0`. Beide am selben Broker. Wire-compat survived; manager imports Properties (1.x) — wenn aiomqtt-1.1.0 je paho-2.x transitiv resolved → manager `_on_connect` arity-break | unify |
| Y4 | `api/app.py:46` + `manager.broadcast()` | ⚠️ WS-Broadcast sendet jede MQTT-Event an **alle WS-Clients** unconditionally — kein per-User-Filter | RBAC |
| Y5 | Logging across services | ⚠️ **Logging-Conventions divergiert:** fac `print()`, api `level=ERROR + print` für token, manager DEBUG, calendar DEBUG, knx INFO. Drei identische FORMAT-Strings copy-pasted. fac/api Outlier | shared logging-lib |
| Y6 | `docker-compose.yml:97` | ⚠️ Manager `privileged: true` rein für `icmplib` raw-socket — `cap_add: [NET_RAW]` würde reichen. Privileged grantet device-access + alle caps + apparmor unconfined | NET_RAW only |
| Y7 | `manager/devices/computer.py:56-76` | ⚠️ **Implizites Probe↔Manager-Schema:** Manager-Computer.__getattr__ liest `payload['data']['result']` schreibt `_state[name]`. Topic-Name = State-Key. Schema-Contract: `connected`/`capabilities` sind NICHT JSON-encoded, alles andere SCHON. Keine machine-readable Contract | OpenAPI-style schema |
| Y8 | `manager/app.py:71-107` | ⚠️ Jeder Consumer macht manuelles Topic-Parsing (`split('/')`, `topic.matches`) — keine zentrale Schema-Definition. Topic-Level-Change auf Publisher → silent break Consumer | typed topic-router |
| Y9 | `api/mqtt.py:32-35` | ⚠️ API `knx/#` — receives `knx/switch/<id>` UND any future knx-subtopic. Immer als knx_state behandelt. Zu breit, brittle | `knx/switch/#` explizit |
| Y10 | `fac/app.py:61` | ⚠️ **fac publisht `fac/{payload}` mit raw-SNMP-trap-Content als Topic-Name.** Manager parsed `fac/{method}/{location_ids}`. Producer/Consumer **Schema-Mismatch** | sync schema (vermutlich nie zusammen getestet) |
| Y11 | `manager.publish_json('manager/device_event')` + `error_mixin client.publish('manager/device_event')` | ⚠️ Selber Topic von zwei Code-Pfaden, kein QoS, payload-shape-sniff (data vs error). Schema-Discriminator fehlt | schema-tag im payload |
| Y12 | `api/app.py:53-57` | ⚠️ API hängt `target='device'` post-receive in Payload — Manager hat bereits `data.event.target` als int. **Zwei `target`-Semantiken** in selber Payload nach API-Mutation | naming-fix |
| Y13 | `knx/knx.py:74` + `api/mqtt.py:35` + `api/app.py:59-77` | ⚠️ `knx/switch/<id>` consumed von Manager (state) UND API (WS + mongo). Neither idempotent. Side-effect-Chain. Keine transactional Garantien | single-consumer pattern |
| Y14 | `manager/devices/brightsign.py:12-14` | ⚠️ BrightSign-Reboot bypassed MQTT — direct HTTP PUT mit hardcoded Creds. Cross-Cut: PJLink, Gude PDU, LGWebOSTV alle sidestep MQTT. **Fünf verschiedene Transport-Stacks** im Manager | central control-plane |
| Y15 | manager/api/calendar/knx Dockerfiles | ⚠️ **Kein Service hat requirements.lock mit Hashes.** Inline RUN pip install. Im Vergleich: probe `requirements.lock.txt` ist `uv pip compile` fully hash-resolvable. **Probe = einziger reproducible Build** | uv lock alle Services |
| Y16 | `manager/devices/computer.py:42` + `probe.py:23` | ⚠️ Manager-Identity = `primary_ip.dns_name` (NetBox); Probe-Identity = `socket.getfqdn()`. **Cross-System-Assumption:** NetBox-DNS-Field == getfqdn(). Drift → silent message-loss | reconciliation/metric |
| Y17 | api/manager/calendar/knx Dockerfiles | ⚠️ **Kein USER** Directive — 5 Container as root + host-network + manager privileged + source-bind-mounts → RCE in any service = root on host | non-root user |

### MEDIUM

| # | Location | Problem | Fix |
|---|----------|---------|-----|
| Z1 | `manager/devices/computer.py:42` | ⚡ `probe_address = manager/<fqdn>` — Topic-Prefix `manager/` kollidiert mit `manager/device_event`. `manager/#` würde beides matchen | unified prefix oder split |
| Z2 | api/manager Dockerfiles | ⚡ `requests==2.30.0` shared in API+Manager+KNX. Beide CVE-affected. Update single-source | bump everywhere |
| Z3 | Alle service Dockerfiles client_id | ⚡ Alle Services fixed `client_id` (`api`, `manager`, ...) — zwei Instanzen kollidieren, Broker dropt alte. Manager-Scale-Out unmöglich | suffix-based id |

---

## Summary

| Severity | Count |
|----------|------:|
| CRITICAL | 17 |
| HIGH | 17 |
| MEDIUM | 3 |
| LOW | 0 |
| **TOTAL** | **37** |

## Top Cross-Cutting-Themes

| # | Pattern | Auswirkung |
|---|---------|------------|
| 1 | **3× near-identische `mqtt_client.py`** mit divergent Bug-State + keiner re-subscribed bei Reconnect | aiomqtt-1.x Services brechen identisch bei Broker-Drop |
| 2 | **QoS-Asymmetrie:** `api/*` qos=1, `manager/*`/`calendar/*` events default qos=0 non-retained | Event-Loss bei transient drop |
| 3 | **Broker-ACL fehlt** → API-JWT/RBAC end-to-end moot | jede authn'd Cert kann `manager/<fqdn>/<cmd>` spoofen |
| 4 | **Source-Bind-Mount** auf allen 5 Services → Dockerfile-Pins decorative | `git pull` swapped Prod ohne Rebuild |
| 5 | **Dep-Drift:** paho-mqtt 1.x/2.x, aiomqtt 1.x vs gmqtt vs paho-raw, anyio 3.6.2 pinned in 3 vs unpinned in api, python 3.11 vs 3.7.17 | inconsistent runtime-behavior |
| 6 | **Implicit Topic-Schema** — jeder Consumer string-splits; producer/consumer-Mismatch on `fac/*` und event-payload-shape | brittle schema-evolution |
| 7 | **TLS-Material:** `ca_key.pem` + `*.p12` mounted in jeden Service obwohl keiner referenziert | Compromised container = full CA-control |
| 8 | **5 verschiedene Device-Control-Transports** (MQTT/HTTP/SNMP/WebSocket/PJLink-TCP) bypass MQTT control-plane | kein central Audit/Auth/Retry |
| 9 | **Logging divergent:** print vs logging DEBUG/INFO/ERROR — keine shared Observability | aggregation hard |
| 10 | **Identity-Coupling** `probe.getfqdn()` == `NetBox.primary_ip.dns_name` ohne Reconciliation | silent message-loss bei DNS-Drift |
| 11 | **Manager privileged: true** rein für ICMP-Raw-Socket — `cap_add: [NET_RAW]` reicht | reduces attack surface |
| 12 | **Reproducible Builds nur auf Probe** (uv-lock); 5 Backend-Services inline RUN pip | Re-deploy ≠ Re-tested |
| 13 | **Duplicate/overlapping MQTT-Subscriptions** im Manager (`probe/#` + `probe/<fqdn>/+`) verdoppeln Event-Dispatch | 2× Handler-Load |

## Hauptmuster (Architektur-Ebene)

1. **Reconnect-Story uniform broken:** Alle aiomqtt-1.x Services (manager/calendar/knx) haben identischen Bug — eine Subscribe, kein MqttError-Wrapper. Müsste durch shared lib gelöst werden.
2. **Auth fragmentiert + ACL-Lücke:** UI-Auth, API-Auth, MQTT-Auth (mTLS), aber dazwischen kein Authz. Mosquitto-ACL würde end-to-end-Story komplettieren.
3. **Dep-Management uneinheitlich:** Probe (post-Audit) hat uv-lock, andere Services inline-RUN. Keine konsistente Update-Story.
4. **Source-Bind-Mounts überall:** Dockerfile-Reproducibility = Theater. Hot-Patching via `git pull` ist Realität.
5. **5 Service-übergreifende Probleme** (X3, X4, X5, X6, X7) lassen vermuten dass **die Service-Konstellation als Ganzes nie End-to-End mit Broker-Restart getestet wurde**.
