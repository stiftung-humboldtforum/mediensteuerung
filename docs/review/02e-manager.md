# Stage 2e — `backend/manager` Review

**Date:** 2026-05-27
**Scope:** MQTT-Hub + Device-State-Machine (`backend/manager/`)
**Reviewer:** caveman:cavecrew-reviewer (Opus 4.7)
**Filter:** cosmetic excluded; CVE/Updates + Concurrency + Auth + Secrets-Handling

> **Größtes Submodul, größtes Audit.** Viele bekannte Anti-Patterns + reale State-Machine-Bugs.

---

## Findings

### CRITICAL

| # | Location | Problem | Fix |
|---|----------|---------|-----|
| C1 | `Dockerfile:10` | 🚨 **`requests==2.30.0`** — CVE-2024-35195 (Session-cert-verify-Bypass nach 1st failure) | >=2.32.4 |
| C2 | `Dockerfile:12` | 🚨 **`aiohttp==3.8.5`** — CVE-2024-23334 (path traversal), CVE-2024-30251 (DoS), CVE-2023-49081/49082 (HTTP-Smuggling), CVE-2024-52303/52304 | >=3.10.11 |
| C3 | `Dockerfile:16` | 🚨 **`git+https://github.com/worosom/aiopjlink` unpinned** — kein commit-hash, supply-chain | Commit-SHA pinnen |
| C4 | `Dockerfile:17` | 🚨 **`PyWebOSTV` + `wsaccel` unpinned + unmaintained** (wsaccel last release 2018, ws4py dead) | Pinnen + Replacement-Plan |
| C5 | `requirements.txt:4` | 🚨 **Doppelt-Pin**: `requirements.txt` pinnt `asyncio-mqtt`, Dockerfile installiert `aiomqtt==1.1.0`. Zwei MQTT-Libs. | requirements.txt droppen oder syncen |
| C6 | `app.py:48` | 🚨 `_, fqdn, device_method = message.topic.value.split('/')` ValueError-unbehandelt bei !=3 Segmenten → killt Message-Loop | try/except oder validate |
| C7 | `app.py:54` | 🚨 `getattr(device, f'on_{device_method}')` unguarded — `Computer.__getattr__` returnt Coroutine-Handler für ANY `on_*`, schreibt `_state[name]` mit Angreifer-Input | whitelist |
| C8 | `app.py:91` | 🚨 `type = topic.split('/')[2]` → `getattr(manager, f'{type}_method')` Topic-Injection — `calendar/start/setup/foo` resolved zu `manager.setup_method` etc. | validate `type in {'device','tag','location'}` |
| C9 | `app.py:35-39` | 🚨 Initial-Subscribes nur **einmal**. aiomqtt 1.x reconnected, Broker vergisst Subs, app re-subscribed **nicht** → silent message-loss | subscribe in `_on_connect` |
| C10 | `manager.py:80` | 🚨 `await self.setup()` rekursiv im except-Branch. asyncio.Lock nicht re-entrant → **Deadlock**. Infinite recursion bei API down | bounded retry-loop |
| C11 | `mqtt_client.py:30-34` | 🚨 `_on_connect` von paho-Network-Thread, mutiert `_is_connected` + drained `_message_queue` während async coroutines `publish_json` lesen → Race + sync `client.publish` statt aiomqtt + kein Resubscribe | `run_coroutine_threadsafe` + Resubscribe |
| C12 | `devices/computer.py:166` | 🚨 **`on_connected(self, *_)` ignoriert LWT-Payload** und setzt unconditionally `is_online=ON` — bekannter Bug (probe LWT setzt ONLINE) | Payload parsen |
| C13 | `devices/computer.py:164` | 🚨 `asyncio.sleep(self.intervals['reboot_interval'])` — Key existiert nicht (gesetzt als `intervals['reboot']` Z.41) → KeyError jede Reboot-Loop-Iter | Key fix |
| C14 | `devices/pjlink.py:72` | 🚨 `self._interface` nie in `__init__` assigned. Fällt durch `Device.__getattr__` zu Coroutine-Factory → AttributeError jedes erste Connect | `self._interface = None` |
| C15 | `devices/snmp_gude.py:14` | 🚨 `PDU_COMMUNITYSTRING = os.environ['PDU_COMMUNITYSTRING']` at module-load → KeyError abort Import → Manager refuses to start | default + check |
| C16 | `devices/snmp_gude.py:156` | 🚨 `while not self.is_ready` — `is_ready` undefined → `Device.__getattr__` returnt truthy coroutine-factory → `not` = False → **Loop-Body läuft nie**, Ready-Gate silently bypassed | define oder remove |
| C17 | `devices/snmp_gude.py:163` | 🚨 `self.lock.release()` ohne Held-Check → RuntimeError auf jeder Cancellation | `if locked()` oder try/except |
| C18 | `devices/tv.py:101-102` | 🚨 `self.loop.create_task(...)` aus `is_registered.setter` + `on_open`/`on_close` (ws4py IO-Thread) — **nicht thread-safe** mit asyncio | `run_coroutine_threadsafe` |
| C19 | `devices/brightsign.py:12-14` | 🚨 **Hardcoded plaintext Creds `'admin','avm'`** | env vars |
| C20 | `misc/__init__.py:45` | 🚨 **`yaml.load(..., Loader=yaml.Loader)`** — Deserialization-RCE | `yaml.safe_load` |
| C21 | `../docker-compose.yml:97` | 🚨 `privileged: true` — Manager braucht nur Raw-Socket für ICMP (icmpable.py:12) | `cap_add: [NET_RAW]` |

### HIGH

| # | Location | Problem | Fix |
|---|----------|---------|-----|
| H1 | `Dockerfile:13` | ⚠️ `aiomqtt==1.1.0` — 2 Major-Versionen behind (current 2.4.x) | migration plan |
| H2 | `Dockerfile:6` | ⚠️ `anyio==3.6.2` Major behind (4.x) | upgrade |
| H3 | `Dockerfile:7` | ⚠️ `uvloop==0.17.0` segfault-Fixes in 0.19+ | >=0.21.0 |
| H4 | `Dockerfile:1` | ⚠️ Python 3.11-slim + unpinned `apt-get` ohne `--no-install-recommends` / `apt-get clean` | pin + cleanup |
| H5 | `requirements.txt:6` | ⚠️ `icmplib==3.0.3` vs Dockerfile `3.0.4` — Version-Drift | single source |
| H6 | `app.py:50-52` | ⚠️ O(n) Device-Lookup pro Probe-Message via list-comprehension+indexing | reverse-Index |
| H7 | `app.py:57` | ⚠️ Variable `message` reassigned zu string innerhalb IndexError-Block, shadows outer `message` | rename |
| H8 | `app.py:97` | ⚠️ `payload['data']['id']` ohne Guard → KeyError verliert Event | validate |
| H9 | `manager.py:81` | ⚠️ `lock.release()` nicht in finally — leaks bei CancelledError | finally |
| H10 | `manager.py:100-103` | ⚠️ `start()` while-True ohne sleep wenn devices leer + `lock.acquire` blockt indefinitely durch C10 | document/fix |
| H11 | `manager.py:131` | ⚠️ `subscribe_device` cancel+del ohne lock — concurrent `update_devices` race | lock |
| H12 | `manager.py:225` | ⚠️ `delete_task(method_name)` vs `tasks[task_name]` Key-Mismatch → tasks-dict wächst unbounded | gleichen Key |
| H13 | `manager.py:31` | ⚠️ `response.json()['access_token']` ohne `response.ok`-Check → HTML-Crash | validate |
| H14 | `mqtt_client.py:37` | ⚠️ `_on_disconnect` nur flag, kein log/metric/notify | log |
| H15 | `devices/computer.py:159-164` | ⚠️ `_reboot` while-Loop ohne `else` — bei device != ON spinnt at full CPU | else-sleep oder break |
| H16 | `devices/computer.py:60-74` | ⚠️ `__getattr__` schreibt `_state[name]` für ANY `on_<x>` Topic + C7 = attacker-controlled state-injection | whitelist |
| H17 | `devices/computer.py:67` | ⚠️ State-Keys silent erstellt — kombiniert mit `is_idle` scan auf `should_*` → Inject via `probe/x/should_anything` | restrict known keys |
| H18 | `devices/computer.py:144-146` | ⚠️ `unsubscribe(probe_topic)` bei offline — Main re-subscribed NICHT bei online → Messages permanent lost | re-subscribe |
| H19 | `devices/pjlink.py:57` | ⚠️ `os.environ['PJLINK_PASSWORD']` in async method — lazy KeyError per-call | `__init__` + validate |
| H20 | `devices/snmp_gude.py:124-130,139-150` | ⚠️ `_watch_powerfeeds`/`_write_powerfeeds` lock release außerhalb try/finally — Exception/Cancel → lock leak → all SNMP deadlock | try/finally |
| H21 | `devices/snmp_gude.py:77` | ⚠️ `ensure_future(_handle_exception(e))` aus `__init__` (sync) — works nur wenn loop läuft. Plus return lässt Device halb-konstruiert, Manager speichert es | constructor-fix |
| H22 | `devices/wolable.py:69,53` | ⚠️ Coroutine eagerly erzeugt + Cancel-Race auf `should_wake` | lazy + serialize |
| H23 | `devices/tv.py:10` | ⚠️ `wsaccel.patch_ws4py()` monkey-patches at import — unmaintained, fragile | replacement |
| H24 | `devices/tv.py:13` | ⚠️ `store = {}` Module-Global mutable — concurrent register() corrupts `/opt/weboscreds.json` (non-atomic open+seek+truncate) | atomic write |
| H25 | `devices/tv.py:52` | ⚠️ `webosclient.connect()` blocking-WS in `asyncio.timeout` blockt Event-Loop | executor |
| H26 | `devices/tv.py:73-77` | ⚠️ Blocking File-I/O in async method | aiofiles / executor |
| H27 | `devices/brightsign.py:12` | ⚠️ `requests.put` blocking in async + kein Timeout | aiohttp + timeout |
| H28 | `devices/brightsign.py:13` | ⚠️ HTTP (nicht HTTPS) für reboot — Cleartext-Cred-Disclosure | HTTPS |
| H29 | `devices/device.py:66-68` | ⚠️ `__getattr__` returnt generic-error-Coroutine für jedes missing-attr — masked AttributeError (siehe C14, C16) | engere fallback-policy |
| H30 | `devices/device.py:55-63` | ⚠️ `cancel()` released `self.lock` unconditionally ohne owner-check | check |
| H31 | `devices/device.py:98-104` | ⚠️ `set_is_online` mutiert `_offline_counter` + `_state` lock-less | lock |
| H32 | `devices/mixins/error_mixin.py:30-33` | ⚠️ `traceback.extract_tb(tb)[-1]` extrahiert Source-Code-Text + `e.args` und published über MQTT `manager/device_event` — **Stack-Trace + Secrets-Leak via MQTT** | sanitize |
| H33 | `devices/mixins/error_mixin.py:57` | ⚠️ `lock.release()` in except — fires immer, RuntimeError swallowed | conditional |
| H34 | `devices/mixins/power_mixin.py:30` | ⚠️ `[device for ...][0]` IndexError wenn PDU noch nicht subscribed + O(n) | dict-lookup + default |
| H35 | `locations.py:31-32,42` | ⚠️ Devices-Snapshot at Construction stale; `__contains__` unvalidated `item['type']` → KeyError bei `is_online` | refresh + validate |
| H36 | `locations.py:72-83` | ⚠️ `__getattr__` async-method mit `sleep(random.random())` in TaskGroup-Loop — sequenziell statt parallel + silent dispatch | refactor |
| H37 | `tags.py:33-34,149-157` | ⚠️ Snapshot-Stale + `Tag.__getattr__` silent-dispatch | refresh + restrict |
| H38 | `misc/__init__.py:98` | ⚠️ Module-Level `last_called_dict` keyed by `name+func.__name__` — Class-Name-Collision + never GC | fix key + cleanup |
| H39 | `misc/__init__.py:101-135` | ⚠️ `memoize` decorator not concurrency-safe — `is_running` flag race | lock |
| H40 | `../docker-compose.yml:91` | ⚠️ `./backend/manager:/app` bind-mount Source — runs unfrozen Code | image-only |

### MEDIUM

| # | Location | Problem | Fix |
|---|----------|---------|-----|
| M1 | `Dockerfile:5` | ⚡ `asyncclick==8.1.3.4` outdated (latest 8.1.7.x) | refresh |
| M2 | `Dockerfile:11` | ⚡ `pymodbus==3.5.4` installed aber kein Import — Dead Dep | remove |
| M3 | `Dockerfile:15` | ⚡ `aiosnmp==0.7.2` Bugfixes in 0.7.3+ | bump |
| M4 | `Dockerfile:2` | ⚡ `apt-get` ohne cleanup | rm /var/lib/apt/lists/* |
| M5 | `app.py:69` | ⚡ Bare `except:` swallows KeyboardInterrupt | typed |
| M6 | `app.py:25` | ⚡ `asyncio.get_event_loop()` deprecated 3.10+ | `get_running_loop` |
| M7 | `manager.py:67` | ⚡ `exit(1)` lässt lock held + skipped cleanup | finally |
| M8 | `manager.py:43` | ⚡ `Api.get` rekursiv auf 401 ohne Retry-Cap | bounded |
| M9 | `devices/icmpable.py:12` | ⚡ `privileged=True` für icmplib — could use `CAP_NET_RAW` | cap-only |
| M10 | `devices/mixins/error_mixin.py:55` | ⚡ `except Exception` catched nicht `CancelledError` in 3.11 | dedicated |
| M11 | `misc/__init__.py:14-15` | ⚡ `shutil.copyfile('./config/base_config.yml', ...)` aber File-Name ist `default_config.yml` → erste Start crashed | sync filename |
| M12 | `misc/__init__.py:138-176` | ⚡ `timeout` decorator `is_timeout_dict` module-global, never cleaned per device | cleanup-on-unsubscribe |

---

## Summary

| Severity | Count |
|----------|------:|
| CRITICAL | 21 |
| HIGH | 40 |
| MEDIUM | 12 |
| LOW | 0 |
| **TOTAL** | **73** |

## Update-Targets (Versions)

| Package | Aktuell | Empfehlung | CVE/Issue |
|---------|---------|-----------|-----------|
| `aiohttp` | 3.8.5 | >=3.10.11 | CVE-2024-23334 + DoS + smuggling |
| `requests` | 2.30.0 | >=2.32.4 | CVE-2024-35195 |
| `aiomqtt` | 1.1.0 | 2.4.x | majors behind |
| `aiopjlink` | git unpinned | Commit-SHA | supply-chain |
| `PyWebOSTV` + `wsaccel` | unpinned + unmaintained | pin + replace | dead deps |
| `anyio` | 3.6.2 | 4.x | major |
| `uvloop` | 0.17.0 | >=0.21.0 | segfault-fixes |
| `pymodbus` | 3.5.4 | **remove** | dead code |
| `asyncio-mqtt` (req.txt) | — | **delete** | duplicate w/ aiomqtt |

## Code-Bugs-Top-Liste (nicht-Deps)

1. **`computer.py:164`** — KeyError `intervals['reboot_interval']` — Reboot komplett broken
2. **`snmp_gude.py:156`** — `is_ready` undefined → Ready-Gate bypassed
3. **`pjlink.py:72`** — `_interface` nie initialized → AttributeError jeden Connect
4. **`computer.py:166`** — LWT-Bug (vom Probe-Audit bekannt) — Probe-LWT setzt ONLINE
5. **`misc/__init__.py:45`** — `yaml.load(Loader=yaml.Loader)` Deserialization-RCE
6. **`misc/__init__.py:15`** — `base_config.yml` referenced, File heißt `default_config.yml` — First-Start-Crash
7. **`mqtt_client.py:30-34`** — Race + kein Resubscribe + Sync-paho-Publish
8. **`manager.py:80`** — Recursive `setup()` Deadlock auf Lock
9. **`app.py:35-39`** — Initial-Subscribes nur einmal — silent message-loss nach Broker-Disconnect
10. **`brightsign.py:14`** — Hardcoded `admin:avm` Plaintext-Creds
11. **`tv.py:101-102`** — `loop.create_task` aus IO-Thread (nicht thread-safe)
12. **`error_mixin.py:30-33`** — Stack-Trace + secrets-Leak via MQTT-Topic

## Hauptmuster

1. **MQTT-Topic-Injection als architekturales Risiko:** Manager dispatched per `getattr(manager, f'{type}_method')` und `getattr(device, f'on_{device_method}')` ohne Allow-List. Attacker mit broker-write-Permission kann beliebige Methoden triggern + State-Keys injizieren.
2. **Async-Concurrency-Schulden:** Lock-handling überall nicht in try/finally, `cancel()` released unconditionally, sync-blocking in async-methods (file-I/O, requests, websockets-connect), thread-callbacks ohne `run_coroutine_threadsafe`.
3. **Reconnect-Story komplett fehlt:** mqtt_client re-subscribed nicht nach Broker-Reconnect; computer.py unsubscribed bei offline und re-subscribed nie. Long-running operation hat schweigende Message-Loss-Risiken.
4. **Unmaintained / Floating Deps:** aiopjlink-Fork unpinned, wsaccel (2018), pymodbus dead code, doppelt-deklarierter MQTT-Lib.
5. **Secrets-Exposition:** Hardcoded Plaintext-Creds (brightsign), Stack-Traces via MQTT geleakt, Module-Level KeyErrors auf env-vars.
6. **`__getattr__`-Anti-Pattern:** Device.__getattr__ + Tag.__getattr__ + Location.__getattr__ + Computer.__getattr__ — alle returnen generic-Coroutines für jedes missing-Attr. Maskt AttributeError → mehrere echte Bugs (`is_ready`, `_interface`) silently broken.
