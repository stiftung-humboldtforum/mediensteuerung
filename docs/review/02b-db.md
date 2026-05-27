# Stage 2b — `backend/db` Review

**Date:** 2026-05-27
**Scope:** MongoDB-Init (`backend/db/docker-entrypoint-initdb.d/init-mongo.js`)
**Reviewer:** caveman:cavecrew-reviewer (Opus 4.7)
**Filter:** cosmetic excluded; auth + data-integrity + update focus

---

## Findings

### CRITICAL

| # | Location | Problem | Fix |
|---|----------|---------|-----|
| C1 | `init-mongo.js` + `docker-compose.yml:7,15` | 🚨 **MongoDB-Auth NIE aktiviert.** Compose setzt `MONGO_INITDB_USERNAME`/`PASSWORD` (Non-Standard, Image ignoriert), keine `MONGO_INITDB_ROOT_USERNAME/PASSWORD`, `mongod --quiet` ohne `--auth`-Flag. DB offen für jeden mit Port-27017-Zugriff (host network). `db.createUser`-Call ist dekorativ. | Compose-Vars zu `MONGO_INITDB_ROOT_USERNAME/PASSWORD` umbenennen für Root, App-Creds separat, `--auth` in mongod-Command |
| C2 | `init-mongo.js:7` vs. `backend/api/db.py:14`, `backend/calendar/db.py:12` | 🚨 **DB-Name-Mismatch.** Init-Script grantet App-User `readWrite` nur auf `MONGO_INITDB_DATABASE` (z.B. `avorus`). API connected zu `client['users']`, Calendar zu `client['calendar']`. Sobald Auth aktiviert wird → komplette App tot. | `readWrite` auf `users` + `calendar` granten ODER Daten in eine DB konsolidieren |

### HIGH

| # | Location | Problem | Fix |
|---|----------|---------|-----|
| H1 | `init-mongo.js:2` | ⚠️ Connection-String ohne `authSource=admin`, Script läuft gegen `MONGO_INITDB_DATABASE` statt `admin`. Mit Real-Root-Auth: `db.createUser()` in Non-Admin-DB erstellt **per-db** User, keinen Cluster-User. | `db.getSiblingDB('admin')` oder Mongo-Init-Lifecycle nutzen |
| H2 | `init-mongo.js` | ⚠️ **Keine Index-Bootstrap.** fastapi-users (Beanie) braucht unique index auf `users.email`/`id`. Manager-Queries (NetBox-Sync, State) ohne Indexes. Cold-Start langsam, Duplikate möglich. | `db.users.createIndex({email:1},{unique:true})` + collection-spezifische Indexes |
| H3 | `init-mongo.js` | ⚠️ **Keine JSON-Schema-Validation.** Production läuft Jahre auf impliziter Schema — jeder malformed Write korrumpiert silent. | `collMod`/`createCollection` mit `validator` auf core Collections |
| H4 | `init-mongo.js` | ⚠️ **Keine Backup-Strategie.** Bind-Volume `./backend/db/mongo-volume` — FS-Level-Backup braucht mongod-Stop. | sibling `mongodump`-Cron-Service oder Procedure |

### MEDIUM

| # | Location | Problem | Fix |
|---|----------|---------|-----|
| M1 | `docker-compose.yml:4` | ⚡ MongoDB `6.0.5` — 6.0 EOL Juli 2025, 6.0.5 hat known CVEs gefixed in späteren 6.0.x | Upgrade `7.0.x` LTS (Driver-Kompat testen) |
| M2 | `init-mongo.js:8` | ⚡ App-Creds in `.env` plaintext at rest (host neben compose). Aktuell egal (kein Auth), aber post-Fix relevant. | docker secrets / external secret manager |
| M3 | `init-mongo.js` | ⚡ **Init-Script läuft nur bei frischem `/data/db`.** Re-Run gegen existing `mongo-volume` no-op. Future Role/Index/Schema-Changes silent fail. | Idempotent Migration-Runner |
| M4 | `docker-compose.yml:14` | ⚡ `network_mode: host` exposed mongod auf 27017 jedem Interface. Mit fehlender Auth (C1) → DB von jedem Host-reachable Client erreichbar. | Bridge-Network oder bind `127.0.0.1` |

### LOW

| # | Location | Problem | Fix |
|---|----------|---------|-----|
| L1 | `backend/db/` | ℹ️ Kein README/OPS-Notes zu Init-Lifecycle, manueller User-Provisioning, Upgrade-Path | Doc schreiben |

---

## Summary

| Severity | Count |
|----------|------:|
| CRITICAL | 2 |
| HIGH | 4 |
| MEDIUM | 4 |
| LOW | 1 |
| **TOTAL** | **11** |

## Update/Hardening-Targets

| Bereich | Aktion | Priorität |
|---------|--------|-----------|
| Auth aktivieren | `MONGO_INITDB_ROOT_*` Vars + `mongod --auth` | CRITICAL |
| DB-Name-Konsistenz | App + Init-Script angleichen | CRITICAL |
| MongoDB-Version | 6.0.5 → 7.0.x LTS | MEDIUM |
| Indexes + Validation | Init-Script erweitern | HIGH |
| Backup-Pipeline | mongodump-Service oder cron | HIGH |
| Idempotent Init | Migration-Runner | MEDIUM |

## Hauptmuster

1. **Auth-Theater:** Credentials existieren in env + Code, aber DB akzeptiert unauth-Connections. System läuft auf Kombination "Auth wäre aktiviert wenn jemand `--auth` setzen würde + Env-Vars die richtigen Namen hätten + DB-Grants konsistent wären".
2. **Init nur once:** Schema/Roles/Indexes nur bei frischer Volume gesetzt — keine Migration-Story.
3. **Versions-Drift:** MongoDB 6.0 EOL bereits 10 Monate her.
