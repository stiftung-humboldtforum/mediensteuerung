# Operational Notes

Runbooks and operational context for the mediensteuerung stack that don't belong in code comments. Dependency-upgrade tracking lives in `docs/review/` (`AUDIT-2026-06.md`, `HANDOVER-2026-07.md`).

## Mongo upgrade runbook

Referenced from `docker-compose.yml` (service `db`). Applies to the `mongo:7.0.x` → `mongo:8.0.x` major upgrade.

**Status / urgency (2026-07-07):** NOT urgent. MongoDB 7.0 EOL is **2027-08-31** (~14 months runway; the 7.0/8.0 lifecycles were extended from 3→4 years — earlier notes saying "Aug 2026" were wrong). Current pin `mongo:7.0.37` is the newest 7.0 patch and carries all 7.0 security fixes. Schedule the 8.0 hop as a planned change within ~12 months, not a rush.

**Driver readiness:** `pymongo==4.17.0` officially supports server 8.0; `beanie==2.1.0` rides pymongo's async API and inherits 8.0 support (verify against beanie's own compat matrix before cutover — lower confidence than the pymongo claim). No stack-blocking breaking change identified.

**Key property — FCV gating:** the binary upgrade is reversible UNTIL `setFeatureCompatibilityVersion` is raised. A 7.0 binary starts fine on FCV-6.0 data; an 8.0 binary starts fine on FCV-7.0 data. Raising FCV to "8.0" is the **point of no return** (rollback to 7.0 then requires a restore).

**Procedure (single major hop, do NOT skip to 8.1/8.2):**

1. **Backup first.** Snapshot / copy `./backend/db/humboldt-mongo-volume` (bind-mounted at `/data/db`) with the container stopped, or take a `mongodump`. This is the rollback path once FCV is raised.
2. **Confirm current FCV is "7.0"** before touching the image:
   ```
   docker exec -it db mongosh --quiet --eval 'db.adminCommand({getParameter:1, featureCompatibilityVersion:1})'
   ```
   If it still reports "6.0", raise it to "7.0" first and let the cluster run healthy for a bit (this step is itself reversible only until you'd want to go back below 7.0):
   ```
   docker exec -it db mongosh --quiet --eval 'db.adminCommand({setFeatureCompatibilityVersion:"7.0", confirm:true})'
   ```
3. **Swap the image** in `docker-compose.yml`: `image: mongo:7.0.37` → `image: mongo:8.0.26` (or newest 8.0.x at the time). Recreate the container:
   ```
   docker compose up -d db
   ```
   Watch the healthcheck go healthy and tail logs for upgrade warnings. At this point the binary is 8.0 but FCV is still "7.0" — **still reversible** (revert the image, recreate).
4. **Verify** the app fleet (api, calendar, manager, knx, fac) reconnects and behaves. Run for a soak period.
5. **Raise FCV to "8.0"** — the point of no return:
   ```
   docker exec -it db mongosh --quiet --eval 'db.adminCommand({setFeatureCompatibilityVersion:"8.0", confirm:true})'
   ```
6. Update `docker-compose.yml` pin + commit; note in the commit that FCV was raised (irreversible).

**Rollback:** before step 5, revert the image pin and `docker compose up -d db`. After step 5, restore the pre-upgrade backup from step 1 onto a 7.0.37 container.

**Next hop after 8.0:** 8.0 EOL is 2029-10-31. No pressure.
