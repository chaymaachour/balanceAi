from datetime import datetime, timedelta

import notifications
import schedule as sch
from conftest import BASE_SETTINGS
from test_revision import ENTRIES, exam
from test_schedule import MON


def ctx(**over):
    c = {"settings": dict(BASE_SETTINGS), "entries": ENTRIES, "exceptions": [], "exams": [], "sessions": []}
    c.update(over)
    return c


def kinds(items):
    return {i["kind"] for i in items}


def test_day_end_and_exam_encouragement():
    items = notifications.compute_due(ctx(exams=[exam("Maths", 3)]), MON)
    day_end = [i for i in items if i["kind"] == "day_end"][0]
    assert day_end["at"] == sch.to_min("17:15")
    assert "Maths" in day_end["body"]  # exam-aware encouragement
    assert "empty_plan" in kinds(items)  # no plan yet -> suggest creating one


def test_session_reminders_and_finished_exam_stops_reminders():
    s = {"id": "s1", "exam_id": "Maths", "date": MON.isoformat(), "start": "18:00", "end": "18:45", "minutes": 45, "status": "planned"}
    items = notifications.compute_due(ctx(exams=[exam("Maths", 3)], sessions=[s]), MON)
    sess = [i for i in items if i["kind"] == "session"][0]
    assert sess["at"] == sch.to_min("17:50")
    assert "session_check" in kinds(items) and "empty_plan" not in kinds(items)
    done_exam = {**exam("Maths", 3), "status": "done"}
    items = notifications.compute_due(ctx(exams=[done_exam], sessions=[s]), MON)
    assert not kinds(items) & {"session", "session_check", "empty_plan"}


def test_quiet_hours_and_disabled():
    late = {"id": "s2", "exam_id": "Maths", "date": MON.isoformat(), "start": "22:30", "end": "23:00", "minutes": 30, "status": "planned"}
    items = notifications.compute_due(ctx(exams=[exam("Maths", 3)], sessions=[late]), MON)
    assert "session" not in kinds(items)
    c = ctx(exams=[exam("Maths", 3)])
    c["settings"]["notifications_enabled"] = False
    assert notifications.compute_due(c, MON) == []


def test_exam_day_message_before_exam():
    items = notifications.compute_due(ctx(exams=[exam("Maths", 0)]), MON)
    e = [i for i in items if i["kind"] == "exam_day"][0]
    assert e["at"] <= sch.to_min("07:30")


def test_languages():
    for lang, word in (("en", "day"), ("tn", "نهارك")):
        c = ctx()
        c["settings"]["notif_lang"] = lang
        assert word in [i for i in notifications.compute_due(c, MON) if i["kind"] == "day_end"][0]["title"].lower()
