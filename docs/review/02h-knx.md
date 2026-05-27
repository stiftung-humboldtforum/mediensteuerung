# Stage 2h — `backend/knx` Review

**Date:** 2026-05-27
**Scope:** KNX-Bus ↔ MQTT-Bridge (`backend/knx/`)
**Reviewer:** caveman:cavecrew-reviewer (Opus 4.7)
**Filter:** cosmetic excluded; CVE/Updates + Reconnect/Auth/Secrets

---

## Findings

### CRITICAL

| # | Location | Problem | Fix |
|---|----------|---------|-----|
| C1 | `knx.py:11` + `docker-compose.yml:139-144` | 🚨 **`KNXKEYS_FILE_PATH` env passed**, aber **kein Bind-Mount** der Keystore-Datei → `FileNotFoundError` on container-start sobald Var gesetzt (siehe Stage 1 M7) | `- $KNXKEYS_FILE_PATH:$KNXKEYS_FILE_PATH:ro` mount |
| C2 | `app.py:34` | 🚨 TLS/mTLS konfiguriert, aber `ssl_context.check_hostname`+`verify_mode` Defaults, kein expliziter `minimum_version=TLSv1_2` | `ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2` |
| C3 | `knx.py:67` | 🚨 `self.switches[int(device.name)]` — wenn `device.name` nicht in dict (Race nach Reload) → KeyError propagiert in xknx-Callback-Dispatch → killt Bus-Reader | `.get()` + guard |

### HIGH

| # | Location | Problem | Fix |
|---|----------|---------|-----|
| H1 | `Dockerfile:6` | ⚠️ `asyncclick==8.1.3.4` + `anyio==3.6.2` — anyio 3.x EOL (4.x required by modern aiomqtt/xknx) | anyio 4.x |
| H2 | `Dockerfile:8` | ⚠️ `requests==2.30.0` — CVE-2023-32681 (Proxy-Authorization Leak), CVE-2024-35195 (verify=False Session-Bypass) | >=2.32.4 |
| H3 | `Dockerfile:9` | ⚠️ `aiomqtt==1.1.0` — current 2.x, `messages()` API geändert | 2.x + adapt app.py:50 |
| H4 | `app.py:50` | ⚠️ Kein Reconnect-Loop — bei MQTT-Drop endet `async for message` silent, Container vertraut auf `restart: always`; während Gap publised `device_updated_cb` via dead client | Retry-Loop mit `MqttError` |
| H5 | `app.py:24` | ⚠️ `reload()` stoppt xknx + re-runs `setup()` → ruft `Api.get()` — wenn API down → Exception bubbles → Consumer-Loop stirbt | try/except + keep old config |
| H6 | `api.py:9` | ⚠️ `os.environ["API_HOSTNAME"]` nicht URL-escaped → Injection wenn Hostname `/` enthält | validate hostname |
| H7 | `api.py:21` | ⚠️ `response.json()['access_token']` ohne status-check — Login-Fail crashed app at startup | `response.ok` check |
| H8 | `knx.py:12` | ⚠️ `KNXKEYS_PASSWORD` plaintext via env — `docker inspect`/proc exposed | Docker-secrets |
| H9 | `knx.py:11` | ⚠️ Env-Access at module-import → `import knx` crashed wenn vars unset | `__init__` + validate |
| H10 | `knx.py:40` | ⚠️ `invert_knx_switch_group_addresses[i] == 'true'` — Schema-Mismatch: andere Code split-by-lines, hier nicht — wahrscheinlich silent `False` für jeden Entry | split/parse parity verify |
| H11 | `knx.py:41` | ⚠️ Bare `except:` — swallows KeyboardInterrupt/SystemExit | typed |
| H12 | `knx.py:57` | ⚠️ Bare `except` um `Switch()`-Ctor — malformed group_address silently dropped mit leerem `logger.exception('')` | catch `XKNXException` + log address |
| H13 | `knx.py:72` | ⚠️ `switch.switch.group_addr_str().split(',')[0][1:]` — brittle Internals-String-Parsing | `switch.switch.group_address` direkt |
| H14 | `knx.py:74` | ⚠️ `knx/switch/<id>` non-retained — Manager-Restart sieht keinen State bis nächstes Bus-Telegram | `retain=True` (Manager idempotent) |
| H15 | `knx.py:60` | ⚠️ `xknx.start()` reconnect-Resubscribe-Story nicht dokumentiert; auf `stop()+start()` während Reload können in-flight Callbacks disposed switches referenzieren | Cancellation-Token + await drain |
| H16 | `mqtt_client.py:9` | ⚠️ Custom `__aenter__` ohne matching `__aexit__` — aiomqtt 2.x Upgrade-Risk | both oder neither |
| H17 | `test.py:1` | ⚠️ **Shipped Dev-Probe-Script** im Container (kein Test-Framework, `print`, `daemon_mode=True` blockt, `try_address` von nichts gerufen) — gebundled via `./backend/knx:/app` mount | aus Image raus oder delete |

### MEDIUM

| # | Location | Problem | Fix |
|---|----------|---------|-----|
| M1 | `Dockerfile:1` | ⚡ Python 3.11 (3.13 stable) | python:3.13-slim |
| M2 | `Dockerfile:10` | ⚡ `xknx==2.11.2` outdated (current 3.x mit KNX/IP Secure Fixes) | 3.x + retest secure tunneling |
| M3 | `Dockerfile:1` | ⚡ Keine requirements.txt/lockfile — Hashes fehlen | requirements.lock |
| M4 | `Dockerfile:1` | ⚡ Container als root + Source-RW-Bind-Mount | non-root + `:ro` |
| M5 | `app.py:46` | ⚡ Subscribe vor `setup()/start()` — kein Resub nach Broker-Reconnect | reconnect-aware wrapper |
| M6 | `api.py:32` | ⚡ Recursive 401-Retry ohne Depth-Guard → RecursionError wenn Token auch 401 | single-retry flag |
| M7 | `api.py:16` | ⚡ Sync `requests` in async-App blockt Event-Loop | `httpx.AsyncClient` oder `to_thread` |
| M8 | `api.py:27` | ⚡ Kein Timeout auf `requests.get/post` → API-Hang freezes Startup+Reload | `timeout=(5,30)` |
| M9 | `knx.py:73` | ⚡ `state != None` statt `is not None`; initial `None` erreicht Manager nie → KNXState.UNDEFINED bis first telegram | `is not None` + initial-publish |
| M10 | `test.py:15` | ⚡ `xknx.stop()` nur in Exception-Path — kein finally cleanup | try/finally |
| M11 | `misc.py:3` | ⚡ `logging.getLogger()` returnt root → third-party (xknx, aiomqtt, urllib3) noisy | `__name__` + Root-Config separat |

---

## Summary

| Severity | Count |
|----------|------:|
| CRITICAL | 3 |
| HIGH | 17 |
| MEDIUM | 11 |
| LOW | 0 |
| **TOTAL** | **31** |

## Update-Targets

| Package | Aktuell | Empfehlung | Grund |
|---------|---------|-----------|-------|
| `requests` | 2.30.0 | >=2.32.4 | CVE-2024-35195 + CVE-2023-32681 |
| `aiomqtt` | 1.1.0 | 2.x | major + reconnect |
| `anyio` | 3.6.2 | 4.x | EOL |
| `xknx` | 2.11.2 | 3.x | IP-Secure-Fixes |
| `python` | 3.11 | 3.13 | lifecycle |
| `asyncclick` | 8.1.3.4 | 8.1.7+ | refresh |

## Code-Bugs-Top-Liste

1. **`knx.py:11` + compose** — KNXKEYS-Datei nicht gemountet → FileNotFoundError
2. **`knx.py:67`** — `self.switches[int(device.name)]` KeyError killt Bus-Reader
3. **`knx.py:40`** — `invert_knx_switch_group_addresses` Schema-Mismatch → wahrscheinlich silent-False für jeden Entry
4. **`knx.py:74`** — Non-retained → Manager-Restart blind bis Bus-Telegram
5. **`test.py`** — Dev-Probe-Script shipped + blockt via daemon_mode=True
6. **`app.py:50`** — Kein Reconnect (selbes Pattern wie Manager + Calendar)

## Hauptmuster

1. **Selbe Reconnect-Schwäche wie Manager + Calendar:** aiomqtt 1.x ohne MqttError-Wrapper, eine Subscribe ohne Re-Subscribe.
2. **Secrets-Plaintext:** KNXKEYS_PASSWORD via env; nicht via Docker-Secrets.
3. **Brittle String-Parsing:** xknx-Internals-`split(',')[0][1:]` ist Major-Version-Bump-Risiko.
4. **State-Initialisierung schwach:** Initial-`None` nie published + non-retained → Manager-State undefined nach Restart bis Bus-Activity.
5. **Dev-Artifacts in Production:** `test.py` shipped + ein bash-Dev-Probe gegen die Bus.
