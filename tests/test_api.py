import json
from datetime import timedelta

import schedule as sch


def j(r):
    return json.loads(r.data)


def test_login_required_and_device_header_ignored(client):
    anon = client.application.test_client()
    assert anon.get("/api/schedule").status_code == 401
    # the legacy device header must NOT grant access
    assert anon.get("/api/schedule", headers={"X-BalanceAI-User": client.uid}).status_code == 401


def test_pages_and_status(client):
    assert client.get("/").status_code == 200
    assert client.get("/sw.js").status_code == 200
    assert j(client.get("/api/status"))["ai_enabled"] is False


def test_onboarding_profiles_and_template(client):
    r = client.post("/api/me/onboarding", json={"profile": "lycee", "use_template": True, "subjects": "Maths, Physique"}, headers=client.h)
    assert j(r)["template_entries"] > 0 and j(r)["settings"]["onboarded"]
    entries = j(client.get("/api/schedule", headers=client.h))["entries"]
    assert {e["title"] for e in entries} <= {"Maths", "Physique"}
    r = client.put("/api/me/settings", json={"profile": "universite"}, headers=client.h)
    assert j(r)["settings"]["profile"] == "universite"
    r = client.post("/api/schedule/template", json={"profile": "universite", "replace": True}, headers=client.h)
    assert j(r)["added"] > 0
    assert client.put("/api/me/settings", json={"study_start": "22:00", "study_end": "21:00"}, headers=client.h).status_code == 400


def test_course_crud_conflicts_and_persistence(client):
    h = client.h
    r = client.post("/api/schedule/entries", json={"title": "Maths", "day": 0, "start": "08:00", "end": "10:00"}, headers=h)
    assert r.status_code == 201
    eid = j(r)["entry"]["id"]
    r = client.post("/api/schedule/entries", json={"title": "Club théâtre", "kind": "club", "day": 0, "start": "09:00", "end": "11:00"}, headers=h)
    assert r.status_code == 409 and j(r)["conflicts"][0]["title"] == "Maths"
    r = client.post("/api/schedule/entries", json={"title": "Club théâtre", "kind": "club", "day": 0, "start": "17:00", "end": "18:00"}, headers=h)
    club = j(r)["entry"]["id"]
    assert client.put(f"/api/schedule/entries/{eid}", json={"title": "Maths avancées", "day": 1, "start": "08:00", "end": "10:00"}, headers=h).status_code == 200
    titles = {e["title"] for e in j(client.get("/api/schedule", headers=h))["entries"]}
    assert titles == {"Maths avancées", "Club théâtre"}
    assert client.delete(f"/api/schedule/entries/{club}", headers=h).status_code == 200
    assert client.post("/api/schedule/entries", json={"title": "X", "day": 0, "start": "10:00", "end": "09:00"}, headers=h).status_code == 400
    assert client.post("/api/schedule/entries", json={"title": "", "day": 0, "start": "08:00", "end": "09:00"}, headers=h).status_code == 400
    intruder = client.application.make_client("intruder@example.com")
    assert intruder.delete(f"/api/schedule/entries/{eid}", headers=intruder.h).status_code == 404


def test_cancel_and_day_off(client):
    h = client.h
    today = sch.now().date()
    eid = j(client.post("/api/schedule/entries", json={"title": "Physique", "day": today.weekday(), "start": "08:00", "end": "10:00"}, headers=h))["entry"]["id"]
    r = client.post("/api/schedule/exceptions", json={"kind": "cancel", "date": today.isoformat(), "entry_id": eid}, headers=h)
    assert r.status_code == 201
    days = j(client.get(f"/api/calendar?start={today.isoformat()}", headers=h))["days"]
    item = [d for d in days if d["date"] == today.isoformat()][0]["items"][0]
    assert item["cancelled"]
    r = client.post("/api/schedule/exceptions", json={"kind": "day_off", "date": today.isoformat()}, headers=h)
    assert r.status_code == 201
    assert client.delete(f"/api/schedule/exceptions/{j(r)['exception']['id']}", headers=h).status_code == 200


def _exam(client, days, **kw):
    d = (sch.now().date() + timedelta(days=days)).isoformat()
    return client.post("/api/exams", json={"subject": "Maths", "date": d, "priority": "high", "chapters": "Suites, Intégrales", **kw}, headers=client.h)


def test_exam_crud_and_plan_and_move(client):
    h = client.h
    r = _exam(client, 6)
    assert r.status_code == 201 and j(r)["plan"]["created"] > 0
    eid = j(r)["exam"]["id"]
    sessions = j(client.get("/api/revisions", headers=h))["sessions"]
    first_dates = {s["date"] for s in sessions}
    new_date = (sch.now().date() + timedelta(days=12)).isoformat()
    r = client.put(f"/api/exams/{eid}", json={"date": new_date}, headers=h)
    assert r.status_code == 200
    sessions2 = j(client.get("/api/revisions", headers=h))["sessions"]
    assert max(s["date"] for s in sessions2) > max(first_dates)  # plan follows the moved exam
    exams = j(client.get("/api/exams", headers=h))["exams"]
    assert exams[0]["date"] == new_date and exams[0]["progress"]["planned"] > 0
    assert client.post("/api/exams", json={"subject": ""}, headers=h).status_code == 400
    assert client.post("/api/exams", json={"subject": "A", "date": "2026-13-40"}, headers=h).status_code == 400
    r = client.put(f"/api/exams/{eid}", json={"status": "done"}, headers=h)
    left = [s for s in j(client.get("/api/revisions", headers=h))["sessions"] if s["status"] == "planned"]
    assert left == []  # finished exam -> no more planned sessions / reminders
    assert client.delete(f"/api/exams/{eid}", headers=h).status_code == 200
    assert j(client.get("/api/exams", headers=h))["exams"] == []


def test_missed_session_reschedules_and_notifies(client):
    h = client.h
    _exam(client, 8)
    s = [x for x in j(client.get("/api/revisions", headers=h))["sessions"] if x["status"] == "planned"][0]
    r = client.patch(f"/api/revisions/{s['id']}", json={"status": "missed"}, headers=h)
    assert r.status_code == 200 and j(r)["rescheduled"]
    items = j(client.get("/api/notifications", headers=h))["items"]
    assert any(i["kind"] == "rescheduled" for i in items)
    s2 = [x for x in j(client.get("/api/revisions", headers=h))["sessions"] if x["status"] == "planned"][0]
    assert client.patch(f"/api/revisions/{s2['id']}", json={"status": "done"}, headers=h).status_code == 200
    assert client.patch(f"/api/revisions/{s2['id']}", json={"status": "weird"}, headers=h).status_code == 400


def test_move_session_conflict(client):
    h = client.h
    day = sch.now().date() + timedelta(days=2)
    client.post("/api/schedule/entries", json={"title": "Algo", "day": day.weekday(), "start": "08:00", "end": "10:00"}, headers=h)
    _exam(client, 9)
    s = [x for x in j(client.get("/api/revisions", headers=h))["sessions"] if x["status"] == "planned"][0]
    r = client.patch(f"/api/revisions/{s['id']}", json={"date": day.isoformat(), "start": "09:00", "minutes": 45}, headers=h)
    assert r.status_code == 409
    r = client.patch(f"/api/revisions/{s['id']}", json={"date": day.isoformat(), "start": "06:00", "minutes": 45}, headers=h)
    assert r.status_code == 200 and j(r)["session"]["locked"] == 1


def test_notifications_read_and_dedupe(client):
    import notifications
    h = client.h
    client.get("/api/me", headers=h)
    item = {"kind": "day_end", "dedupe_key": "day_end:2026-10-19", "title": "t", "body": "b", "link": "#checkin"}
    assert notifications.create(client.uid, item)
    assert notifications.create(client.uid, item) is None  # duplicate ignored
    data = j(client.get("/api/notifications", headers=h))
    assert data["unread"] == 1
    nid = data["items"][0]["id"]
    assert client.post(f"/api/notifications/{nid}/read", headers=h).status_code == 200
    assert j(client.get("/api/notifications", headers=h))["unread"] == 0
    client.post("/api/notifications/test", headers=h)
    assert client.post("/api/notifications/read-all", headers=h).status_code == 200


def test_tick_creates_due_reminder_once(client):
    from datetime import datetime
    import notifications
    h = client.h
    client.put("/api/me/settings", json={"wellness_reminder": True, "checkin_time": "19:00", "reminder_days": [0, 1, 2, 3, 4, 5, 6]}, headers=h)
    when = datetime(2026, 10, 19, 19, 5, tzinfo=sch.TZ)
    assert notifications.tick(when, only_user=client.uid)["created"] == 1
    assert notifications.tick(when + timedelta(minutes=1), only_user=client.uid)["created"] == 0
    early = datetime(2026, 10, 20, 18, 0, tzinfo=sch.TZ)
    assert notifications.tick(early, only_user=client.uid)["created"] == 0


def test_dashboard_and_delete_me(client):
    h = client.h
    d = j(client.get("/api/dashboard", headers=h))
    assert d["has_schedule"] is False and d["next_exam"] is None
    _exam(client, 5)
    d = j(client.get("/api/dashboard", headers=h))
    assert d["next_exam"]["subject"] == "Maths" and d["next_sessions"]
    assert client.delete("/api/me", json={"password": "wrong"}, headers=h).status_code == 403
    assert client.delete("/api/me", json={"password": "Sup3rSecret99"}, headers=h).status_code == 200
    assert client.get("/api/me").status_code == 401
