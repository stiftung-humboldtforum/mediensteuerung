# Stage 2d — `backend/api` Review

**Date:** 2026-05-27
**Scope:** FastAPI HTTP+WS-Layer (`backend/api/`)
**Reviewer:** caveman:cavecrew-reviewer (Opus 4.7)
**Filter:** cosmetic excluded; CVE/Updates + Auth + Data-Path-Risiken

---

## Findings

### CRITICAL

| # | Location | Problem | Fix |
|---|----------|---------|-----|
| C1 | `Dockerfile:5` | 🚨 **`fastapi==0.95.1`** (Apr 2023) — CVE-2024-24762 (ReDoS in python-multipart via Form) | bump >=0.110, dann Pydantic-v2-Migration |
| C2 | `Dockerfile:10` | 🚨 **`pydantic==1.10.7`** — multiple CVEs (Regex-DoS), v1 unmaintained außer Security-Stream | 1.10.latest oder v2-Migration |
| C3 | `app.py:23,26` | 🚨 **CORS `allow_origins=['*']` + `allow_credentials=True`** — Spec-Violation, Browser ignorieren credentials bei Wildcard, Anti-Pattern | explizite Origin-Liste |
| C4 | `app.py:96` | 🚨 **JWT-Refresh ohne Revocation/jti-Tracking** — gestohlener Token kann indefinitely refreshed werden | jti-Blacklist oder kurze Lifetime |
| C5 | `routes/base.py:91,93` | 🚨 **WS-Auth: `manager.connect(websocket)` BEFORE Token-Validation.** Unauth-Client accepted. Plus close-code `1000` (normal) statt `1008` (policy) | Token validate → dann accept |
| C6 | `routes/base.py:87` | 🚨 **WS-Token via Query-String** — landet in Proxy-Logs, Browser-History, Referrer-Leak | Subprotocol oder First-Message-Auth |
| C7 | `routes/config.py:18,23` | 🚨 GET/POST `/config/` — POST schreibt `Annotated[list, Body()]` ohne Schema-Validation via `yaml.dump` nach `/manager/config/config.yml`. Admin-only, aber Admin-Compromise → arbitrary YAML-Overwrite | Schema-Model + Validation |
| C8 | `misc/data.py:83` | 🚨 **`nb.http_session.verify = False`** — TLS-Verify deaktiviert für NetBox-API → Credentials+Daten MITM-Risiko | proper CA-Bundle |

### HIGH

| # | Location | Problem | Fix |
|---|----------|---------|-----|
| H1 | `Dockerfile:11` | ⚠️ `uvicorn==0.22.0` — h11-Desync/Header-Smuggling-Fixes in later | >=0.30 |
| H2 | `Dockerfile:8` | ⚠️ `websockets==11.0.3` — CVE-2024-29940-class fixed in 12.x | >=12.0 |
| H3 | `Dockerfile:7` | ⚠️ `fastapi-users[beanie]==11.0.0` — current 13.x, multiple Auth-Flow-Fixes; nutzt noch Pydantic v1 | plan upgrade |
| H4 | `Dockerfile:6` | ⚠️ `fastapi-mqtt==1.0.7` — current 2.x | upgrade |
| H5 | `Dockerfile:13` | ⚠️ **pynetbox community-Fork `devon-mar/openapi-3.5` via `git+https`** ohne Hash — Supply-Chain-Risk | Vendor oder Commit-SHA pinnen |
| H6 | `Dockerfile:1` | ⚠️ `python:3.11-slim` ohne Digest-Pin | sha256 digest |
| H7 | `app.py:50,60,74,78` | ⚠️ Bare `except`, untyped int-parse auf MQTT-Topic, ungetaggte Broadcast aller MQTT-Messages an alle WS-Clients | typisierte excepts, validate, filter |
| H8 | `app.py:102` | ⚠️ `authorization.split(" ")[1]` IndexError-Risk | defensive parse |
| H9 | `connection_manager.py:13,18,30` | ⚠️ Bare except, list-mutation während iteration, kein per-socket-error-handling | typisierte excepts, list-copy |
| H10 | `db.py:10` | ⚠️ MongoDB-URI `mongodb://` ohne TLS | TLS oder srv |
| H11 | `init_user.py:50,51,54` | ⚠️ `EmailStr(None)` Risk, `print(user)` möglicher Password-Leak, bare except | validate env, redact, narrow except |
| H12 | `mqtt.py:19,28,32` | ⚠️ MQTTv311 hardcoded, QoS 0 verliert Messages bei Reconnect, `knx/#` wildcard zu breit (broadcast leaked non-switch topics an WS) | v5 prüfen, QoS 1, narrow subscribe |
| H13 | `misc/__init__.py:10` | ⚠️ `authenticate_token` neue user_db+user_manager pro Call — teuer pro WS-Reconnect | Cache/reuse |
| H14 | `misc/data.py:48,55,62,114` | ⚠️ `self.lock.acquire()` ohne try/finally — Exception zwischen acquire+release → Deadlock | `with self.lock:` |
| H15 | `misc/data.py:71` | ⚠️ Watchdog re-creates dataloader bei error — alte Thread läuft weiter (daemon ≠ killable) | thread-lifecycle fix |
| H16 | `misc/data.py:39` | ⚠️ `__aenter__` busy-waits `asyncio.sleep(1)` ohne timeout — bei langsamer NetBox-Fetch (5min) blockiert | wait_for |
| H17 | `misc/data.py:79` | ⚠️ `NETBOX_API_TOKEN` None silent → pynetbox unauth-Requests | validate |
| H18 | `misc/data.py:136,139` | ⚠️ IndexError bei NetBox-Race, N+M HTTP-Calls sync in Load-Loop | `next()` default, parallelize |
| H19 | `models/calendar.py:45,24,32` | ⚠️ Pydantic v1 Optional ohne `= None` → PATCH-Semantik broken (alle Felder required) | `= None` defaults |
| H20 | `routes/base.py:32,38,33` | ⚠️ `asyncio.get_event_loop()` import-time deprecated (3.10+, raised in 3.12), Thread-Start vor Loop konstruiert, Old-Thread mutiert Shared-State nach on_error | startup-hook, lifecycle fix |
| H21 | `routes/base.py:78,79` | ⚠️ `method_name` untyped Raw-Path-Param direkt in MQTT-Topic interpoliert; `params: dict` Mass-Assignment | Enum + Model |
| H22 | `routes/base.py:87` | ⚠️ Long-lived WS — Token-Expiry nach Connect nie re-checked | periodic re-validate |
| H23 | `routes/base.py:96,100,103,104` | ⚠️ Bare except, kein message-size-limit, KeyError silent, client-controlled `target` in MQTT-Topic | narrow except, max_size, validate, enum |
| H24 | `routes/calendar.py:23,25,36` | ⚠️ `_id` from client → upsert any user can overwrite others' events; Type-Confusion (ObjectId vs str); `delete_event(id: str)` ohne ObjectId-Validation | Owner-Model, type-fix, validate |
| H25 | `routes/config.py:24` | ⚠️ Kein atomic write — partial write bei Crash truncated config.yml | tmp + `os.replace` |
| H26 | `routes/knx.py:25` | ⚠️ `save_event` aus MQTT-Handler ohne Auth, Exceptions silent | confirm intent, log |
| H27 | `schemas.py:20,28` | ⚠️ `BaseUserCreate`/`BaseUserUpdate` exposed `is_superuser`/`is_active`/`is_verified` — Mass-Assignment, Self-Elevation auf User-Update-Endpoint möglich | exclude in schema |
| H28 | `users.py:48` | ⚠️ JWT-Lifetime 48h ohne Rotation/Revocation | shorter + refresh-rotation |
| H29 | `users.py:30,36` | ⚠️ `print(reset_token)` + `print(verification_token)` — Token in stdout logged | redact/remove |
| H30 | `users.py:67` | ⚠️ `GET /users/` returnt voll User-Documents inkl. `hashed_password` (BeanieBaseUser-Default) — Verify Beanie-Schema-Exclude. **Wahrscheinlich Leak** | response_model mit exclude |
| H31 | `users.py:83` | ⚠️ Bulk-load alle Users ohne Pagination | limit/skip |

### MEDIUM

| # | Location | Problem | Fix |
|---|----------|---------|-----|
| M1 | `Dockerfile:2` | ⚡ `apt-get` ohne `--no-install-recommends` / `rm -rf /var/lib/apt/lists/*` — Image-Bloat + curl+git in prod surface | tighten |
| M2 | `Dockerfile:3` | ⚡ Keine `requirements.txt` — Versionen inline, transitive Deps unpinned | Lock-File (uv/pip-tools) |
| M3 | `app.py:33` | ⚡ Deprecated `@app.on_event('startup')` — removed in modern FastAPI | lifespan context |
| M4 | `app.py:154` | ⚡ SPA-Fallback gibt index.html für any 404 — relies on Starlette safe-join | dokumentieren |
| M5 | `connection_manager.py:6` | ⚡ Kein per-socket Auth-Identity — alle MQTT-Events an alle WS-Clients broadcast | confirm intent / filter |
| M6 | `db.py:10,11` | ⚡ KeyError-Crash bei missing env, kein pool-size/timeout config | validate + tune |
| M7 | `init_user.py:45` | ⚡ Unbounded Recursion bei mismatch-Password-Input | Loop |
| M8 | `mqtt.py:7` | ⚡ Cert-Paths hardcoded, fail-loud at module-import | lazy load |
| M9 | `models/__init__.py:5` | ⚡ `PyObjectId` Pydantic v1 `__get_validators__`/`__modify_schema__` — entfernt in v2 | migration |
| M10 | `models/calendar.py:38` | ⚡ `allow_population_by_field_name` → `populate_by_name` in Pydantic v2 | migration |
| M11 | `models/calendar.py:24,32` | ⚡ Optional ohne `= None` default (M-level analog zu H19) | defaults |
| M12 | `routes/calendar.py:32,42` | ⚡ Returnt `status.HTTP_404_NOT_FOUND` (int) als Body — Client kriegt 200 OK mit Body "404" | `raise HTTPException(404)` |
| M13 | `routes/knx.py:18` | ⚡ `get_events` ohne Pagination | limit/skip |
| M14 | `schemas.py:17` | ⚡ `Config: orm_mode = True` — v1, in v2 `from_attributes` | migration |
| M15 | `users.py:48` | ⚡ HS256 mit einem shared Secret für reset+verification+access — single secret pwn alles | split |
| M16 | `users.py:17` | ⚡ `API_SECRET` KeyError at import, kein min-length | validate >=32 |
| M17 | `users.py:69` | ⚡ `is_active: bool = Query(None)` Type-Lüge — sollte `Optional[bool] = None` | type fix |

---

## Summary

| Severity | Count |
|----------|------:|
| CRITICAL | 8 |
| HIGH | 31 |
| MEDIUM | 17 |
| LOW | 0 |
| **TOTAL** | **56** |

## Update-Targets (Versions)

| Package | Aktuell | Empfehlung | CVE/Issue |
|---------|---------|-----------|-----------|
| `fastapi` | 0.95.1 | >=0.110.x (oder v2-Migration auf >=0.110) | CVE-2024-24762 |
| `pydantic` | 1.10.7 | 1.10.latest oder v2 | Regex-DoS class |
| `uvicorn` | 0.22.0 | >=0.30 | h11-Desync-Fixes |
| `websockets` | 11.0.3 | >=12.0 | CVE-2024-29940-class |
| `fastapi-users[beanie]` | 11.0.0 | 13.x | Auth-Flow-Fixes |
| `fastapi-mqtt` | 1.0.7 | 2.x | major |
| `pynetbox` | git-Fork | upstream + Commit-Pin | Supply-Chain |
| `python` | 3.11-slim (floating) | 3.12 oder 3.11 mit digest | reproducibility |

## Hauptmuster

1. **WS-Auth-Schwachstellen:** Token-in-Query, accept-before-validate, kein expiry-check für long-lived Sessions, Connection bei Auth-Fail mit Normal-Code geschlossen.
2. **CORS-Anti-Pattern:** Wildcard-Origin + Credentials — Browser-Spec verbietet, Server akzeptiert silent.
3. **Pydantic-v1-Lock-In:** Models, Schemas, fastapi-users alle auf v1 — Migration-Debt für gesamte v2-Upgrade-Story.
4. **Mass-Assignment im User-Update:** `is_superuser` exposed → Self-Elevation-Risk.
5. **TLS-Verify-Off bei NetBox:** Credentials + Daten MITM-Window.
6. **MQTT-Topic-Injection:** Client-controlled `target`/`method_name` direkt in Publish-Topic interpoliert.
7. **Reload-Mode in Prod:** Source-Bind-Mount + `uvicorn --reload` (siehe Stage 1).
