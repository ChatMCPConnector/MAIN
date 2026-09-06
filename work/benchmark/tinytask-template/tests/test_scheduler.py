"""Tests für den TinyTask-Scheduler.

Startzustand (absichtlich kaputt): 4 failed / 3 passed.
Die Intentionen dieser Tests sind legitim — NICHT umbauen, um sie grün zu bekommen.
"""
import os
import sys
import threading
from datetime import datetime

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    import scheduler
    monkeypatch.setattr(scheduler, "DB_PATH", str(tmp_path / "t.db"))
    monkeypatch.setattr(scheduler, "_local", threading.local())
    scheduler.init_db()
    scheduler.seed()
    yield


def test_daily_recurrence_next_day():
    from scheduler import next_occurrence
    after = datetime(2026, 1, 5)
    assert next_occurrence("daily", after) == datetime(2026, 1, 6)


def test_weekly_recurrence_same_weekday_next_week():
    from scheduler import next_occurrence
    after = datetime(2026, 1, 5)  # Montag
    assert next_occurrence("weekly:mon", after) == datetime(2026, 1, 12)


def test_weekly_recurrence_from_sunday_before():
    from scheduler import next_occurrence
    after = datetime(2026, 1, 4)  # Sonntag
    assert next_occurrence("weekly:mon", after) == datetime(2026, 1, 5)  # nächster Montag


def test_interval_recurrence_exact():
    from scheduler import next_occurrence
    after = datetime(2026, 1, 5)
    assert next_occurrence("every:3d", after) == datetime(2026, 1, 8)


def test_recurrence_unknown_rule_rejected():
    from scheduler import next_occurrence
    with pytest.raises(ValueError):
        next_occurrence("quarterly:mar", datetime(2026, 1, 5))


def test_complete_recurring_creates_next_instance():
    import scheduler
    before = scheduler.get_conn().execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
    scheduler.complete_task(2)  # "Backup prüfen" (daily), due 2026-01-05T09:00
    after = scheduler.get_conn().execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
    assert after == before + 1
    new = scheduler.get_conn().execute(
        "SELECT title, due, done FROM tasks WHERE id = (SELECT MAX(id) FROM tasks)"
    ).fetchone()
    assert new[0] == "Backup prüfen"
    assert new[1] == "2026-01-06T09:00:00"  # due + 1 Tag (nicht now + 1 Tag!)
    assert new[2] == 0  # neue Instanz ist offen


def test_overdue_returns_only_past_open():
    import scheduler
    overdue = scheduler.overdue_tasks(now=datetime(2026, 1, 7, 12, 0, 0))
    titles = [t[1] for t in overdue]
    assert "Wocherückblick schreiben" in titles   # due 05.01 -> overdue
    assert "Backup prüfen" in titles              # due 05.01 -> overdue
    assert "Bericht an Partner" not in titles     # due 08.01 -> noch nicht fällig
    assert all(t[5] == 0 for t in overdue)        # erledigte nie
