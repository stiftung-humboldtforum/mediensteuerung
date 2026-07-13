"""Scheduler service: resolves opening windows and publishes target states.

Publishes per location (retained AND periodically re-published — the broker
runs without persistence, so retained alone does not survive a broker
restart, KALENDER-REDESIGN.md §3.3):

    schedule/target/{location_id}
        {"state": "on"|"off", "ready_by": iso|null, "window": {...}|null,
         "next_window": {...}|null, "published_at": iso}

    schedule/heartbeat
        {"published_at": iso, "locations": n, "degraded": bool}

Windows from adjacent days are merged before the state decision, so a window
spilling past midnight that overlaps or touches the next day's window reports
the true operating end. ``next_window`` looks ahead up to LOOKAHEAD_DAYS;
``null`` means "nothing scheduled within that horizon".

Fail-safe rules (§3.6): a Mongo read error or an invalid document never turns
anything off — documents are validated on load, the engine is dry-run before
it replaces the last-known-good one, and one broken location never blocks the
other locations or the heartbeat. Consumers must treat a missing target as
"no action", never as "off".

Health: every successful tick touches HEALTH_FILE (only while a plan is
loaded); the container healthcheck alerts when the file goes stale.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from misc import SCHEDULE_TZ, logger
from resolution import ResolutionEngine, parse_hhmm

TICK_SECONDS = 30
RELOAD_TICKS = 10          # periodic reload every 10 ticks (~5 min)
LOOKAHEAD_DAYS = 14
HEALTH_FILE = Path('/tmp/scheduler-health')

EFFECT_KINDS = ('hours', 'extend', 'closed')


def validate_exception(doc) -> str | None:
    """Returns a reason string if the document is unusable, else None."""
    scope = doc.get('scope') or {}
    effect = doc.get('effect') or {}
    if doc.get('date') is None and not doc.get('range'):
        return 'weder date noch range gesetzt'
    if scope.get('kind') not in ('house', 'areas'):
        return f"scope.kind '{scope.get('kind')}' unbekannt"
    if scope.get('kind') == 'areas' and not scope.get('area_ids'):
        return 'scope.areas ohne area_ids'
    if effect.get('kind') not in EFFECT_KINDS:
        return f"effect.kind '{effect.get('kind')}' unbekannt"
    try:
        if effect['kind'] == 'hours':
            parse_hhmm(effect['open']), parse_hhmm(effect['close'])
        elif effect['kind'] == 'extend':
            parse_hhmm(effect['close'])
    except (KeyError, ValueError, AttributeError):
        return 'effect-Zeiten fehlen oder sind kein HH:MM'
    return None


class Scheduler:
    def __init__(self, client=None):
        self.client = client
        self.engine = None          # last-known-good engine
        self.degraded = False
        self.expected_lead_min = 30
        self._published: set = set()  # location_ids with a retained target
        self._ticks = 0

    async def load(self):
        """Reload profile/exceptions/areas; keep last-known-good on ANY failure.

        Broken exception documents are skipped (logged), and the new engine
        must survive a resolve dry-run before it replaces the old one — a
        poison document therefore never kills the running plan (§3.6).
        """
        try:
            # Lazy import: the pure target computation stays testable without
            # a pymongo installation.
            from db import db
            profile = await db.opening_profile.find_one({'active': True})
            if profile is None:
                raise LookupError('kein aktives opening_profile')
            exceptions = []
            async for doc in db.exceptions.find():
                reason = validate_exception(doc)
                if reason:
                    logger.error('Ausnahme %s übersprungen: %s', doc.get('_id'), reason)
                    continue
                exceptions.append(doc)
            locations = {doc['_id']: doc.get('parent')
                         async for doc in db.locations.find()}
            areas = {doc['_id']: doc.get('members', [])
                     async for doc in db.area_sets.find()}

            engine = ResolutionEngine(
                profile, exceptions, areas, locations, tz=SCHEDULE_TZ)
            for warning in engine.config_warnings:
                logger.warning(warning)
            # Dry-run before swapping: a semantically broken plan must not
            # replace the last-known-good engine.
            today = datetime.now(ZoneInfo(SCHEDULE_TZ)).date()
            for offset in (-1, 0, 1):
                engine.resolve_all(today + timedelta(days=offset))

            self.engine = engine
            self.expected_lead_min = int(profile.get('expected_lead_min', 30))
            self.degraded = False
            logger.info('Plan geladen: %d Locations, %d Ausnahmen',
                        len(locations), len(exceptions))
        except Exception:
            # Fail-safe: never drop to an empty plan because of a read error.
            self.degraded = True
            logger.exception('Plan-Reload fehlgeschlagen — behalte last-known-good')

    async def start(self):
        while True:
            self._ticks += 1
            if self.engine is None or self._ticks % RELOAD_TICKS == 0:
                # Self-healing: retry after failed initial load, and pick up
                # changes even if an api/schedule/update message was lost.
                await self.load()
            try:
                await self.tick()
            except Exception:
                logger.exception('tick fehlgeschlagen')
            await asyncio.sleep(TICK_SECONDS)

    async def tick(self):
        now = datetime.now(timezone.utc)
        current_ids = set()
        try:
            if self.engine is not None:
                targets = self.targets(now)
                current_ids = set(targets)
                for location_id, target in targets.items():
                    await self.client.publish_json(
                        f'schedule/target/{location_id}', target, qos=1, retain=True)
                # Clear retained targets of locations that left the plan —
                # otherwise a stale 'on' would outlive its location (§3.6).
                for gone in self._published - current_ids:
                    await self.client.publish_json(
                        f'schedule/target/{gone}', None, retain=True)
                self._published = current_ids
                HEALTH_FILE.touch()
        finally:
            # The heartbeat must go out even if the target loop failed.
            await self.client.publish_json('schedule/heartbeat', {
                'published_at': now.isoformat(),
                'locations': len(current_ids),
                'degraded': self.degraded or self.engine is None,
            }, qos=1, retain=True)

    # -- pure computation ----------------------------------------------------

    def targets(self, now: datetime) -> dict:
        tz = ZoneInfo(SCHEDULE_TZ)
        today = now.astimezone(tz).date()
        result = {}
        for location_id in sorted(self.engine.locations):
            try:
                result[location_id] = self._target_for(location_id, today, now)
            except Exception:
                # One broken location must not block the others (§3.6).
                logger.exception('[%s] target-Berechnung fehlgeschlagen', location_id)
        return result

    def _target_for(self, location_id, today, now):
        windows = self._windows(location_id, today, offsets=(-1, 0, 1))
        merged = self._merge(windows)
        current = next((w for w in merged if w[0] <= now < w[1]), None)
        upcoming = next((w for w in merged if w[0] > now), None)
        if upcoming is None:
            # Look further ahead so a closed stretch (holiday block) still
            # reports the next real window within the horizon.
            for offset in range(2, LOOKAHEAD_DAYS + 1):
                ahead = self._windows(location_id, today, offsets=(offset,))
                if ahead:
                    upcoming = min((w.start, w.end, w.source) for w in ahead)
                    break
        return {
            'state': 'on' if current else 'off',
            'ready_by': current[0].isoformat() if current else (
                upcoming[0].isoformat() if upcoming else None),
            'window': self._payload(current),
            'next_window': self._payload(upcoming),
            'expected_lead_min': self.expected_lead_min,
            'lookahead_days': LOOKAHEAD_DAYS,
            'published_at': now.isoformat(),
        }

    def _windows(self, location_id, today, offsets):
        found = []
        for offset in offsets:
            resolution = self.engine.resolve(
                location_id, today + timedelta(days=offset))
            for warning in resolution.warnings:
                logger.warning('[%s] %s', location_id, warning)
            if resolution.window:
                found.append(resolution.window)
        return found

    @staticmethod
    def _merge(windows):
        """Overlapping or touching windows become one interval, so a window
        spilling past midnight reports the true operating end."""
        merged = []
        for window in sorted(windows, key=lambda w: w.start):
            if merged and window.start <= merged[-1][1]:
                start, end, source = merged[-1]
                if window.end > end:
                    end = window.end
                    source = f'{source}+{window.source}' if window.source != source else source
                merged[-1] = (start, end, source)
            else:
                merged.append((window.start, window.end, window.source))
        return merged

    @staticmethod
    def _payload(interval):
        if interval is None:
            return None
        start, end, source = interval
        return {'start': start.isoformat(), 'end': end.isoformat(), 'source': source}
