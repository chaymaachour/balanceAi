from datetime import date, timedelta

import revision
import schedule as sch
from conftest import BASE_SETTINGS
from test_schedule import MON, entry

ENTRIES = [entry(f"c{d}", d, "08:00", "16:00") for d in range(5)] + [entry("club", 2, "17:00", "18:30", "club")]


def exam(i, days, priority="medium", prep=20, difficult="", chapters="Ch1, Ch2, Ch3"):
    return {"id": i, "subject": i, "title": "", "chapters": chapters, "difficult": difficult,
            "date": (MON + timedelta(days=days)).isoformat(), "time": "08:00", "priority": priority,
            "preparation": prep, "minutes_per_day": 0, "status": "upcoming"}


def assert_no_overlaps(sessions, entries, exceptions=()):
    for s in sessions:
        d = date.fromisoformat(s["date"])
        a0, a1 = sch.to_min(s["start"]), sch.to_min(s["end"])
        assert sch.to_min(BASE_SETTINGS["study_start"]) <= a0 and a1 <= sch.to_min(BASE_SETTINGS["study_end"])
        for i in sch.effective_day(entries, list(exceptions), d):
            if not i["cancelled"]:
                assert not sch.overlaps(a0, a1, sch.to_min(i["start"]), sch.to_min(i["end"])), (s, i)
        for o in sessions:
            if o is not s and o["date"] == s["date"]:
                assert not sch.overlaps(a0, a1, sch.to_min(o["start"]), sch.to_min(o["end"]))


def test_plan_uses_only_free_slots_and_respects_daily_cap():
    res = revision.plan([exam("Maths", 10, "high", difficult="Intégrales")], ENTRIES, [], BASE_SETTINGS, [], MON)
    assert res["sessions"]
    assert_no_overlaps(res["sessions"], ENTRIES)
    by_day = {}
    for s in res["sessions"]:
        by_day[s["date"]] = by_day.get(s["date"], 0) + s["minutes"]
        assert s["date"] < exam("Maths", 10)["date"]
    assert max(by_day.values()) <= BASE_SETTINGS["daily_study_minutes"]
    assert res["sessions"][0]["focus"] == "Intégrales"  # difficult chapters first


def test_plan_is_personalised():
    a = revision.plan([exam("Maths", 6, "high", prep=10)], ENTRIES, [], BASE_SETTINGS, [], MON)
    b = revision.plan([exam("Maths", 6, "low", prep=80)], ENTRIES, [], BASE_SETTINGS, [], MON)
    assert sum(s["minutes"] for s in a["sessions"]) > sum(s["minutes"] for s in b["sessions"])


def test_closer_exam_gets_priority():
    res = revision.plan([exam("Far", 20), exam("Near", 3)], ENTRIES, [], BASE_SETTINGS, [], MON)
    assert res["sessions"][0]["exam_id"] == "Near"


def test_shortfall_when_not_enough_time():
    res = revision.plan([exam("Big", 2, "high", prep=0, difficult="A, B, C")], ENTRIES, [], BASE_SETTINGS, [], MON)
    assert res["shortfalls"] and res["shortfalls"][0]["missing_minutes"] > 0


def test_cancelled_class_frees_time():
    exc = [{"id": "x", "date": MON.isoformat(), "kind": "day_off", "entry_id": None}]
    base = revision.plan([exam("Maths", 5, "high")], ENTRIES, [], BASE_SETTINGS, [], MON)
    off = revision.plan([exam("Maths", 5, "high")], ENTRIES, exc, BASE_SETTINGS, [], MON)
    first_base = [s for s in base["sessions"] if s["date"] == MON.isoformat()]
    first_off = [s for s in off["sessions"] if s["date"] == MON.isoformat()]
    assert first_off[0]["start"] < first_base[0]["start"]
    assert_no_overlaps(off["sessions"], ENTRIES, exc)


def test_done_sessions_reduce_need_and_past_exams_ignored():
    e = exam("Maths", 8)
    need = revision.needed_minutes(e)
    done = [{"id": "s", "exam_id": "Maths", "date": MON.isoformat(), "start": "18:00", "end": "18:45", "minutes": need, "status": "done", "locked": 0}]
    assert revision.plan([e], ENTRIES, [], BASE_SETTINGS, done, MON)["sessions"] == []
    past = exam("Old", -1)
    assert revision.plan([past], ENTRIES, [], BASE_SETTINGS, [], MON)["sessions"] == []
    assert revision.plan([{**e, "status": "done"}], ENTRIES, [], BASE_SETTINGS, [], MON)["sessions"] == []


def test_today_starts_after_now():
    res = revision.plan([exam("Maths", 4, "high")], [], [], BASE_SETTINGS, [], MON, now_min=sch.to_min("15:02"))
    today = [s for s in res["sessions"] if s["date"] == MON.isoformat()]
    assert today and today[0]["start"] >= "15:15"


def test_missed_slot_not_reused_same_day():
    missed = {"id": "m", "exam_id": "Maths", "date": MON.isoformat(), "start": "17:15", "end": "18:00", "minutes": 45, "status": "missed", "locked": 0}
    res = revision.plan([exam("Maths", 5, "high")], ENTRIES, [], BASE_SETTINGS, [missed], MON)
    today = [s for s in res["sessions"] if s["date"] == MON.isoformat()]
    assert today and all(not sch.overlaps(sch.to_min(s["start"]), sch.to_min(s["end"]), 17 * 60 + 15, 18 * 60) for s in today)
