# Stage 2f — `backend/calendar` Review

**Date:** 2026-05-27
**Scope:** Calendar/Event-Trigger-Service (`backend/calendar/`)
**Reviewer:** caveman:cavecrew-reviewer (Opus 4.7)
**Filter:** cosmetic excluded; TZ/Persistence/Reconnect-Focus

---

## Findings

### CRITICAL

| # | Location | Problem | Fix |
|---|----------|---------|-----|
| C1 | `Dockerfile:7` | 🚨 **`aiomqtt==1.1.0`** — keine Auto-Reconnect-Loop, API komplett anders als 2.x. Bei Broker-Disconnect → Service tot. Selbes Pattern wie Manager (Stage 2e). | 2.x + Reconnect-Loop |
| C2 | `app.py:30` | 🚨 Kein MqttError/Reconnect-Wrapper um `async with Client(...)` — Broker-Disconnect kills Service permanent. | `while True: try: ... except MqttError: sleep` |
| C3 | `app.py:33` | 🚨 Subscription nur **einmal** vor `messages()`-Context — bei Reconnect nicht re-issued. | inside reconnect-loop |
| C4 | `calendar_service.py:14` | 🚨 `message_queue` plain-list mutiert von `callback()` (sync) + `start()` (async) — Single-Threaded asyncio rettet vor Korruption, aber Publishes lost-Risk real. | deque + lock |
| C5 | `calendar_service.py:54` | 🚨 **Keine Persistenz von `is_happening`** über Restart. Bei Restart all Events reset zu False → currently-happening-Event feuert **`start`-Callback erneut** → Duplicate `start` an Manager. Keine Idempotenz. | mongo-persist + load |
| C6 | `calendar_service.py:55` | 🚨 `localizer.localize(datetime.now())` — naive system-local-time + Berlin-tz-Label. Container-TZ ≠ Europe/Berlin (default UTC slim) → Events feuern 1-2h off. | `datetime.now(localizer)` mit zoneinfo |
| C7 | `calendar_service.py:63` | 🚨 `message_queue.pop()` aus ENDE (LIFO) — Events out-of-Order published. **`end` kann VOR `start` published werden.** | `pop(0)` oder `deque.popleft()` |
| C8 | `db.py:6` | 🚨 MongoDB-URL ohne TLS — plaintext Credentials + Daten on-the-wire | `?tls=true` + CA |
| C9 | `event.py:36` | 🚨 `parser.parse(start)` ohne try/except — malformed iCal/ISO crashed `load_events()`, lässt `self.events` partially built | try/except + skip |
| C10 | `event.py:40` | 🚨 `dateutil.rrule.rrulestr(rrule)` raises ValueError bei malformed RRULE — selber Crash-Path | wrap + log + skip |
| C11 | `event.py:67` | 🚨 `self.start.replace(tzinfo=now.tzinfo)` — clobbert original-tz von dateutil. **Wall-clock vs absolute-Time-Bug across DST.** | `astimezone(now.tzinfo)` |
| C12 | `event.py:78` | 🚨 **Hardcoded `if self.id == 72:` Debug-Log in Production** | entfernen |

### HIGH

| # | Location | Problem | Fix |
|---|----------|---------|-----|
| H1 | `Dockerfile:1` | ⚠️ Python 3.11 — trailing two releases, Security-Only-Mode bald | 3.12-slim |
| H2 | `Dockerfile:6` | ⚠️ `anyio==3.6.2` — 4.x current, CVE-adjacent Fixes | bump 4.x |
| H3 | `Dockerfile:10` | ⚠️ `motor==3.3.1` — PyMongo 4.9+ hat native async, motor in maintenance | motor 3.6.x oder PyMongo-async migration |
| H4 | `Dockerfile:10` | ⚠️ Keine `requirements.lock`, kein Hash-Pinning, kein Non-Root-User | hash-pinned + `USER nobody` |
| H5 | `app.py:32` | ⚠️ `subscribe('api/calendar/update')` ohne qos — Default 0 (api published qos=1) → Messages lost bei transient drop | `qos=1` |
| H6 | `app.py:36` | ⚠️ `load_events()` seriell in Message-Loop — Mongo-slow → Updates back up | try/except + log |
| H7 | `app.py:37` | ⚠️ `calendar_task` nie cancelled — on-shutdown task-leak; on-exception scheduler feuert gegen dead client | finally cancel |
| H8 | `calendar_service.py:55` | ⚠️ 5-sec-Tick + `now > start and now < end` — Events <5s können ganz verpasst werden | catch-up oder min-duration |
| H9 | `calendar_service.py:62` | ⚠️ `sleep(5)` zwischen tick + publish-drain — Callback für NOW-Event delayed up to 5s | drain vor sleep |
| H10 | `calendar_service.py:64` | ⚠️ Wenn `publish` raises (MqttError), remaining queued Messages dropped vor send completes | re-queue oder persistent |
| H11 | `calendar_service.py:65` | ⚠️ Publish-Topic `calendar/{edge}/{type}/{method}` ohne retained-Flag — late-Subscribers (Manager-Restart) miss in-flight `start` | retain + Manager idempotent |
| H12 | `db.py:7` | ⚠️ KeyError at import-time bei missing env-var — Container crash-loop ohne useful log | explicit check |
| H13 | `event.py:40` | ⚠️ `rrulestr` ohne `dtstart=` → naive datetime; kombiniert mit L67-68 `.replace(tzinfo=...)` strippt real-tz. Cross-DST-Occurrences shift 1h | `dtstart=self.start` (tz-aware) |
| H14 | `event.py:46` | ⚠️ `int(duration / 1000)` truncated — duration in ms; 999ms → 0sec | `timedelta(seconds=duration/1000.0)` |
| H15 | `event.py:59` | ⚠️ `is_happening` setter keine Idempotenz across Restart (siehe C5) | persist last state |
| H16 | `event.py:69` | ⚠️ Compares `now` vs `self.start` (original-tz) statt `start` (rebound L67). Inkonsistent zwischen rrule-Branch (rebound) und non-rrule (original) | konsistent |
| H17 | `event.py:74` | ⚠️ Heuristik `(start - duration).day != start.day` — fragil um Monats/Jahres-Boundary + DST-25h-Tage | `rrule.before(now) <= now < before+duration` |
| H18 | `event.py:84` | ⚠️ `is_happening = False` am Update-Ende wenn kein Branch matched — `rrule.after(today)` returnt NEXT occurrence (already past today midnight) → current-aber-active-occurrence missed | `.before(now)` |
| H19 | `misc.py:6` | ⚠️ Hardcoded `Europe/Berlin` + `datetime.now()` ohne tz-info — depends on Container-TZ | zoneinfo + aware-datetime |
| H20 | `mqtt_client.py:7` | ⚠️ Kein Last-Will — Manager hat keinen Weg toten Calendar-Service zu detecten | `will_message='offline'` |

### MEDIUM

| # | Location | Problem | Fix |
|---|----------|---------|-----|
| M1 | `Dockerfile:2` | ⚡ Kein apt-update + Base-Digest nicht gepinnt | `@sha256:` digest |
| M2 | `Dockerfile:5` | ⚡ `asyncclick==8.1.3.4` outdated | refresh |
| M3 | `Dockerfile:8` | ⚡ `python-dateutil==2.8.2` — 2.9.0 (März 2024) tz-Fixes | 2.9 |
| M4 | `Dockerfile:9` | ⚡ `pytz==2023.3.post1` — TZ-Data outdated, DE DST/Legal-Time-Changes lag | 2024.x+ |
| M5 | `app.py:19` | ⚡ `asyncio.get_event_loop()` deprecated 3.10+, removed 3.12 wenn kein running loop | `get_running_loop` |
| M6 | `app.py:37` | ⚡ `await calendar_task` unreachable — outer `async for` nur exit on close | `gather` oder `TaskGroup` |
| M7 | `db.py:9` | ⚡ Kein `serverSelectionTimeoutMS` / connection-timeout | explizit |
| M8 | `db.py:10` | ⚡ `AsyncIOMotorClient` at module-import → bound zu loadenden Loop. Bei `asyncio.run`-new-Loop → motor broken | lazy-init |
| M9 | `event.py:95` | ⚡ `set_options` resets `_is_happening` nicht — bei Window-Edit fragile | document oder recompute |
| M10 | `mqtt_client.py:6` | ⚡ Kein `__aexit__` override — Base handelt, aber divergiert von Manager-Variant | verify |

---

## Summary

| Severity | Count |
|----------|------:|
| CRITICAL | 12 |
| HIGH | 20 |
| MEDIUM | 10 |
| LOW | 0 |
| **TOTAL** | **42** |

## Update-Targets

| Package | Aktuell | Empfehlung | Grund |
|---------|---------|-----------|-------|
| `aiomqtt` | 1.1.0 | 2.4.x | Reconnect-Story + API-Major |
| `motor` | 3.3.1 | 3.6.x oder PyMongo-async | maintenance only |
| `python-dateutil` | 2.8.2 | 2.9 | TZ-Fixes |
| `pytz` | 2023.3.post1 | 2024.x+ | TZ-DB-Outdated |
| `anyio` | 3.6.2 | 4.x | Major behind |
| `python` | 3.11 | 3.12 | Lifecycle |
| TZ-Stack | `pytz`+`Europe/Berlin` Hardcode | `zoneinfo` + env-config | Modern Python TZ-API |

## Code-Bugs-Top-Liste

1. **`event.py:78`** — Hardcoded `if self.id == 72:` Debug-Code in Production
2. **`event.py:67`** — TZ-replace clobbert original-tz → DST-Bug (1h-Shift twice/year)
3. **`calendar_service.py:63`** — LIFO-Pop kann `end` VOR `start` published feuern
4. **`calendar_service.py:54`** — Keine Restart-Idempotenz → Duplicate `start`-Event nach Restart
5. **`calendar_service.py:55`** — `datetime.now()` ohne TZ-Awareness → 1-2h-Off bei UTC-Container
6. **`event.py:36,40`** — Malformed iCal/RRULE crashed gesamten `load_events()`
7. **`app.py:30,33`** — kein Reconnect, kein Resubscribe (selbes Pattern wie Manager)

## Hauptmuster

1. **TZ-Verarbeitung systematisch fragil:** `datetime.now()` ohne tz, `pytz.localize` auf naive datetime, `.replace(tzinfo=...)` statt `astimezone`, hardcoded Berlin in misc.py. DST-Übergänge (zweimal/Jahr) potenzielle Off-by-1h-Bugs.
2. **Restart-Idempotenz fehlt:** State (`is_happening`) nicht persistent, Events feuern bei Restart erneut.
3. **Reconnect-Pattern identisch broken wie Manager:** aiomqtt 1.x, eine Subscribe, kein retry.
4. **Production-Debug-Code:** `if self.id == 72: logger.info(...)` — Live-Artifact.
5. **Event-Order-Garantie verletzt:** LIFO-Pop produziert event-end-before-start-Race.
