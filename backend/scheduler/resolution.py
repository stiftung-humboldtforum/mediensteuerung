"""Pure resolution engine: opening profile + exceptions -> effective window.

No I/O in this module. All datetime math is done in UTC-aware datetimes,
converted from wall-clock times via zoneinfo (KALENDER-REDESIGN.md §3.2):

  * ``close < open`` means the window ends on the following day.
  * ``close == open`` is invalid (recorded as a warning, no window) — the
    fail-safe direction for an input error is "no change", not 24h runtime.
  * DST: a non-existent local time (spring forward) is rolled forward to the
    next valid minute; an ambiguous local time (fall back) resolves to its
    first occurrence (fold=0).
  * ``extend`` operates on the result of the previous resolution stage and is
    invalid on a day without a window (recorded as a warning, not applied).

Date fields accept ``datetime.date``, ``datetime.datetime`` (as stored by
Mongo/BSON — normalized to its date) and ISO strings.

Resolution is computed per *location* (the atomic scheduling unit). Named
area sets and the location hierarchy only widen the coverage of an exception;
they never form their own resolution target. Area-set members and scope ids
that match no known location are reported via ``config_warnings`` instead of
silently creating phantom targets.

Application order per location and day — later stages override earlier ones:

  1. weekday window from the opening profile,
  2. house-wide exceptions,
  3. location exceptions, least specific first (an exception covering fewer
     locations is more specific and therefore applied later); ties are broken
     by ``created_at`` (newer wins), then by ``_id`` for total determinism.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

WEEKDAY_KEYS = ('mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun')


@dataclass(frozen=True)
class Window:
    """Effective operating window as absolute instants."""
    start: datetime
    end: datetime
    source: str  # 'profile' or exception id


@dataclass
class Resolution:
    """Result of resolving one location for one day."""
    window: Window | None
    warnings: list[str] = field(default_factory=list)


def parse_hhmm(value: str) -> time:
    hours, minutes = value.split(':')
    return time(int(hours), int(minutes))


def as_date(value) -> date:
    """Normalize date | datetime (BSON) | ISO string to a plain date."""
    if isinstance(value, datetime):  # before date: datetime IS a date subclass
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(value)


def localize(day: date, wall: time, tz: ZoneInfo) -> datetime:
    """Wall-clock time on ``day`` -> aware datetime, per the DST rules above."""
    naive = datetime.combine(day, wall)
    candidate = naive.replace(tzinfo=tz, fold=0)
    # Round-trip through UTC detects non-existent local times: they come back
    # as a different wall-clock value.
    while candidate.astimezone(timezone.utc).astimezone(tz).replace(tzinfo=None) != naive:
        naive += timedelta(minutes=1)
        candidate = naive.replace(tzinfo=tz, fold=0)
    return candidate


class ResolutionEngine:
    """Resolves effective windows from a profile and a list of exceptions.

    ``profile``    {'weekdays': {'mon': {'open': '10:30', 'close': '18:30'}|None, ...}}
    ``exceptions`` [{'_id', 'date' | 'range': {'from', 'to', 'continuous'},
                     'scope': {'kind': 'house'} | {'kind': 'areas', 'area_ids': [...]},
                     'effect': {'kind': 'hours'|'extend'|'closed', ...},
                     'created_at': <iso str|datetime>}]
    ``areas``      {area_id: iterable of location_ids} — named sets; a plain
                   location_id used in a scope always covers itself.
    ``location_parents`` {location_id: parent_location_id|None} — an exception
                   covering a location also covers all its descendants.
    """

    def __init__(self, profile, exceptions=(), areas=None,
                 location_parents=None, tz='Europe/Berlin'):
        self.profile = profile
        self.exceptions = list(exceptions)
        self.areas = {k: set(v) for k, v in (areas or {}).items()}
        self.location_parents = dict(location_parents or {})
        self.tz = ZoneInfo(tz)
        self.config_warnings: list[str] = []

        self._all_locations = set(self.location_parents)
        for set_id, members in self.areas.items():
            unknown = members - self._all_locations
            for member in sorted(unknown):
                self.config_warnings.append(
                    f"area_set '{set_id}': Mitglied '{member}' ist keine bekannte Location — ignoriert")
            self.areas[set_id] = members - unknown

    @property
    def locations(self):
        return frozenset(self._all_locations)

    # -- coverage ---------------------------------------------------------

    def _descendants(self, location_id):
        found = {location_id}
        changed = True
        while changed:
            changed = False
            for child, parent in self.location_parents.items():
                if parent in found and child not in found:
                    found.add(child)
                    changed = True
        return found

    def _expand_scope(self, exception):
        scope = exception['scope']
        if scope['kind'] == 'house':
            return None  # sentinel: covers everything
        covered = set()
        for area_id in scope['area_ids']:
            if area_id in self.areas:
                members = self.areas[area_id]
            elif area_id in self._all_locations:
                members = {area_id}
            else:
                self.config_warnings.append(
                    f"Ausnahme '{exception.get('_id')}': scope '{area_id}' ist weder "
                    f"Location noch Area-Set — ignoriert")
                continue
            for member in members:
                covered |= self._descendants(member)
        return covered

    def _matches_day(self, exception, day: date):
        when = exception.get('date')
        if when is not None:
            return as_date(when) == day
        rng = exception.get('range')
        if not rng:
            return False
        return as_date(rng['from']) <= day <= as_date(rng['to'])

    # -- window construction ----------------------------------------------

    def _build_window(self, day: date, open_s: str, close_s: str,
                      source: str, result: Resolution) -> Window | None:
        open_t, close_t = parse_hhmm(open_s), parse_hhmm(close_s)
        if open_t == close_t:
            result.warnings.append(
                f"'{source}': open == close ({open_s}) ist ungültig — kein Fenster")
            return None
        start = localize(day, open_t, self.tz)
        close_day = day if close_t > open_t else day + timedelta(days=1)
        return Window(start, localize(close_day, close_t, self.tz), source)

    def _apply(self, day: date, current: Window | None, exception, result: Resolution):
        effect = exception['effect']
        source = str(exception.get('_id', 'exception'))
        rng = exception.get('range')
        continuous = bool(rng and rng.get('continuous'))

        if effect['kind'] == 'closed':
            return None

        if effect['kind'] == 'hours':
            window = self._build_window(day, effect['open'], effect['close'],
                                        source, result)
            if window is None:
                return current  # invalid hours: fail-safe = no change
            if continuous:
                window = self._clip_continuous(day, rng, window)
            return window

        # extend: only meaningful on top of an existing window
        if current is None:
            result.warnings.append(
                f"extend-Ausnahme '{source}' ignoriert: kein Fenster am {day.isoformat()}")
            return None
        close_t = parse_hhmm(effect['close'])
        close_day = day if close_t > current.start.timetz().replace(tzinfo=None) else day + timedelta(days=1)
        # Guard against shortening: extend never ends before the current close.
        candidate = localize(close_day, close_t, self.tz)
        if candidate <= current.end:
            result.warnings.append(
                f"extend-Ausnahme '{source}' ignoriert: {effect['close']} liegt vor bestehendem Ende")
            return current
        window = Window(current.start, candidate, source)
        if continuous:
            window = self._clip_continuous(day, rng, window)
        return window

    def _clip_continuous(self, day, rng, window):
        """Continuous range: open on first day, straight through to close on
        the last day. Middle days become full-day windows."""
        first, last = as_date(rng['from']), as_date(rng['to'])
        start = window.start if day == first else localize(day, time(0, 0), self.tz)
        if day == last:
            end = window.end
        else:
            end = localize(day + timedelta(days=1), time(0, 0), self.tz)
        return Window(start, end, window.source)

    # -- public API ---------------------------------------------------------

    def resolve(self, location_id, day: date) -> Resolution:
        result = Resolution(window=None)

        weekday = self.profile['weekdays'].get(WEEKDAY_KEYS[day.weekday()])
        if weekday:
            result.window = self._build_window(
                day, weekday['open'], weekday['close'], 'profile', result)

        applicable = []
        for exception in self.exceptions:
            if not self._matches_day(exception, day):
                continue
            covered = self._expand_scope(exception)
            if covered is not None and location_id not in covered:
                continue
            # Sort key: house (tier 0) before locations (tier 1); within the
            # location tier, wider coverage first (= weaker, overridden later);
            # newer created_at last (= wins on ties); _id as final tiebreaker
            # for total determinism.
            tier = 0 if covered is None else 1
            size = 0 if covered is None else len(covered)
            applicable.append(
                ((tier, -size, self._created_key(exception),
                  str(exception.get('_id', ''))), exception))

        for _, exception in sorted(applicable, key=lambda pair: pair[0]):
            result.window = self._apply(day, result.window, exception, result)

        return result

    def resolve_all(self, day: date) -> dict:
        return {loc: self.resolve(loc, day) for loc in sorted(self._all_locations)}

    @staticmethod
    def _created_key(exception) -> datetime:
        """created_at as aware-UTC datetime; naive values count as UTC,
        missing/unparseable values sort first (= lose every tie)."""
        value = exception.get('created_at')
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        if isinstance(value, str):
            try:
                parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
                return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
            except ValueError:
                pass
        return datetime.min.replace(tzinfo=timezone.utc)
