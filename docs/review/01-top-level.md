# Stage 1 — Top-Level + Infrastructure Review

**Date:** 2026-05-27
**Scope:** `docker-compose.yml`, `docker-compose-certs.yml`, `install/`, `docs/`, `README.md`, `maintenance/docker-watchdog/`, `backend/mkcert/`
**Out of scope:** `backend/*` service code (Stages 2a–2h), `frontend/`
**Reviewer:** caveman:cavecrew-reviewer (Opus 4.7)
**Filter:** cosmetic findings excluded; update + real-bug focus

---

## Findings

### CRITICAL

| # | Location | Problem | Fix |
|---|----------|---------|-----|
| C1 | `maintenance/docker-watchdog/docker-watchdog.py:23` | 🚨 Bug iteriert dict-Keys (Container-IDs) und vergleicht jede ID-String mit `'unhealthy'` — immer True, `healthy` immer True, Watchdog restartet NIE. Defense-System non-funktional. | `for h in health_states.values(): h['Status'] != 'unhealthy'` |
| C2 | `maintenance/docker-watchdog/docker-watchdog.py:18` | 🚨 `container.attrs` einmal bei Object-Construction geholt, im Loop nie refreshed — State permanent stale. | `container.reload()` vor `attrs`-Read |
| C3 | `maintenance/docker-watchdog/docker-watchdog.service:9` | 🚨 `ExecStart=/usr/bin/docker-watchdog.py` aber `install.sh:14` kopiert nach `/usr/local/bin/` — Service startet nicht (ENOENT). | Pfade synchronisieren |
| C4 | `docker-compose.yml:35` | 🚨 Broker-Healthcheck referenziert `CertAuth.crt`, `server.crt`, `server.key` — `tls-gen/basic` produziert `ca_certificate.pem`, `server_certificate.pem`, `server_key.pem` (matched `mosquitto.conf`). Files existieren nicht → mosquitto_sub error → grep -v Error empty → exit 0 (healthy) → unverifiziert. | Echte Dateinamen + `2>&1` pipe |
| C5 | `docker-compose.yml:35` | 🚨 Healthcheck-Logik invertiert — mosquitto_sub schreibt Errors nur nach stderr, Pipe captured nur stdout; bei Broker-Failure grep auf empty input exit 1 → `\|\| exit 0` reports healthy. | stderr redirect oder Logik invertieren |

### HIGH

| # | Location | Problem | Fix |
|---|----------|---------|-----|
| H1 | `maintenance/docker-watchdog/docker-watchdog.py:17` | ⚠️ `containers.list()` default `all=False` → exited Container unsichtbar | `all=True` |
| H2 | `maintenance/docker-watchdog/docker-watchdog.py:28` | ⚠️ Restartet ALLE running Container wenn EIN Container unhealthy — auch Healthy unrelated | nur betroffene Container restarten |
| H3 | `docker-compose.yml:4` | ⚠️ `mongo:6.0.5` EOL Juli 2025 — keine Security-Patches mehr | bump 7.0.x oder 8.0.x LTS |
| H4 | `docker-compose.yml:24` | ⚠️ `eclipse-mosquitto:2.0.18-openssl` pinned alt — 2.0.20+ shippt CVE-2024-3935 (heap exec) + CVE-2023-28366 (memleak via crafted SUBSCRIBE) Fixes | bump current 2.0.x patch |
| H5 | `maintenance/docker-watchdog/docker-watchdog.service:10` | ⚠️ `WorkingDirectory=/home/alex/humboldt` — Operator-Username hardcoded | drop oder generic path |
| H6 | `maintenance/docker-watchdog/docker-watchdog.service:12` | ⚠️ `RestartSec=600s` nach Crash → 10min silent | reduce ~10s |
| H7 | `maintenance/docker-watchdog/docker-watchdog.py:1` | ⚠️ Kein try/except um docker-client-calls — transient Docker-Daemon-Error killt Prozess, 10min Recovery-Delay | Loop-Body in try/except |
| H8 | `docker-compose.yml:69` | ⚠️ `curl --insecure` healthcheck akzeptiert kaputten Cert; mit interval=120s timeout=120s retries=5 start_period=5s → API kann ~10min unentdeckt unhealthy, blockt dependent-chain | kürzere intervals + sinnvoller start_period |
| H9 | `docker-compose.yml:14` | ⚠️ `network_mode: host` für jeden Service + ungenutztes `pubsub`-Bridge-Network (Zeile 172); MongoDB 27017, Broker 8883, API 80/443 direkt am Host ohne Firewall-Layer | unused network droppen, Host-Exposure dokumentieren, oder bridge nutzen |
| H10 | `docker-compose.yml:13` | ⚠️ `./backend/db/mongo-volume:/data/db` bind-mount unter Repo-Tree — `git clean -fdx` zerstört DB | named docker volume |
| H11 | `docker-compose.yml:97` | ⚠️ `manager` mit `privileged: true` auf host-network — full root-equivalent | drop privileged, gezielte cap_add wenn nötig |
| H12 | `docker-compose.yml:55,61` | ⚠️ Source-Code-bind-mounts + `uvicorn --reload` → Dev-Mode in Production | bind-mounts + --reload raus oder split prod compose |
| H13 | `docker-compose.yml:23` | ⚠️ Broker-Healthcheck ohne `retries`/`start_period` — defaults: 3 retries, 10s interval, kein startup-grace → unhealthy nach ~30s cold-start, bricht dependents | `start_period: 30s retries: 5` |
| H14 | `backend/mkcert/mkcerts.sh:3` | ⚠️ `mkcert` Cert ~398 Tage gültig, keine automatische Renewal in compose/install/watchdog — silent fail nach ~13 Monaten | renewal cron/service |

### MEDIUM

| # | Location | Problem | Fix |
|---|----------|---------|-----|
| M1 | `install/env_setup.sh:6` | ⚡ `tr -dc 'A-Za-z0-9'` Password-Gen — pipe kann früh schließen → kürzere Passwords möglich | `head -c 64 /dev/urandom \| base64 \| tr -dc 'A-Za-z0-9' \| head -c 32` |
| M2 | `install/env_setup.sh:27` | ⚡ NetBox-Password via plain JSON, `curl -k` akzeptiert any cert; bei `http://` URL plaintext | non-https refusen oder loud warn |
| M3 | `install/env_setup.sh:48` | ⚡ `sed` Delimiter-Konflikt-Risiko falls Charset später erweitert | nicht-interpretierter Delimiter |
| M4 | `docker-compose.yml:1` | ⚡ `version: '3.8'` obsolet in Compose v2 — emittiert Warning | line entfernen |
| M5 | `docker-compose.yml:18` | ⚡ mongo healthcheck ohne Auth — kollidiert mit `MONGO_INITDB_ROOT_USERNAME` auf fresh volume | `--eval` mit credentials |
| M6 | `docker-compose.yml:7` | ⚡ `MONGO_INITDB_USERNAME`/`PASSWORD` ist NICHT Standard-Var (`MONGO_INITDB_ROOT_USERNAME`/`PASSWORD`) | verify init-Scripts oder rename |
| M7 | `docker-compose.yml:128` | ⚡ `knx` konsumiert `KNXKEYS_FILE_PATH` aber kein Mount → FileNotFound | bind-mount addieren |
| M8 | `install/ssl_setup.sh:3` | ⚡ `ssl_setup.sh` + `certs_setup.sh` byte-identisch; nur former wird genutzt | dead file löschen |
| M9 | `backend/mkcert/Dockerfile:1` | ⚡ `FROM alpine` ohne Tag → `:latest` floating → non-reproducible | `alpine:3.20` pinnen |
| M10 | `backend/mkcert/Dockerfile:4` | ⚡ `mkcert v1.4.4` (2022-07), kein Signature-Verify | SHA256 pinnen + verify |
| M11 | `backend/mkcert/Dockerfile:7` | ⚡ `git clone --depth=1 tls-gen` ohne Commit-Pin — kann silent Filenames brechen | tag/commit pinnen |
| M12 | `maintenance/docker-watchdog/install.sh:8` | ⚡ `python3-sdnotify` kein Debian-Package — eigentlich `python3-systemd` oder pip `sdnotify`; `-qq` silenced den Fehler | pip install oder Paketname fix |
| M13 | `maintenance/docker-watchdog/install.sh:6` | ⚡ `-qq` silenced apt-get errors → fehlende Pakete unbemerkt | `-qq` raus |
| M14 | `install/install.sh:15` | ⚡ `git clone` skip via inside-repo-check + `cd avorus` auch skipped → fragile CWD-Abhängigkeit | document oder robusten Pfad |
| M15 | `docker-compose.yml:171` | ⚡ `networks: pubsub` declared, aber kein Service referenziert | delete |
| M16 | `docker-compose.yml:39` | ⚡ API healthcheck `start_period: 5s` zu kurz für FastAPI+Mongo+TLS-Startup | bump 30s |
| M17 | `docker-compose.yml:153` | ⚡ `fac`, `calendar`, `manager` ohne Healthcheck | minimal healthcheck (process oder MQTT-ping) |

---

## Summary

| Severity | Count |
|----------|------:|
| CRITICAL | 5 |
| HIGH | 14 |
| MEDIUM | 17 |
| LOW | 0 |
| **TOTAL** | **36** |

## Top Update-Targets

| Komponente | Aktuell | Empfehlung | Grund |
|------------|---------|-----------|-------|
| MongoDB | `mongo:6.0.5` | `mongo:7.0` oder `mongo:8.0` | 6.0 EOL Juli 2025 |
| Mosquitto | `eclipse-mosquitto:2.0.18-openssl` | `2.0.20+-openssl` | CVE-2024-3935, CVE-2023-28366 |
| mkcert base | `alpine:latest` (floating) | `alpine:3.20` | Reproduzierbarkeit |
| mkcert binary | `v1.4.4` (2022) | latest + SHA256 | Signature-Verify |
| tls-gen | unpinned | spezifischer Tag | API-Stabilität |
| docker-watchdog | (kompletter Rewrite) | siehe C1-C3, H1-H2, H7 | Funktional kaputt |
| Broker-Healthcheck | (kompletter Rewrite) | siehe C4, C5, H13 | Funktional kaputt + Filename-Mismatch |

## Hauptmuster

1. **Defense-Systeme nicht funktional:** Watchdog (C1, C2) + Broker-Healthcheck (C4, C5) sind beide kaputt — System hat keine working Health-Detection auf Infrastruktur-Ebene.
2. **Production vs. Development vermischt:** `--reload`, source-mounts, host-network ohne Doku, `privileged: true` ohne Justification.
3. **Versions-Drift:** Mehrere EOL/CVE-relevante Pins (Mongo, Mosquitto). Floating-Tags wo nicht erwartet.
4. **Cert-Lifecycle ungemanaged:** mkcert-Ausstellung manuell, kein automatischer Renewal-Pfad, kein Alarm bei Expiry.
