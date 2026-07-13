"""Truth table for the resolution engine (KALENDER-REDESIGN.md §3.2).

Every semantic rule of the plan has at least one case here; the P1 milestone
requires this suite to stay green.
"""

import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from resolution import ResolutionEngine, localize, parse_hhmm  # noqa: E402

TZ = ZoneInfo('Europe/Berlin')

PROFILE = {
    'weekdays': {
        'mon': {'open': '10:30', 'close': '18:30'},
        'tue': None,  # Schließtag
        'wed': {'open': '10:30', 'close': '18:30'},
        'thu': {'open': '10:30', 'close': '18:30'},
        'fri': {'open': '10:30', 'close': '18:30'},
        'sat': {'open': '10:30', 'close': '18:30'},
        'sun': {'open': '10:30', 'close': '18:30'},
    },
}

# 2026-07-13 is a Monday, 2026-07-14 a Tuesday.
MON = date(2026, 7, 13)
TUE = date(2026, 7, 14)
WED = date(2026, 7, 15)

# Location hierarchy: floor EG with rooms saal/foyer/garderobe below it.
PARENTS = {'eg': None, 'saal': 'eg', 'foyer': 'eg', 'garderobe': 'eg'}
AREAS = {'abendbereich': {'saal', 'foyer'}}


def engine(exceptions=(), areas=AREAS, parents=PARENTS):
    return ResolutionEngine(PROFILE, exceptions, areas, parents)


def wall(day, hhmm, plus_days=0):
    return localize(day + timedelta(days=plus_days), parse_hhmm(hhmm), TZ)


def exc(_id, *, day=None, rng=None, scope=None, effect=None, created='2026-01-01T00:00:00'):
    record = {'_id': _id, 'scope': scope or {'kind': 'house'},
              'effect': effect, 'created_at': created}
    if day is not None:
        record['date'] = day
    if rng is not None:
        record['range'] = rng
    return record


# -- Profil ----------------------------------------------------------------

def test_plain_weekday_window():
    res = engine().resolve('saal', MON)
    assert res.window.start == wall(MON, '10:30')
    assert res.window.end == wall(MON, '18:30')
    assert res.window.source == 'profile'


def test_closed_weekday_has_no_window():
    assert engine().resolve('saal', TUE).window is None


# -- Haus-Ausnahmen ----------------------------------------------------------

def test_house_closed_overrides_profile():
    res = engine([exc('x', day=MON, effect={'kind': 'closed'})]).resolve('saal', MON)
    assert res.window is None


def test_house_hours_overrides_profile():
    res = engine([exc('x', day=MON, effect={'kind': 'hours', 'open': '09:00', 'close': '22:00'})]).resolve('saal', MON)
    assert res.window.start == wall(MON, '09:00')
    assert res.window.end == wall(MON, '22:00')


def test_house_hours_creates_window_on_closed_day():
    res = engine([exc('x', day=TUE, effect={'kind': 'hours', 'open': '12:00', 'close': '20:00'})]).resolve('saal', TUE)
    assert res.window.start == wall(TUE, '12:00')


# -- Bereichs-Ausnahmen: Scope, Spezifität, Hierarchie -----------------------

def test_area_exception_only_hits_covered_locations():
    rules = [exc('x', day=MON, scope={'kind': 'areas', 'area_ids': ['abendbereich']},
                 effect={'kind': 'extend', 'close': '22:00'})]
    e = engine(rules)
    assert e.resolve('saal', MON).window.end == wall(MON, '22:00')
    assert e.resolve('garderobe', MON).window.end == wall(MON, '18:30')


def test_area_beats_house_exception():
    rules = [
        exc('house', day=MON, effect={'kind': 'hours', 'open': '10:30', 'close': '20:00'}),
        exc('area', day=MON, scope={'kind': 'areas', 'area_ids': ['saal']},
            effect={'kind': 'hours', 'open': '10:30', 'close': '23:00'}),
    ]
    e = engine(rules)
    assert e.resolve('saal', MON).window.end == wall(MON, '23:00')
    assert e.resolve('foyer', MON).window.end == wall(MON, '20:00')


def test_narrower_scope_wins_on_partial_overlap():
    # Ausnahme 1 deckt {saal, foyer}, Ausnahme 2 nur {foyer}: fürs Foyer
    # gewinnt die engere Regel, für den Saal gilt weiter Ausnahme 1.
    rules = [
        exc('wide', day=MON, scope={'kind': 'areas', 'area_ids': ['abendbereich']},
            effect={'kind': 'hours', 'open': '10:30', 'close': '21:00'}),
        exc('narrow', day=MON, scope={'kind': 'areas', 'area_ids': ['foyer']},
            effect={'kind': 'hours', 'open': '10:30', 'close': '23:30'}),
    ]
    e = engine(rules)
    assert e.resolve('foyer', MON).window.end == wall(MON, '23:30')
    assert e.resolve('saal', MON).window.end == wall(MON, '21:00')


def test_equal_specificity_newer_created_wins():
    rules = [
        exc('older', day=MON, scope={'kind': 'areas', 'area_ids': ['saal']},
            effect={'kind': 'hours', 'open': '10:30', 'close': '20:00'},
            created='2026-01-01T00:00:00'),
        exc('newer', day=MON, scope={'kind': 'areas', 'area_ids': ['saal']},
            effect={'kind': 'hours', 'open': '10:30', 'close': '21:00'},
            created='2026-06-01T00:00:00'),
    ]
    assert engine(rules).resolve('saal', MON).window.end == wall(MON, '21:00')


def test_parent_location_exception_covers_children():
    rules = [exc('x', day=MON, scope={'kind': 'areas', 'area_ids': ['eg']},
                 effect={'kind': 'closed'})]
    e = engine(rules)
    for loc in ('saal', 'foyer', 'garderobe', 'eg'):
        assert e.resolve(loc, MON).window is None, loc


# -- extend -------------------------------------------------------------------

def test_extend_lengthens_profile_window():
    rules = [exc('x', day=MON, effect={'kind': 'extend', 'close': '22:00'})]
    res = engine(rules).resolve('saal', MON)
    assert res.window.start == wall(MON, '10:30')
    assert res.window.end == wall(MON, '22:00')


def test_extend_applies_on_top_of_previous_stage():
    # Haus setzt 09:00–20:00, Bereichs-extend hebt nur das Ende auf 22:00 —
    # Basis ist das Ergebnis der Haus-Stufe, nicht das Profil.
    rules = [
        exc('house', day=MON, effect={'kind': 'hours', 'open': '09:00', 'close': '20:00'}),
        exc('area', day=MON, scope={'kind': 'areas', 'area_ids': ['saal']},
            effect={'kind': 'extend', 'close': '22:00'}),
    ]
    res = engine(rules).resolve('saal', MON)
    assert res.window.start == wall(MON, '09:00')
    assert res.window.end == wall(MON, '22:00')


def test_extend_on_closed_day_is_ignored_with_warning():
    rules = [exc('x', day=TUE, effect={'kind': 'extend', 'close': '22:00'})]
    res = engine(rules).resolve('saal', TUE)
    assert res.window is None
    assert any('extend' in w for w in res.warnings)


def test_extend_cannot_shorten():
    rules = [exc('x', day=MON, effect={'kind': 'extend', 'close': '17:00'})]
    res = engine(rules).resolve('saal', MON)
    assert res.window.end == wall(MON, '18:30')
    assert any('ignoriert' in w for w in res.warnings)


def test_extend_past_midnight():
    rules = [exc('x', day=MON, effect={'kind': 'extend', 'close': '01:00'})]
    res = engine(rules).resolve('saal', MON)
    assert res.window.end == wall(MON, '01:00', plus_days=1)


# -- Fenster über Mitternacht -------------------------------------------------

def test_hours_over_midnight_end_next_day():
    rules = [exc('x', day=MON, effect={'kind': 'hours', 'open': '18:00', 'close': '01:00'})]
    res = engine(rules).resolve('saal', MON)
    assert res.window.start == wall(MON, '18:00')
    assert res.window.end == wall(MON, '01:00', plus_days=1)


# -- Ranges -------------------------------------------------------------------

def test_range_non_continuous_applies_per_day():
    rules = [exc('x', rng={'from': MON, 'to': WED, 'continuous': False},
                 effect={'kind': 'hours', 'open': '08:00', 'close': '20:00'})]
    e = engine(rules)
    for day in (MON, TUE, WED):
        res = e.resolve('saal', day)
        assert res.window.start == wall(day, '08:00'), day
        assert res.window.end == wall(day, '20:00'), day


def test_range_continuous_runs_through_nights():
    rules = [exc('x', rng={'from': MON, 'to': WED, 'continuous': True},
                 effect={'kind': 'hours', 'open': '08:00', 'close': '20:00'})]
    e = engine(rules)
    first = e.resolve('saal', MON).window
    middle = e.resolve('saal', TUE).window
    last = e.resolve('saal', WED).window
    assert first.start == wall(MON, '08:00')
    assert first.end == wall(TUE, '00:00')
    assert middle.start == wall(TUE, '00:00')
    assert middle.end == wall(WED, '00:00')
    assert last.start == wall(WED, '00:00')
    assert last.end == wall(WED, '20:00')


# -- DST ----------------------------------------------------------------------

def test_dst_spring_forward_rolls_to_next_valid_time():
    # 2026-03-29: 02:00 -> 03:00, 02:30 existiert nicht -> 03:00.
    day = date(2026, 3, 29)
    resolved = localize(day, parse_hhmm('02:30'), TZ)
    assert resolved.hour == 3 and resolved.minute == 0
    assert resolved.utcoffset() == timedelta(hours=2)


def test_dst_fall_back_uses_first_occurrence():
    # 2026-10-25: 03:00 -> 02:00, 02:30 doppelt -> erstes Vorkommen (CEST, +02:00).
    day = date(2026, 10, 25)
    resolved = localize(day, parse_hhmm('02:30'), TZ)
    assert resolved.utcoffset() == timedelta(hours=2)


def test_window_spanning_spring_forward_keeps_absolute_order():
    # Fenster 18:00–01:00 in der Nacht der Frühjahrs-Umstellung (01:00 existiert).
    day = date(2026, 3, 28)
    rules = [exc('x', day=day, effect={'kind': 'hours', 'open': '18:00', 'close': '02:30'})]
    res = engine(rules).resolve('saal', day)
    assert res.window.end > res.window.start
    # 02:30 am 29.03. existiert nicht -> 03:00 CEST.
    assert res.window.end == datetime(2026, 3, 29, 3, 0, tzinfo=TZ)


# -- resolve_all ----------------------------------------------------------------

def test_resolve_all_covers_every_known_location():
    result = engine().resolve_all(MON)
    assert set(result) == {'eg', 'saal', 'foyer', 'garderobe'}
    assert all(r.window is not None for r in result.values())
