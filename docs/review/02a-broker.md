# Stage 2a — `backend/broker` Review

**Date:** 2026-05-27
**Scope:** Mosquitto-Broker-Config (`backend/broker/mosquitto/config/mosquitto.conf`)
**Reviewer:** caveman:cavecrew-reviewer (Opus 4.7)
**Filter:** cosmetic excluded; security + production-hardening focus

---

## Findings

### CRITICAL

| # | Location | Problem | Fix |
|---|----------|---------|-----|
| C1 | `mosquitto.conf` | 🚨 **Keine ACL-Datei / keine Topic-Restriktionen.** Mit `use_identity_as_username true` + einer CA: **jeder Client mit CA-Cert** (Probe, Manager, geleakter Cert) kann ANY Topic publish/subscribe — inkl. spoofen von `probe/<other-fqdn>/connected` retained oder Hijack von Command-Topics. | `acl_file /opt/tls/acl` mit `pattern write probe/%u/#`, `pattern read manager/%u/#` etc. |

### HIGH

| # | Location | Problem | Fix |
|---|----------|---------|-----|
| H1 | `mosquitto.conf` | ⚠️ **Keine Persistenz konfiguriert.** Retained Messages (`connected`, `capabilities`, `boot_time`) + queued Messages für offline Sessions verschwinden bei Broker-Restart. Manager sieht nach Broker-Restart erst neuen State wenn Probes selbst reconnecten. | `persistence true` + `persistence_location /mosquitto/data/` |
| H2 | `mosquitto.conf` | ⚠️ **Kein TLS-Version-Pin / keine Cipher-Policy.** Defaults erlauben TLS 1.0/1.1 auf älteren Builds. | `tls_version tlsv1.2` (min) + explizite `ciphers`/`ciphers_tls1.3` |
| H3 | `mosquitto.conf:1` | ⚠️ `max_inflight_messages 0` = **unlimited per Client**. Slow/stalled Manager subscribed at QoS≥1 → unbounded Broker-Memory-Growth | finite Wert, z.B. `max_inflight_messages 100` |

### MEDIUM

| # | Location | Problem | Fix |
|---|----------|---------|-----|
| M1 | `mosquitto.conf:2` | ⚡ `max_queued_messages 10000` ist per-Client; kein `max_queued_bytes` / `memory_limit` global | beide Caps setzen |
| M2 | `mosquitto.conf:4` | ⚡ `upgrade_outgoing_qos true` upgraded Probe-QoS-0-Sensor-Publishes auf Subscriber-QoS — erhöht Broker-Memory + Bandwidth für transient sensor data (fire-and-forget intention) | `upgrade_outgoing_qos false` außer Manager braucht explicit at-least-once |
| M3 | `mosquitto.conf:5` | ⚡ `listener 8883` ohne Bind-Address → bindet auf `0.0.0.0`; auf host-network exposed das auf jedem Interface | `listener 8883 <internal-ip>` oder Firewall-Doc |
| M4 | `mosquitto.conf` | ⚡ Kein `log_dest` / `log_type` — Audit-Trail für TLS-Handshake-Fails, Auth-Rejects, Disconnects fehlt je nach Image-Default | `log_dest stdout` + `log_type error warning notice` |
| M5 | `mosquitto.conf:10` | ⚡ `use_identity_as_username true` + 1 CA: Username = CN/Subject; ohne ACL + ohne `allow_zero_length_clientid false` können zwei Probes mit gleichem CN kollidieren | ACL-`pattern`-Rules + clientid-Cap |
| M6 | `mosquitto.conf` | ⚡ Kein `allow_zero_length_clientid false` — leere Client-IDs erlaubt, Ghost-Sessions möglich | `allow_zero_length_clientid false` |

### LOW

| # | Location | Problem | Fix |
|---|----------|---------|-----|
| L1 | `mosquitto.conf` | ℹ️ Kein `connection_messages true` / `log_timestamp_format` explicit | für reproduzierbare Logs pinnen |
| L2 | `mosquitto.conf` | ℹ️ Kein `max_packet_size`-Cap → oversized PUBLISH möglich | `max_packet_size 1048576` |
| L3 | `mosquitto.conf` | ℹ️ Default `sys_interval` publishes `$SYS/#` (broker-internals) — ohne ACL für jeden authenticated Client lesbar | ACL tightening oder `sys_interval 0` |
| L4 | `mosquitto.conf:9` | ℹ️ Kein `crlfile` — revoked Client-Certs bleiben gültig bis CA-Expiry | `crlfile /opt/tls/crl.pem` falls Revocation im Threat-Model |

---

## Summary

| Severity | Count |
|----------|------:|
| CRITICAL | 1 |
| HIGH | 3 |
| MEDIUM | 6 |
| LOW | 4 |
| **TOTAL** | **14** |

## Update/Hardening-Targets

| Bereich | Aktion | Priorität |
|---------|--------|-----------|
| ACL-File | Topic-Permissions per Identity definieren | CRITICAL |
| Persistenz | `persistence true` + Volume mount | HIGH |
| TLS-Policy | min `tlsv1.2`, explicit Ciphers | HIGH |
| Memory-Bounds | `max_inflight_messages`, `max_queued_bytes`, `memory_limit` | HIGH/MEDIUM |
| QoS-Upgrade | Re-evaluate `upgrade_outgoing_qos` vs. Probe-Sensor-Stream-Design | MEDIUM |
| Logging | explizite `log_dest`/`log_type` | MEDIUM |

## Hauptmuster

1. **Authorization-Lücke:** mTLS authentifiziert **wer**, aber nicht **was er darf**. Komplette Topic-Permission-Schicht fehlt. Größtes Single-Risk.
2. **Operational-Defaults überall:** Persistenz, Logging, Memory-Bounds, TLS-Version — alles auf Image/Build-Default verlassen.
3. **Probe ↔ Broker QoS-Mismatch:** Probe publisht Sensors mit QoS 0 (intentional fire-and-forget), Broker upgraded sie auf Subscriber-QoS. Architekturaler Kontrast.
