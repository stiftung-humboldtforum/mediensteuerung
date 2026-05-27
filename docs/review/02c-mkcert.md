# Stage 2c — `backend/mkcert` Review

**Date:** 2026-05-27
**Scope:** TLS-Cert-Generation (`backend/mkcert/`, `docker-compose-certs.yml`)
**Reviewer:** caveman:cavecrew-reviewer (Opus 4.7)
**Filter:** cosmetic excluded; key-handling + rotation + reproducibility focus

> Note: einige Findings überlappen mit Stage 1 (Broker-Healthcheck, mkcert-Versionen). Hier mit Fokus auf Cert-Pipeline + Key-Material.

---

## Findings

### CRITICAL

| # | Location | Problem | Fix |
|---|----------|---------|-----|
| C1 | `mkcerts.sh:7` + `docker-compose.yml:28,56,92,117,143,162` | 🚨 **tls-gen produziert `ca_key.pem` + `*.p12` (PKCS#12 mit Private Keys) in `/root/mqtt`.** Line 9 `cp -r ./result /root/mqtt`. Host-bind `./backend/mkcert/certs/mqtt:/opt/tls` mounted in **jeden Service-Container** (broker, api, manager, calendar, knx, fac). Jeder kompromittierte Container hat **Broker-CA-Signing-Key** auf Disk → kann beliebige Server/Client-Certs minten gegen `require_certificate true`. | `ca_key.pem`, `testca/private/`, `*.p12` aus `/root/mqtt` strippen vor bind-mount |
| C2 | `docker-compose-certs.yml:11` | 🚨 **Bind-mount `./backend/mkcert/certs:/root`** — exposed **whole** `/root` inkl. mkcert-CAROOT `/root/.local/share/mkcert/rootCA-key.pem` (API-CA-Private-Key). Sensitive Key in Host-Repo-Path lesbar. | CAROOT outside `/root` setzen (env `CAROOT=/cert-store-private`), separate non-bind volume, ODER nur public outputs nach `/output` kopieren |
| C3 | `mkcerts.sh:3` | 🚨 **Keine Cert-Rotation.** mkcert v1.4.4 leaf ~825d, CA ~10y. tls-gen `DAYS_OF_VALIDITY=3650`. Kein cron/timer/watchdog für Renewal. API HTTPS hard-fail auf Browsern mit 398d-Limit (Safari/Chrome). | Scheduled re-run `docker-compose-certs.yml` + Container-Restart |
| C4 | `mkcerts.sh:9` | 🚨 **`cp -r ./result /root/mqtt` nicht idempotent.** Erst-Run: erstellt dir. Re-Run: legt **nested** `/root/mqtt/result/...` an, Mosquitto liest stale Certs. Renewal silently broken. | `rm -rf /root/mqtt && cp -r ./result /root/mqtt` ODER `cp -rT` |
| C5 | `mkcerts.sh:1` | 🚨 **`set -eu` fehlt.** Jeder failing Step (mkcert exit, missing env, make error) → silent → `echo Done!` while producing partial/no Certs. | `set -eu` ganz oben |
| C6 | `docker-compose.yml:35` | 🚨 Broker-Healthcheck-Filenames falsch (CertAuth.crt etc. existieren nicht — tls-gen produziert ca_certificate.pem/server_certificate.pem) + invertierte Exit-Logik → **healthy regardless of broker state** (auch in Stage 1 C4/C5) | Echte Filenames + `2>&1` + Logik fix |
| C7 | `Dockerfile:1` | 🚨 `FROM alpine` floating-tag — Rebuild kann alpine-Major mit anderem openssl/make/python3-Verhalten ziehen, silent ändert Cert-Content | `FROM alpine:3.20@sha256:...` pinnen |
| C8 | `Dockerfile:4` | 🚨 mkcert-Binary über Netz ohne Checksum/Signature-Verify. Upstream-Tag-Deletion oder MITM ersetzt Binary | SHA256 pinnen + verify |
| C9 | `Dockerfile:7` | 🚨 `git clone --depth=1 tls-gen` unpinned — jeder Rebuild snapped current main. Output-Filenames + Default-Key-Bits + SAN-Verhalten changed across Versionen | Tag/Commit pinnen |

### HIGH

| # | Location | Problem | Fix |
|---|----------|---------|-----|
| H1 | `mkcerts.sh:3` | ⚠️ `$API_HOSTNAME` unquoted, nicht validiert. Unset → Filename collapsed → `docker-compose.yml:61` bricht | `: "${API_HOSTNAME:?must be set}"` |
| H2 | `mkcerts.sh:3` | ⚠️ SAN-Liste hardcoded `$API_HOSTNAME 127.0.0.1 localhost` — fehlt Aliases, k8s-Service-Names, Container-Short-Names | Mehr SANs |
| H3 | `mkcerts.sh:7` | ⚠️ tls-gen baked `crlDistributionPoints = URI:http://crl-server:8000/basic.crl` in jeden Cert — kein CRL-Server existiert. Strict-TLS-Clients failen oder hangen auf CRL-Fetch | openssl.cnf patchen oder URL strippen |
| H4 | `mkcerts.sh:7` | ⚠️ `SERVER_ALT_NAME`/`CLIENT_ALT_NAME` env nicht gesetzt → tls-gen common.mk fallback `$(shell hostname)` = random Docker-Container-Hostname. Broker-Cert SAN endet `[DNS=<random>]`. Clients per IP/Alias → SAN-Mismatch | `SERVER_ALT_NAME=$MQTT_HOSTNAME` exportieren |
| H5 | `mkcerts.sh:11` | ⚠️ `chmod 0600 /root/mqtt/*` strippt Read von Non-Root, Non-1883 UIDs — wenn Service-Container je Non-Root → mqtt-TLS-Bring-Up bricht | ACL für Service-UIDs oder 0644 für public Cert-Files |
| H6 | `mkcerts.sh:11` | ⚠️ `chmod 0600` auf `*.p12` PKCS#12 — enthält Private Keys, an jeden Service distributed (siehe C1) | `.p12` löschen post-gen |
| H7 | `mkcerts.sh:12` | ⚠️ `setfacl -R -m u:1883:rx` — UID 1883 hardcoded für mosquitto-Image. Bei Image-Wechsel/Bump silently fail | UID aus broker-image resolven oder assert |
| H8 | `mkcerts.sh:4` | ⚠️ Nur `rootCA.pem` kopiert; `rootCA-key.pem` bleibt im host-visible bind-mount → aktive CA-Key ohne Rotation, leak-Risiko forever | Nach Sign sofort wipen oder outside bind-mount |
| H9 | `Dockerfile:3` | ⚠️ `apk add --no-cache` Pakete unpinned (openssl, make, python3, acl) — Rebuild → andere Toolchain | Versionen pinnen |
| H10 | `Dockerfile:7` | ⚠️ tls-gen geklont in `/tls-gen` ohne vorigen WORKDIR — funktioniert coincidentally. tls-gen-Layout-Change killt cert-gen silently | absolute Pfade + Assertion |
| H11 | `docker-compose-certs.yml:4` | ⚠️ `image: mkcert` no-registry-no-tag + `build:` — Local-Image, kein GC-Guard. Cached `mkcert:latest` behält outdated mkcert binary; `--pull` nicht dokumentiert | tag + dropping `image:` ODER `mkcert:1.4.4-tls-gen-<sha>` |
| H12 | `docker-compose-certs.yml:11` | ⚠️ Kein `user:` override — container läuft als root → root-owned files in host bind. Host-Operator braucht sudo für rotate | `user: "${UID}:${GID}"` oder chown step |
| H13 | `docker-compose-certs.yml:14` | ⚠️ Kein Rotation-Service — `install/certs_setup.sh` + `ssl_setup.sh` one-shots. Nichts re-runt Cert-Gen oder restartet broker/api near-expiry | systemd timer/cron renewal job |
| H14 | `docker-compose.yml:28` | ⚠️ `./backend/mkcert/certs/mqtt:/opt/tls` mounted **ganzen** `mqtt/` (inkl. `ca_key.pem` + `*.p12`) in broker UND jeden Client | split dirs oder keys strippen post-gen |

### MEDIUM

| # | Location | Problem | Fix |
|---|----------|---------|-----|
| M1 | `Dockerfile:10` | ⚡ `WORKDIR /root` AFTER `COPY mkcerts.sh .` → script lands `/mkcerts.sh` nicht `/root/mkcerts.sh` — works coincidentally | COPY nach WORKDIR oder explizit absolute path |
| M2 | `mkcerts.sh:7` | ⚡ tls-gen `DAYS_OF_VALIDITY=3650` (10y) für Broker-Server/Client + CA. Keine Rotation. Single-Point-Compromise lebt Jahre | Override `DAYS_OF_VALIDITY=365` + scheduled regen |
| M3 | `mkcerts.sh:7` | ⚡ `NUMBER_OF_PRIVATE_KEY_BITS=2048` RSA. Upgrade-Path zu ECC (`USE_ECC=true`, `ECC_CURVE=prime256v1`) ein-Zeiler, tls-gen-recommended | ECC erwägen |
| M4 | `mkcerts.sh:10` | ⚡ `chmod 0700 /root/mqtt` in container = host bind-mount erbt — Non-Root-Operator kann nicht inspekt/backup ohne sudo. Hardening OK, undocumented | install README |
| M5 | `mkcerts.sh:12` | ⚡ Kein Fallback wenn `setfacl` failed (FS ohne ACL-Support); `set -eu` absent (C5) → swallowed | verify oder fallback chmod 0640 |
| M6 | `docker-compose-certs.yml:1` | ⚡ `version: '3.8'` obsolet in Compose v2 | line entfernen |
| M7 | `docker-compose-certs.yml:14` | ⚡ `command: /mkcerts.sh` ohne `entrypoint` reset — Alpine default `/bin/sh -c` invokes shebang. Bei base-image-Change → bricht | `entrypoint: ["/bin/sh", "/mkcerts.sh"]` |

### LOW

| # | Location | Problem | Fix |
|---|----------|---------|-----|
| L1 | `backend/mkcert/.gitignore` | ℹ️ `certs` ignored, enthält live CA-Private-Keys nach Run — accidental `git add -f` oder `git clean -fxd` mishandling | Pre-Commit-Guard + structure-only `.gitkeep` |

---

## Summary

| Severity | Count |
|----------|------:|
| CRITICAL | 9 |
| HIGH | 14 |
| MEDIUM | 7 |
| LOW | 1 |
| **TOTAL** | **31** |

## Update/Hardening-Targets

| # | Aktion | Priorität |
|---|--------|-----------|
| 1 | `mkcerts.sh`: `ca_key.pem` / `rootCA-key.pem` / `*.p12` strippen vor host-bind-mount | CRITICAL |
| 2 | Broker-Healthcheck-Filenames + Logik fixen | CRITICAL |
| 3 | Cert-Rotation: scheduled regen + Container-Restart | CRITICAL |
| 4 | Pin Upstream: alpine-digest, mkcert SHA256, tls-gen commit | CRITICAL |
| 5 | Bind-Mounts splitten: CA-Private-Key NIE in Service-Container | CRITICAL |
| 6 | `set -eu` in mkcerts.sh | CRITICAL |
| 7 | Idempotent `cp -rT` | CRITICAL |
| 8 | SAN-Coverage erweitern + crl-URL strippen | HIGH |
| 9 | UID-1883-Assumption resolven | HIGH |
| 10 | Schema/CRL-Distribution-Point entfernen oder real CRL-Server bauen | HIGH |

## Hauptmuster

1. **Key-Material überall verteilt:** Broker-CA-Private-Key in `/opt/tls` von **jedem** Service-Container. API-CA-Private-Key in Host-Repo. Komplette Trust-Chain compromised wenn ein Container/Disk-Image leaked.
2. **Keine Rotation:** Certs leben 2-10 Jahre, kein Renewal-Hook. Web-PKI-Browser akzeptieren nicht >398 Tage → API-HTTPS-Brokenness eingebaut.
3. **Reproducibility-Lücke:** Floating alpine, mkcert-Download ohne Checksum, tls-gen unpinned → Build kann jederzeit silent kaputtgehen.
4. **Non-idempotente Pipeline:** `cp -r` ohne `-T` → Renewal-Run produziert nested-stale-State.
