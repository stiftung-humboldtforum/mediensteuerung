"""Regression tests for the adversarial-review findings (2026-07-13).

Each test pins the fix of one reviewed defect; keep them green.
"""

import asyncio
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from resolution import ResolutionEngine, localize, parse_hhmm  # noqa: E402
from scheduler_service import Scheduler, validate_exception  # noqa: E402

TZ = ZoneInfo('Europe/Berlin')
MON = date(2026, 7, 13)
TUE = date(2026, 7, 14)
WED = date(2026, 7, 15)

PROFILE = {
    'weekdays': {
        'mon': {'open': '10:30', 'close': '18:30'},
        'tue': None,
        'wed': {'open': '10:30', 'close': '18:30'},
        'thu': {'open': '10:30', 'close': '18:30'},
        'fri': {'open': '10:30', 'close': '18:30'},
        'sat': {'open': '10:30', 'close': '18:30'},
        'sun': {'open': '10:30', 'close': '18:30'},
    },
}


def engine(exceptions=(), areas=None, parents=None):
    return ResolutionEngine(PROFILE, exceptions,
                            areas if areas is not None else {},
                            parents if parents is not None else {'saal': None})


def wall(day, hhmm, plus_days=0):
    return localize(day + timedelta(days=plus_days), parse_hhmm(hhmm), TZ)


# -- Finding 1: BSON-datetime als Datumstyp ----------------------------------

def test_bson_datetime_single_date_matches():
    rules = [{'_id': 'x', 'date': datetime(2026, 7, 13),  # BSON liefert datetime
              'scope': {'kind': 'house'}, 'effect': {'kind': 'closed'},
              'created_at': datetime(2026, 1, 1)}]
    assert engine(rules).resolve('saal', MON).window is None


def test_bson_datetime_range_does_not_crash_and_matches():
    rules = [{'_id': 'x',
              'range': {'from': datetime(2026, 7, 13), 'to': datetime(2026, 7, 15),
                        'continuous': False},
              'scope': {'kind': 'house'},
              'effect': {'kind': 'hours', 'open': '08:00', 'close': '20:00'},
              'created_at': datetime(2026, 1, 1)}]
    res = engine(rules).resolve('saal', TUE)
    assert res.window.start == wall(TUE, '08:00')


# -- Finding 2: Poison-Dokument (Validierung) ---------------------------------

def test_validate_exception_rejects_broken_documents():
    assert validate_exception({'scope': {'kind': 'house'},
                               'effect': {'kind': 'closed'}}) is not None  # kein Datum
    assert validate_exception({'date': MON, 'scope': {'kind': 'nope'},
                               'effect': {'kind': 'closed'}}) is not None
    assert validate_exception({'date': MON, 'scope': {'kind': 'house'},
                               'effect': {'kind': 'hours', 'open': 'zehn'}}) is not None
    assert validate_exception({'date': MON, 'scope': {'kind': 'house'},
                               'effect': {'kind': 'closed'}}) is None


def test_exception_without_date_and_range_matches_nothing():
    rules = [{'_id': 'x', 'scope': {'kind': 'house'},
              'effect': {'kind': 'closed'}, 'created_at': '2026-01-01T00:00:00'}]
    # Engine selbst crasht nicht und wendet die Regel nie an.
    assert engine(rules).resolve('saal', MON).window is not None


# -- Finding 5/edge-3: Fenster-Merge über Mitternacht -------------------------

def make_scheduler(exceptions=()):
    s = Scheduler(client=None)
    s.engine = ResolutionEngine(PROFILE, exceptions, {}, {'saal': None})
    return s


def test_overlapping_windows_merge_to_true_end():
    # Mo-Abendfenster bis 03:00 + Di-Frühöffnung ab 02:00: um 02:30 muss das
    # publizierte Ende Di 18:00 sein, nicht Di 03:00.
    rules = [
        {'_id': 'abend', 'date': '2026-07-13', 'scope': {'kind': 'house'},
         'effect': {'kind': 'hours', 'open': '18:00', 'close': '03:00'},
         'created_at': '2026-01-01T00:00:00'},
        {'_id': 'frueh', 'date': '2026-07-14', 'scope': {'kind': 'house'},
         'effect': {'kind': 'hours', 'open': '02:00', 'close': '18:00'},
         'created_at': '2026-01-01T00:00:00'},
    ]
    target = make_scheduler(rules).targets(
        datetime(2026, 7, 14, 2, 30, tzinfo=TZ))['saal']
    assert target['state'] == 'on'
    assert target['window']['end'] == datetime(2026, 7, 14, 18, 0, tzinfo=TZ).isoformat()


def test_touching_continuous_windows_merge():
    rules = [{'_id': 'messe',
              'range': {'from': '2026-07-13', 'to': '2026-07-15', 'continuous': True},
              'scope': {'kind': 'house'},
              'effect': {'kind': 'hours', 'open': '08:00', 'close': '20:00'},
              'created_at': '2026-01-01T00:00:00'}]
    # Mitten in der Nacht Di->Mi: durchgehend an, Ende erst Mi 20:00.
    target = make_scheduler(rules).targets(
        datetime(2026, 7, 15, 1, 0, tzinfo=TZ))['saal']
    assert target['state'] == 'on'
    assert target['window']['end'] == datetime(2026, 7, 15, 20, 0, tzinfo=TZ).isoformat()


# -- Finding edge-6: continuous + extend --------------------------------------

def test_continuous_extend_runs_through_nights():
    rules = [{'_id': 'aufbau',
              'range': {'from': '2026-07-13', 'to': '2026-07-15', 'continuous': True},
              'scope': {'kind': 'house'},
              'effect': {'kind': 'extend', 'close': '22:00'},
              'created_at': '2026-01-01T00:00:00'}]
    e = engine(rules)
    middle = e.resolve('saal', TUE)
    # Dienstag ist Schließtag: extend hat dort keine Basis — dokumentierte
    # Warnung; Mo und Mi laufen bis Mitternacht durch bzw. ab Mitternacht.
    first = e.resolve('saal', MON).window
    last = e.resolve('saal', WED).window
    assert first.start == wall(MON, '10:30')
    assert first.end == wall(TUE, '00:00')
    assert last.start == wall(WED, '00:00')
    assert last.end == wall(WED, '22:00')
    assert middle.window is None and any('extend' in w for w in middle.warnings)


# -- Finding edge-7: created_at-Formate gemischt ------------------------------

def test_created_at_mixed_formats_compare_chronologically():
    rules = [
        {'_id': 'aelter_utc', 'date': '2026-07-13',
         'scope': {'kind': 'areas', 'area_ids': ['saal']},
         'effect': {'kind': 'hours', 'open': '10:30', 'close': '22:00'},
         'created_at': '2026-06-01T13:00:00+02:00'},   # = 11:00 UTC
        {'_id': 'neuer_naiv', 'date': '2026-07-13',
         'scope': {'kind': 'areas', 'area_ids': ['saal']},
         'effect': {'kind': 'hours', 'open': '10:30', 'close': '20:00'},
         'created_at': datetime(2026, 6, 1, 12, 0)},   # naiv = 12:00 UTC (neuer!)
    ]
    res = engine(rules).resolve('saal', MON)
    assert res.window.end == wall(MON, '20:00')  # der chronologisch Neuere gewinnt


def test_identical_keys_fall_back_to_id_deterministically():
    def rule(_id, close):
        return {'_id': _id, 'date': '2026-07-13',
                'scope': {'kind': 'areas', 'area_ids': ['saal']},
                'effect': {'kind': 'hours', 'open': '10:30', 'close': close},
                'created_at': '2026-01-01T00:00:00'}
    a, b = rule('aaa', '20:00'), rule('zzz', '21:00')
    assert engine([a, b]).resolve('saal', MON).window.end == wall(MON, '21:00')
    assert engine([b, a]).resolve('saal', MON).window.end == wall(MON, '21:00')


# -- Finding 8/edge-8: open == close -------------------------------------------

def test_open_equals_close_yields_no_window_with_warning():
    rules = [{'_id': 'tippfehler', 'date': '2026-07-13', 'scope': {'kind': 'house'},
              'effect': {'kind': 'hours', 'open': '10:00', 'close': '10:00'},
              'created_at': '2026-01-01T00:00:00'}]
    res = engine(rules).resolve('saal', MON)
    # Fail-safe: keine Änderung — Profil-Fenster bleibt, Warnung dokumentiert.
    assert res.window.source == 'profile'
    assert any('open == close' in w for w in res.warnings)


# -- Finding edge-10: unbekannte Bereichs-IDs ----------------------------------

def test_unknown_area_member_and_scope_id_warn_instead_of_phantom():
    e = ResolutionEngine(
        PROFILE,
        [{'_id': 'x', 'date': '2026-07-13',
          'scope': {'kind': 'areas', 'area_ids': ['tippfehler']},
          'effect': {'kind': 'closed'}, 'created_at': '2026-01-01T00:00:00'}],
        areas={'set1': {'saal', 'geist'}},
        location_parents={'saal': None})
    assert 'geist' not in e.locations          # kein Phantom-Target
    assert any('geist' in w for w in e.config_warnings)
    res = e.resolve('saal', MON)
    assert res.window is not None              # unbekannter Scope trifft niemanden
    assert any('tippfehler' in w for w in e.config_warnings)


# -- Finding 6: Horizont --------------------------------------------------------

def test_next_window_found_beyond_adjacent_days():
    # Montag 19:00, Dienstag Schließtag: next_window muss Mittwoch liefern.
    target = make_scheduler().targets(datetime(2026, 7, 13, 19, 0, tzinfo=TZ))['saal']
    assert target['state'] == 'off'
    assert target['next_window']['start'] == datetime(2026, 7, 15, 10, 30, tzinfo=TZ).isoformat()


# -- Findings tick(): Orphan-Cleanup + Heartbeat-Garantie -----------------------

class FakeClient:
    def __init__(self):
        self.published = []

    async def publish_json(self, topic, payload, **kwargs):
        self.published.append((topic, payload, kwargs))


def test_tick_clears_retained_targets_of_removed_locations():
    client = FakeClient()
    s = Scheduler(client=client)
    s.engine = ResolutionEngine(PROFILE, (), {}, {'a': None, 'b': None})
    asyncio.run(s.tick())
    s.engine = ResolutionEngine(PROFILE, (), {}, {'a': None})
    asyncio.run(s.tick())
    cleared = [(t, p) for t, p, k in client.published
               if t == 'schedule/target/b' and p is None and k.get('retain')]
    assert cleared, 'entferntes Location-Target muss retained geleert werden'


def test_heartbeat_survives_target_failure():
    client = FakeClient()
    s = Scheduler(client=client)
    s.engine = None  # kein Plan geladen
    asyncio.run(s.tick())
    beats = [p for t, p, _ in client.published if t == 'schedule/heartbeat']
    assert beats and beats[0]['degraded'] is True
