# Stage 2g — `backend/fac` Review

**Date:** 2026-05-27
**Scope:** SNMP-Trap → MQTT-Bridge (`backend/fac/`, 78 LoC)
**Reviewer:** caveman:cavecrew-reviewer (Opus 4.7) + manual cross-check
**Filter:** cosmetic excluded

---

## Findings

### CRITICAL

| # | Location | Problem | Fix |
|---|----------|---------|-----|
| C1 | `Dockerfile:1` | 🚨 **Python `3.7.17` EOL Juni 2023** — 3 Jahre keine Security-Patches | 3.12-slim |
| C2 | `app.py:11` vs. `docker-compose.yml:159` | 🚨 **ENV-Var-Mismatch:** Compose passt `FAC_COMMUNITYSTRING`, app liest `COMMUNITYSTRING`. **Container crashed bei jedem Start** mit KeyError vor allen Handlern. (vom Reviewer übersehen — manuell verifiziert) | Einen der Namen sync |
| C3 | `app.py:43` | 🚨 UDP-Trap-Listener bind `0.0.0.0:8080` ohne Auth (nur Community-String) — exposed via host-net | bind internal interface + Doc |
| C4 | `app.py:61` | 🚨 Bare-Name `mqtt_client` in Method-Body — relies auf Module-Global-Leak von `__main__`. Funktioniert coincidentally. | `self.mqtt_client` |
| C5 | `app.py:77` | 🚨 `app.join()` auf daemon-Thread blockt forever während Dispatcher läuft. Outer `while True` reconnect-Loop **unreachable** — MQTT-Disconnects nie recover | Dispatcher im Main-Thread, MQTT supervise |

### HIGH

| # | Location | Problem | Fix |
|---|----------|---------|-----|
| H1 | `requirements.txt:1` | ⚠️ `pysnmp 4.4.12` unmaintained upstream | `pysnmp-lextudio` (drop-in) oder pysnmp 6.x |
| H2 | `app.py:21` | ⚠️ SNMPv1 Community-String als BOTH readOnly + writeOnly (same arg zweimal) | distinct names oder zweiten Arg weg |
| H3 | `app.py:26-28,47,50,54,60` | ⚠️ `print()` überall statt `logging` — keine Levels/Timestamps | logging-Modul |
| H4 | `app.py:30` | ⚠️ Bare `except` — hides errors silent | `except Exception` + logger.exception |
| H5 | `app.py:46-47` | ⚠️ Port-Bind-Failure caught + swallowed → run() läuft mit kein Transport → silently dead | re-raise oder sys.exit |
| H6 | `app.py:61` | ⚠️ `publish()` return-code (MQTT_ERR_*) ignoriert — silent drops bei Disconnect | check rc + log |
| H7 | `app.py:67-71` | ⚠️ `tls_set()` ohne `tls_version`/`ciphers`/`tls_insecure_set(False)`-Audit; Cert-Paths nicht validated | explizite TLS-Args + file-existence check |
| H8 | `app.py:72` | ⚠️ `connect()` raises bei Broker-outage; kein try/except → Prozess stirbt bei first failed boot | retry mit backoff |
| H9 | `app.py:77` | ⚠️ Kein `mqtt_client.disconnect()/loop_stop()` per Iter — würde Threads + Sockets leaken wenn reachable | finally cleanup |
| H10 | `Dockerfile:1` | ⚠️ Container läuft als root (kein `USER`) | non-root |

### MEDIUM

| # | Location | Problem | Fix |
|---|----------|---------|-----|
| M1 | `requirements.txt:2` | ⚡ `paho-mqtt 1.6.1` superseded by 2.x | >=2.1 + CallbackAPIVersion |
| M2 | `app.py:72` | ⚡ `MQTT_HOSTNAME` inline KeyError on miss | upfront validate |
| M3 | `app.py:74` | ⚡ `on_connect=print` assigned NACH `loop_start()/connect()` — Race | vor connect, real handler |
| M4 | `Dockerfile:3-4` | ⚡ Keine `--upgrade pip`, kein Hash-Pinning | requirements.lock mit hashes |

---

## Summary

| Severity | Count |
|----------|------:|
| CRITICAL | 5 |
| HIGH | 10 |
| MEDIUM | 4 |
| LOW | 0 |
| **TOTAL** | **19** |

## Update-Targets

| Package | Aktuell | Empfehlung | Grund |
|---------|---------|-----------|-------|
| `python` | 3.7.17 | 3.12-slim | 3 Jahre EOL |
| `pysnmp` | 4.4.12 | `pysnmp-lextudio` 6.x | unmaintained upstream |
| `paho-mqtt` | 1.6.1 | 2.1+ | major behind |

## Code-Bugs-Top-Liste

1. **`app.py:11` + compose:159** — ENV-Mismatch `COMMUNITYSTRING` vs `FAC_COMMUNITYSTRING` → Service **broken on every start**
2. **`app.py:77`** — `join()` blockt → Reconnect-Loop unreachable
3. **`app.py:61`** — Bare-Name `mqtt_client` (Module-Global-Leak) → coincidentally working
4. **`app.py:21`** — Community-String als RO+RW gleichzeitig

## Hauptmuster

1. **Wahrscheinlich nicht produktiv-laufend:** ENV-Var-Mismatch lässt vermuten dass Service entweder (a) nie restartet wurde seit Compose-Rename oder (b) Service ist tatsächlich tot und niemand merkts (SNMP-Traps gehen verloren).
2. **EOL-Stack:** Python 3.7 + pysnmp 4 + paho 1.6 = ältester Service im Setup.
3. **Code-Qualität deutlich schlechter** als andere Services — `print`-Debug, Bare-Name-Leak, fehlende cleanup, "Trap Listener started..." als Hauptzeichen statt structured-log.
