from datetime import date

import schedule as sch
from conftest import BASE_SETTINGS

MON = date(2026, 10, 19)  # a Monday


def entry(i, day, start, end, kind="course", recurring=True, d=None):
    return {"id": i, "kind": kind, "title": i, "day": day, "start": start, "end": end,
            "recurring": recurring, "date": d, "location": ""}


def test_templates_profiles():
    lycee = sch.template_entries("lycee")
    uni = sch.template_entries("universite", ["Algo", "Maths"])
    assert lycee and uni and sch.template_entries("autre") == []
    assert all(e["kind"] == "course" and e["recurring"] for e in lycee)
    assert {e["title"].split(" — ")[-1] for e in uni} <= {"Algo", "Maths"}
    for tpl in (lycee, uni):  # templates must not contain conflicts
        withid = [{**e, "id": str(i)} for i, e in enumerate(tpl)]
        assert all(not sch.find_conflicts(withid, e, ignore_id=e["id"]) for e in withid)


def test_conflict_detection():
    entries = [entry("a", 0, "08:00", "10:00")]
    assert sch.find_conflicts(entries, entry("b", 0, "09:00", "11:00"))
    assert not sch.find_conflicts(entries, entry("c", 0, "10:00", "11:00"))  # touching is fine
    assert not sch.find_conflicts(entries, entry("d", 1, "09:00", "11:00"))
    one_off = entry("e", 0, "09:30", "10:30", kind="club", recurring=False, d=MON.isoformat())
    assert sch.find_conflicts(entries, one_off)


def test_cancelled_moved_and_day_off():
    entries = [entry("a", 0, "08:00", "10:00"), entry("b", 0, "14:00", "16:00"), entry("club", 0, "17:00", "18:00", "club")]
    exc = [{"id": "x1", "date": MON.isoformat(), "entry_id": "a", "kind": "cancel"},
           {"id": "x2", "date": MON.isoformat(), "entry_id": "b", "kind": "move", "start": "15:00", "end": "17:00"}]
    items = {i["id"]: i for i in sch.effective_day(entries, exc, MON)}
    assert items["a"]["cancelled"] and items["b"]["moved"] and items["b"]["start"] == "15:00"
    off = sch.effective_day(entries, [{"id": "x", "date": MON.isoformat(), "kind": "day_off", "entry_id": None}], MON)
    assert all(i["cancelled"] for i in off if i["kind"] == "course")
    assert not [i for i in off if i["kind"] == "club"][0]["cancelled"]
    assert sch.effective_day(entries, [], date(2026, 10, 20)) == []  # Tuesday: no classes


def test_day_end_reminder_respects_commute_rest_and_preferences():
    s = dict(BASE_SETTINGS)
    items = sch.effective_day([entry("a", 0, "08:00", "16:00")], [], MON)
    r = sch.day_end_reminder(s, items, MON)
    assert r["at"] == sch.to_min("16:00") + 30 + 45  # end + commute + rest -> 17:15
    s["home_time"] = "17:30"
    assert sch.day_end_reminder(s, items, MON)["at"] == sch.to_min("17:30") + 45
    s["checkin_time"] = "19:00"
    assert sch.day_end_reminder(s, items, MON)["at"] == sch.to_min("19:00")


def test_day_end_reminder_days_quiet_hours_and_no_classes():
    s = dict(BASE_SETTINGS, reminder_days=[1, 2])
    items = sch.effective_day([entry("a", 0, "08:00", "16:00")], [], MON)
    assert sch.day_end_reminder(s, items, MON)["reason"] == "day_not_allowed"
    s = dict(BASE_SETTINGS, quiet_start="17:00", quiet_end="07:00")
    assert sch.day_end_reminder(s, items, MON)["reason"] == "quiet_hours"
    s = dict(BASE_SETTINGS)
    assert sch.day_end_reminder(s, [], MON)["reason"] == "no_classes"
    s["wellness_reminder"], s["checkin_time"] = True, "20:00"
    assert sch.day_end_reminder(s, [], MON)["at"] == 20 * 60
    s["notifications_enabled"] = False
    assert sch.day_end_reminder(s, items, MON)["at"] is None


def test_quiet_hours_over_midnight():
    s = {"quiet_start": "22:00", "quiet_end": "07:30"}
    assert sch.in_quiet_hours(23 * 60, s) and sch.in_quiet_hours(6 * 60, s)
    assert not sch.in_quiet_hours(12 * 60, s)


def test_free_slots_exclude_classes_travel_rest():
    items = sch.effective_day([entry("a", 0, "08:00", "12:00"), entry("b", 0, "14:00", "16:00")], [], MON)
    slots = sch.free_slots(BASE_SETTINGS, items)
    # one outing 08:00-16:00 (short lunch gap), home 16:30, rest until 17:15
    assert slots == [(sch.to_min("17:15"), sch.to_min("21:30"))]
