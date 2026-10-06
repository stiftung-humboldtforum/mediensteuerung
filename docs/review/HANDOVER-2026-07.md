# Handover: Dependency-Upgrades mediensteuerung (Stand 2026-07-07)

Anleitung für die Weiterführung des Dependency-Upgrade-Tracks durch ein anderes Modell / eine neue Session. Kontext: Version-Review vom 2026-07-07, aufbauend auf dem 40-Agent-Audit `docs/review/AUDIT-2026-06.md` (2026-06-26). Ältere Dokumente (`UPDATE_PATH.html`, `REPORT.html`) sind historisch — nicht als Versionsquelle verwenden.

## 1. Repo-Topologie & Workflow (zuerst lesen)

- Superproject + 10 Git-Submodules (frontend, 8 Backend-Services, docker-watchdog). **Jeder Bump = Commit im Submodule + Submodule-Pointer-Bump im Superproject.** Kein Monorepo.
- Push-Remotes: die `stiftung-humboldtforum/mediensteuerung-*` Forks aus `.gitmodules` (lokale origins wurden bereits per `git submodule sync` umgezogen; Upstream ist `avorus-soft/*`).
- Python-Deps: pro Service `requirements.in` (Top-Level-Pins) → generiertes, gehashtes `requirements.txt`. Dockerfiles installieren mit `pip install --require-hashes`.
- Frontend: yarn v1, `yarn.lock` ist Quelle der Wahrheit, Docker-Build nutzt `yarn install --frozen-lockfile`.

## 2. Invarianten (nicht brechen)

1. **Hash-Pinning-Workflow** bei jedem Python-Bump:
   ```
   # requirements.in editieren, dann:
   python -m uv pip compile requirements.in -o requirements.txt --universal --generate-hashes --python-version 3.12
   # Verifikation (löst gegen linux/cp312-Wheels auf):
   pip download -r requirements.txt --require-hashes --only-binary=:all: --platform manylinux_2_17_x86_64 --python-version 312 -d /tmp/verify
   ```
   Gotcha: `pip download --platform` wertet Env-Marker gegen den **Host** aus — win32-markierte Deps (pywin32 im watchdog, colorama) schlagen auf Windows scheinbar fehl; stattdessen prüfen, dass der Marker in der Zeile steht.
2. **`vite` bleibt exakt `8.0.16` gepinnt.** 8.1.0 hat eine rolldown-Bundler-Regression am `@popperjs/core`-Re-Export von `@blueprintjs/core` (Build bricht). Bei jedem neuen 8.1.x-Patch: Bump nur mit grünem `tsc && vite build` mergen, sonst Pin behalten.
3. **manager/aiopjlink** bleibt separat per Git-Commit-SHA mit `--no-deps` installiert (kein PyPI-Release, null Dependencies) — nicht in requirements.in ziehen.
4. Frontend-Verifikation minimal: `yarn install` (lockfile-Update committen!) + `tsc && vite build` grün.
5. Nach Hardware-relevanten manager-Änderungen: Gude-PDU-SET und LG-webOS-Pairing/Reconnect sind **noch nicht hardware-validiert** — vor Deploy stagen.

> **Wave-2 Currency-Recheck 2026-07-07 durchgeführt** (`w8u6g2ji1`, 6-Agent-Live-Sweep vs PyPI/npm/DockerHub). Vollständiges Delta unten in §6. Zwei Items erledigt (§7). **Prioritäten korrigiert** — siehe unten. Wichtigste Korrektur: mongo 7.0 EOL ist **2027-08-31, NICHT 2026** — kein zeitkritischer Posten. Neuer Top-Zeitfahrer: `alpine:3.21` EOL 2026-11-01.

## 3. Aufgaben in Reihenfolge (korrigiert 2026-07-07)

### A. ✅ ERLEDIGT — `alpine:3.21` → `3.23` (war zeitkritisch: EOL 2026-11-01, ~4 Mo)
- `backend/mkcert/Dockerfile` gebumpt (statischer Cert-Helper, nur wget + gehashtes Binary — Alpine-Minor ohne Runtime-Effekt). Nicht container-gebaut (kein Docker am Host); Änderung trivial+reversibel.
- Falls längster Support gewünscht: 3.24 (EOL 2028-06-01) statt 3.23 (EOL 2027-11-01).

### B. eslint-Entscheidung (Lint-Stack ist aktuell tot) — OFFEN, braucht Owner-Entscheid
Befund: `frontend/package.json` hat `lint: eslint .` + Plugins (`eslint-plugin-react` 7.37.5, `eslint-plugin-react-hooks` 4.6.0, `eslint-config-prettier` 8.10.2), aber **kein `eslint`** (weder package.json noch yarn.lock) und **keine Config** (`.eslintrc*`/`eslint.config.*`). Optionen — eine wählen, mit dem Owner abstimmen falls unklar:
- (a) Minimal: `eslint ^8.57.1` + `.eslintrc` nachrüsten — **NICHT empfohlen**, eslint 8 ist EOL (2024-10-05, keine Security-Backports).
- (b) Modernisieren (**empfohlen**): eslint `9.39.4` (stabile Flat-Config-Basis, sicherer als direkt 10.6.0) + typescript-eslint `8.63.0` + eslint-plugin-react-hooks `7.1.1` + eslint-config-prettier `10.1.8` + `eslint.config.js` schreiben.
- (c) Entfernen: `lint`-Script + 3 tote Plugins löschen (falls Linting nicht gewollt).
- Nebenbefund: **Orphan-Testfile** `frontend/src/services/api/apiProblem.test.ts` (10 echte Assertions, nutzt jest-Globals) hält `@types/jest` am Leben, aber es gibt keinen Test-Runner → Test läuft nie, blockiert aber `@types/jest`-Drop. Entscheid separat: (i) Vitest einrichten und Tests aktivieren, (ii) Testfile + `@types/jest` löschen (Präzedenz: storage.test.ts wurde in B-Track gelöscht), oder (iii) so lassen.

### C. Kleinkram-Sweep frontend
- ✅ `web-vitals` gedroppt (nirgends importiert, Build grün verifiziert) — siehe §7.
- `@types/jest`: **NICHT drop-bar** ohne Entscheid zum Orphan-Test (siehe B, Nebenbefund) — der Build braucht die Typen für `apiProblem.test.ts`.
- `axios-hooks` 4.0.0 → **5.1.1**: löst die react-19-Peer-Violation, ist aber **verhaltensbrechend** (v5: `refetch()` schreibt jetzt in Cache + leitet Key aus 1. Arg ab, vorher immer cache-skip; Event-Args an refetch ignoriert). Alle `refetch()`-Call-Sites reviewen → **investigate, kein Drop-in**.
- Hygiene optional: `typescript`, `sass`, `prettier`, `@types/*` von `dependencies` nach `devDependencies`.

### D. date-fns 2 → 4 (kleiner als dokumentiert)
- Einzige Nutzung: `frontend/src/utils/formatDate.ts` (format, parseISO, Locale-Imports). v3/v4 ändern Locale-Import-Pfade (`date-fns/locale/ar-SA` → named export aus `date-fns/locale`). Latest 4.4.0.
- Kein MUI-Druck: `@mui/x-date-pickers` 9.5 erlaubt weiterhin `^2.25`, Datums-Adapter ist ohnehin `AdapterMoment`.

### E. Mongo 7.0 → 8.0 (strategisch, KEINE Deadline — EOL 2027-08-31)
- Treiberseitig unblocked: pymongo 4.17 offiziell Server-8.0-fähig, beanie 2.1 erbt via pymongo-async-API (gegen beanie-Matrix gegenchecken).
- **Runbook jetzt in `NOTES.md` → "Mongo upgrade runbook"** (der `See NOTES.md`-Verweis im Compose-Kommentar zeigte auf eine nicht-existente Datei — Datei angelegt, Verweis jetzt gültig). Enthält: Backup, FCV-Check, Single-Major-Hop `mongo:8.0.26`, Point-of-no-Return, Rollback.
- Innerhalb ~12 Mo planen, nicht rushen.

### F. Bekannte Deferred (nur nach explizitem Auftrag)
uvicorn 0.50.x (Verhaltensbrüche — §6), wakeonlan 4.0.0 (WoL-Verhaltensänderung — §6), prettier 3, mermaid 11, i18n-js 3→4, uuid, pynetbox 7.8 (server-gated: NetBox 4.6), TypeScript 5.9/6, @mui/x-Minors (9.8, brechen in Minors!), node:22→24 (EOL 2027-04-30), python 3.12→3.13, Base-Image-Digest-Pinning (nur mit Renovate/Dependabot).

## 4. Vor jeder neuen Welle

Currency-Spot-Check der Fast-Mover gegen PyPI/npm/DockerHub. Letzter voller Live-Sweep: **2026-07-07** (§6). Backend-Locks waren dann vollständig konsistent (identische shared Transitives über alle 6 Services) — diesen Zustand bei Einzel-Bumps erhalten: verwandte Services in derselben Welle nachziehen. Zwei Transitives (`charset-normalizer`, `typing-extensions`) sind fleet-weit identisch gepinnt → jeder Bump davon erzwingt Re-Compile aller 6 Services (batchen).

## 5. Definition of Done pro Bump

1. `requirements.in`/`package.json` geändert, Lock regeneriert, Hash-/Lockfile committed.
2. Verifikation gelaufen (Abschnitt 2; Container-Build wo Docker verfügbar).
3. Commit im Submodule, Pointer-Bump im Superproject, Commit-Message nennt Grund (CVE/EOL/Kompat).
4. Nicht validierbare Punkte (Hardware, Container-Build fehlt) explizit im Commit/PR-Text als offen markiert.

## 6. Wave-2 Currency-Delta (Live-Sweep 2026-07-07)

Vollreport (mit CVE-Refs pro Paket): `w8u6g2ji1` Task-Output. Zusammenfassung:

**Keine ungefixte CVE im Stack.** Alle sicherheitsrelevanten Pins sind bereits auf der gepatchten Release (starlette 1.3.1, cryptography 49.0.0 fixt CVE-2026-39892/-34073, aiohttp 3.14.1 fixt CVE-2026-54273/-54277, eslint-config-prettier 8.10.2 ist die *saubere* Re-Release — NICHT CVE-2025-54313, apisauce→axios 1.18.x ≥ nötigem 1.15.1).

**MOVE-NOW-Kandidaten (currency-only, kein Security-Treiber; verifizierbar per Build/uv, aber wg. fehlendem Container-/Runtime-Test NICHT autonom gebumpt — Owner-Greenlight):**

| Paket | Ist → Ziel | Scope | Grund |
|---|---|---|---|
| charset-normalizer | 3.4.7 → 3.4.8 | Python ×6 | Trivial-Patch. Fleet-Re-Pin — mit typing-extensions batchen. |
| typing-extensions | 4.15.0 → 4.16.0 | Python ×6 | Additiver Backport. Fleet-Re-Pin. `uv lock` vorher: kein `<4.16`-Cap? |
| fastapi | 0.138.1 → 0.139.0 | api | Additiv, hebt Starlette-Floor NICHT (bleibt 1.3.1). Nur mit uv-recompile + Stack-Test. |
| @mui/material + icons | 9.1.2/9.1.1 → 9.2.0 | frontend | Minor in v9, react ^19 OK. Lockstep. styled-engine-sc bleibt 9.1.1 (kein 9.2.0). |
| @blueprintjs/core + icons | 6.16.0/6.11.0 → 6.17.1/6.13.0 | frontend | Patch/Minor in v6, react 19 OK. Lockstep. |
| mobx-state-tree | 7.2.0 → 7.3.1 | frontend | Minor in v7, peer mobx ^6.3.0 OK. |
| moment-timezone | 0.5.48 → 0.6.2 | frontend | Frische IANA-tz-DB (DST-Korrektheit für AV-Scheduling!) + strengere Types. Runtime-safe, nur TS-Build-Risiko. |
| sass | 1.80.0 → 1.101.0 | frontend | Minor Dart-Sass 1.x, API-kompatibel. Nur mehr Deprecation-Warnings. |

**HOLD/INVESTIGATE (Refactor oder externes Gate nötig):**
- `uvicorn` 0.49.0 → 0.50.2 — Verhaltensbrüche: httptools-Floor ≥0.8.0, ProxyHeadersMiddleware konsumiert jetzt doppelte Forwarding-Header, `--ws auto` defaultet auf websockets-**sansio** (Legacy: `--ws websockets` pinnen). WS-Endpoints gegen websockets 16.0 testen. Kein CVE.
- `wakeonlan` 3.3.0 → 4.0.0 (manager) — `send_magic_packet` deprecated (Shim behält `ip_address=`/`port=`, quellkompatibel), aber getaddrinfo-basierte Family-Detection = Runtime-Änderung auf WoL-Pfad. Auf echtem Broadcast-Netz validieren, `send_magic_packet`→`wake()` migrieren. Kein CVE.
- `axios-hooks` 4.0.0 → 5.1.1 — refetch-Cache-Verhalten bricht (siehe §3.C).
- `date-fns` 2.30.0 → 4.4.0 — siehe §3.D.
- `pynetbox` 7.4.1 → 7.8.0 — Code unbetroffen (nur ObjectChange extras→core in 7.6, wird nicht genutzt), aber server-gated: 7.8 validiert vs NetBox 4.6, 7.4.1 vs 4.1–4.4. Gegen Live-NetBox testen.
- `@mui/x-*` 9.5/9.4 → 9.8.0 — MUI-X bricht in *Minors*, Trio zusammen bewegen, erst vetten.
- `typescript` 5.7.3 → 6.0.3 (flippt Defaults) / interim 5.9.x. `prettier` 2.8.8 → 3.9.4 (reformatiert ganzen Tree). `uuid` 9→14 (ESM-only). `mermaid` 10.9.6 → 11 (ESM-Rewrite, aktueller Pin CVE-clean). `i18n-js` 3→4 (Rewrite).

**Container-EOL-Fahrplan:** alpine ✅ (§7); node:22-alpine EOL **2027-04-30** (nächster, Node-24-Migration planen); python:3.12-slim Security bis Okt 2028 (Digest auf 3.12.13 re-pinnen; 3.13 KEIN Drop-in — uv-Locks py-versionsspezifisch); mongo 7.0 EOL 2027-08-31; mosquitto 2.0.22 + debian trixie aktuell.

**Bereits current (no-change):** react/react-dom 19.2.7, pydantic 2.13.4 (+core 2.46.4 gepaart, NICHT einzeln bewegen), beanie 2.1.0, fastapi-users 15.0.5, pymongo 4.17.0, aiomqtt 2.5.1, requests 2.34.2, urllib3 2.7.0, cryptography 49.0.0, xknx 3.16.0, pysnmp 7.1.27, aiowebostv 0.7.5, aiohttp 3.14.1, mobx 6.16.1, styled-components 6.4.3, notistack 3.0.2, @fullcalendar/* 6.1.21, vite 8.0.16 (HOLD-Pin, siehe unten) u.v.m.

**vite bleibt exakt 8.0.16:** 8.1.3 ist latest, aber Changelogs 8.1.1/8.1.2/8.1.3 bumpen rolldown NICHT → die @popperjs/@blueprintjs-`placements`-Regression (vitejs/vite#22835) ist NICHT nachweislich gefixt. Re-check erst wenn ein Release rolldown bumpt / #22779 schließt.

## 7. Ausgeführt 2026-07-07 (dieser Durchgang, NICHT committed/pushed)

Working-Tree-Änderungen im Superproject + frontend-Submodule:
1. **frontend/package.json + yarn.lock**: `web-vitals` entfernt (nirgends importiert; `index.tsx` sauber). `yarn install` + `tsc && vite build` **grün verifiziert** (nur Pre-existing Chunk-Size/Plugin-Timing-Warnings, keine Errors).
2. **backend/mkcert/Dockerfile**: `alpine:3.21` → `alpine:3.23` (EOL-Fahrer 2026-11-01). Nicht container-gebaut (kein Docker am Host); statischer Cert-Helper, reversibel.
3. **NOTES.md** (neu, Repo-Root): Mongo-Upgrade-Runbook → repariert den toten `See NOTES.md`-Verweis in `docker-compose.yml`.
4. **docs/review/HANDOVER-2026-07.md** (diese Datei): Mongo-EOL-Fehler korrigiert (2027 statt 2026), Prioritäten neu, §6/§7 ergänzt.

Commit/Push offen (Submodule-Commit im frontend-Fork + Pointer-Bump im Superproject; NOTES.md/HANDOVER im Superproject). Owner-Entscheide offen: eslint (§3.B), Orphan-Test, MOVE-NOW-Batch-Greenlight.
