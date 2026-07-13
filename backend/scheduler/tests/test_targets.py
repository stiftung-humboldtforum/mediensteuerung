"""Target computation of the scheduler service (pure part, no I/O).

`Scheduler.targets(now)` must yield correct state/ready_by/window payloads,
including windows that spill past midnight (KALENDER-REDESIGN.md §3.3/§3.6).
"""

import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from resolution import ResolutionEngine  # noqa: E402
from scheduler_service import Scheduler  # noqa: E402

TZ = ZoneInfo('Europe/Berlin')

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


def scheduler(exceptions=()):
    s = Scheduler(client=None)
    s.engine = ResolutionEngine(PROFILE, exceptions, {}, {'saal': None})
    return s


def at(y, m, d, hh, mm):
    return datetime(y, m, d, hh, mm, tzinfo=TZ)


def test_state_on_inside_window():
    target = scheduler().targets(at(2026, 7, 13, 12, 0))['saal']  # Montag
    assert target['state'] == 'on'
    assert target['window']['source'] == 'profile'
    assert target['ready_by'] == at(2026, 7, 13, 10, 30).isoformat()


def test_state_off_before_open_with_upcoming_window():
    target = scheduler().targets(at(2026, 7, 13, 8, 0))['saal']
    assert target['state'] == 'off'
    assert target['window'] is None
    # ready_by zeigt aufs kommende Fenster, damit der Orchestrator planen kann.
    assert target['ready_by'] == at(2026, 7, 13, 10, 30).isoformat()
    assert target['next_window']['start'] == at(2026, 7, 13, 10, 30).isoformat()


def test_state_off_on_closed_day_points_to_next_day():
    target = scheduler().targets(at(2026, 7, 14, 12, 0))['saal']  # Dienstag zu
    assert target['state'] == 'off'
    assert target['window'] is None
    assert target['next_window']['start'] == at(2026, 7, 15, 10, 30).isoformat()


def test_window_spilling_past_midnight_stays_on():
    # Abendveranstaltung Montag 18:00–01:00: um 00:30 (Dienstag!) noch an,
    # obwohl Dienstag Schließtag ist.
    rules = [{'_id': 'abend', 'date': '2026-07-13',
              'scope': {'kind': 'house'},
              'effect': {'kind': 'hours', 'open': '18:00', 'close': '01:00'},
              'created_at': '2026-01-01T00:00:00'}]
    target = scheduler(rules).targets(at(2026, 7, 14, 0, 30))['saal']
    assert target['state'] == 'on'
    assert target['window']['end'] == at(2026, 7, 14, 1, 0).isoformat()


def test_boundary_exactly_at_close_is_off():
    target = scheduler().targets(at(2026, 7, 13, 18, 30))['saal']
    assert target['state'] == 'off'
