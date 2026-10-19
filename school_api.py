"""API for profiles, timetable, exams, revision plans, notifications and Web Push.

Users are identified by an anonymous random device ID (header X-BalanceAI-User)
generated in the browser: no name, e-mail or password is collected.
"""
from __future__ import annotations

import logging
import re
from datetime import date as Date, timedelta

from flask import Blueprint, jsonify, request

import ai_service
import config
import db
import notifications
import push
import revision
import schedule as sch
import auth
import store
from demo_fallback import demo_coach
from messages import pick, t
from validators import (DEFAULT_SETTINGS, ValidationError, parse_date, parse_entry, parse_exam, parse_exception,
                        parse_session_patch, parse_settings, parse_subscription, validate_coach)

log = logging.getLogger("balanceai.school")
bp = Blueprint("school", __name__, url_prefix="/api")
UID_RE = re.compile(r"^[a-z0-9-]{16,40}$")
REPLAN_KEYS = ("study_start", "study_end", "daily_study_minutes", "session_minutes", "break_minutes",
               "commute_minutes", "rest_minutes", "home_time")


class NotFound(Exception):
    pass


@bp.errorhandler(ValidationError)
def _bad(exc):
    return jsonify({"error": str(exc)}), 400


@bp.errorhandler(NotFound)
def _missing(exc):
    return jsonify({"error": "Not found."}), 404


def uid() -> str:
    """The user id comes ONLY from the authenticated session (never from the request)."""
    return auth.current_user_id()


def body() -> dict:
    data = request.get_json(silent=True)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValidationError("Invalid request body.")
    return data


def _owned(table: str, user: str, item_id: str) -> dict:
    with db.tx() as c:
        row = c.execute(f"SELECT * FROM {table} WHERE id=? AND user_id=?", (item_id, user)).fetchone()
    if not row:
        raise NotFound()
    return dict(row)


def _now_parts():
    now = sch.now()
    return now, now.date(), now.hour * 60 + now.minute


# ------------------------------------------------------------------ replanning
def replan(user: str) -> dict:
    """Rebuild future planned sessions from real free slots. Done, missed and
    manually moved (locked) sessions are kept."""
    now, today, nm = _now_parts()
    ctx = store.context(user)
    active = {e["id"] for e in revision.active_exams(ctx["exams"], today)}
    with db.tx() as c:
        c.execute("UPDATE revision_sessions SET status='missed', updated_at=? WHERE user_id=? AND status='planned' "
                  'AND (date<? OR (date=? AND "end"<=?))', (db.utcnow(), user, today.isoformat(), today.isoformat(), sch.to_hm(nm)))
        for s in ctx["sessions"]:
            if s["status"] == "planned" and (not s["locked"] or s["exam_id"] not in active):
                c.execute("DELETE FROM revision_sessions WHERE id=? AND status='planned' AND (date>? OR (date=? AND \"end\">?))",
                          (s["id"], today.isoformat(), today.isoformat(), sch.to_hm(nm)))
    ctx = store.context(user)
    res = revision.plan(ctx["exams"], ctx["entries"], ctx["exceptions"], ctx["settings"], ctx["sessions"], today, nm)
    with db.tx() as c:
        for s in res["sessions"]:
            c.execute('INSERT INTO revision_sessions(id,user_id,exam_id,date,start,"end",minutes,status,locked,focus,created_at,updated_at) '
                      "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                      (db.new_id(), user, s["exam_id"], s["date"], s["start"], s["end"], s["minutes"], "planned", 0,
                       s["focus"], db.utcnow(), db.utcnow()))
    subjects = {e["id"]: e["subject"] for e in ctx["exams"]}
    return {"created": len(res["sessions"]), "exams": res["exams"],
            "shortfalls": [{**x, "subject": subjects.get(x["exam_id"], "")} for x in res["shortfalls"]]}


def _replan_if_exams(user: str):
    return replan(user) if store.exams(user) else None


# ------------------------------------------------------------------ profile & settings
@bp.get("/me")
def me():
    user = uid()
    return jsonify({"settings": store.get_settings(user), "has_schedule": bool(store.entries(user)),
                    "push": {"available": push.AVAILABLE and bool(push.public_key()), "subscriptions": len(push.subscriptions(user))},
                    "timezone": config.TIMEZONE})


@bp.put("/me/settings")
def update_settings():
    user = uid()
    old = store.get_settings(user)
    new = parse_settings(body(), old)
    store.save_settings(user, new)
    plan = _replan_if_exams(user) if any(old.get(k) != new.get(k) for k in REPLAN_KEYS) else None
    return jsonify({"settings": new, "plan": plan})


@bp.post("/me/onboarding")
def onboarding():
    user = uid()
    data = body()
    settings = parse_settings({**data, "onboarded": True}, store.get_settings(user))
    store.save_settings(user, settings)
    added = 0
    if data.get("use_template") and settings["profile"] in ("lycee", "universite") and not store.entries(user):
        with db.tx() as c:
            for e in sch.template_entries(settings["profile"], settings["subjects"]):
                store.insert_entry(c, user, e)
                added += 1
    return jsonify({"settings": settings, "template_entries": added})


@bp.post("/me/reset")
def reset_me():
    """Erase timetable, exams, revisions, notifications and push subscriptions but keep the account."""
    user = uid()
    with db.tx() as c:
        for table in ("revision_sessions", "exams", "schedule_exceptions", "schedule_entries", "notifications", "push_subscriptions"):
            c.execute(f"DELETE FROM {table} WHERE user_id=?", (user,))
    store.save_settings(user, dict(DEFAULT_SETTINGS))
    return jsonify({"reset": True})


@bp.delete("/me")
def delete_me():
    return auth.delete_account()  # requires the account password


# ------------------------------------------------------------------ timetable
@bp.get("/schedule")
def get_schedule():
    user = uid()
    return jsonify({"entries": store.entries(user), "exceptions": store.exceptions(user)})


def _save_entry(user: str, entry_id: str | None):
    data = body()
    entry = parse_entry(data)
    current = store.entries(user)
    conflicts = sch.find_conflicts(current, {**entry, "id": entry_id or ""}, ignore_id=entry_id)
    if conflicts and not data.get("force"):
        return jsonify({"error": "conflict", "conflicts": conflicts}), 409
    with db.tx() as c:
        if entry_id:
            c.execute('UPDATE schedule_entries SET kind=?,title=?,day=?,start=?,"end"=?,location=?,recurring=?,date=? '
                      "WHERE id=? AND user_id=?",
                      (entry["kind"], entry["title"], entry["day"], entry["start"], entry["end"], entry["location"],
                       1 if entry["recurring"] else 0, entry["date"], entry_id, user))
            new_id = entry_id
        else:
            new_id = store.insert_entry(c, user, entry)
    return jsonify({"entry": {**entry, "id": new_id}, "conflicts": conflicts, "plan": _replan_if_exams(user)}), 200 if entry_id else 201


@bp.post("/schedule/entries")
def add_entry():
    return _save_entry(uid(), None)


@bp.put("/schedule/entries/<entry_id>")
def edit_entry(entry_id):
    user = uid()
    _owned("schedule_entries", user, entry_id)
    return _save_entry(user, entry_id)


@bp.delete("/schedule/entries/<entry_id>")
def delete_entry(entry_id):
    user = uid()
    _owned("schedule_entries", user, entry_id)
    with db.tx() as c:
        c.execute("DELETE FROM schedule_entries WHERE id=? AND user_id=?", (entry_id, user))
    return jsonify({"deleted": True, "plan": _replan_if_exams(user)})


@bp.post("/schedule/template")
def apply_template():
    user = uid()
    data = body()
    settings = store.get_settings(user)
    profile = data.get("profile") if data.get("profile") in ("lycee", "universite") else settings["profile"]
    if profile not in ("lycee", "universite"):
        raise ValidationError("Choose the Lycée or Université profile to use a template.")
    with db.tx() as c:
        if data.get("replace"):
            c.execute("DELETE FROM schedule_entries WHERE user_id=? AND kind='course'", (user,))
        entries = sch.template_entries(profile, settings["subjects"])
        for e in entries:
            store.insert_entry(c, user, e)
    return jsonify({"added": len(entries), "plan": _replan_if_exams(user)})


@bp.post("/schedule/exceptions")
def add_exception():
    user = uid()
    x = parse_exception(body())
    if x["entry_id"]:
        _owned("schedule_entries", user, x["entry_id"])
    with db.tx() as c:
        if x["entry_id"]:
            c.execute("DELETE FROM schedule_exceptions WHERE user_id=? AND date=? AND entry_id=?", (user, x["date"], x["entry_id"]))
        else:
            c.execute("DELETE FROM schedule_exceptions WHERE user_id=? AND date=? AND kind='day_off'", (user, x["date"]))
        xid = db.new_id()
        c.execute('INSERT INTO schedule_exceptions(id,user_id,date,entry_id,kind,start,"end",note,created_at) VALUES(?,?,?,?,?,?,?,?,?)',
                  (xid, user, x["date"], x["entry_id"], x["kind"], x["start"], x["end"], x["note"], db.utcnow()))
    return jsonify({"exception": {**x, "id": xid}, "plan": _replan_if_exams(user)}), 201


@bp.delete("/schedule/exceptions/<exc_id>")
def delete_exception(exc_id):
    user = uid()
    _owned("schedule_exceptions", user, exc_id)
    with db.tx() as c:
        c.execute("DELETE FROM schedule_exceptions WHERE id=? AND user_id=?", (exc_id, user))
    return jsonify({"deleted": True, "plan": _replan_if_exams(user)})


@bp.get("/calendar")
def calendar():
    user = uid()
    start = parse_date(request.args.get("start"), "start", required=False)
    base = Date.fromisoformat(start) if start else sch.now().date()
    ctx = store.context(user)
    subjects = {e["id"]: e["subject"] for e in ctx["exams"]}
    days = []
    for d in sch.week_dates(base):
        ds = d.isoformat()
        days.append({
            "date": ds, "weekday": d.weekday(), "day_off": sch.is_day_off(ctx["exceptions"], d),
            "items": sch.effective_day(ctx["entries"], ctx["exceptions"], d),
            "sessions": [{**s, "subject": subjects.get(s["exam_id"], "")} for s in ctx["sessions"] if s["date"] == ds],
            "exams": [e for e in ctx["exams"] if e.get("date") == ds],
            "reminder": sch.day_end_reminder(ctx["settings"], sch.effective_day(ctx["entries"], ctx["exceptions"], d), d),
        })
    return jsonify({"days": days, "today": sch.now().date().isoformat()})


# ------------------------------------------------------------------ exams
def _exam_view(e: dict, sessions: list[dict], today: Date) -> dict:
    dl = (Date.fromisoformat(e["date"]) - today).days if e.get("date") else None
    if e["status"] == "done":
        state = "done"
    elif dl is None:
        state = "no_date"
    elif dl < 0:
        state = "past"
    elif dl == 0:
        state = "today"
    else:
        state = "upcoming"
    return {**e, "days_left": dl, "state": state, "progress": revision.progress(e, sessions)}


@bp.get("/exams")
def list_exams():
    user = uid()
    today = sch.now().date()
    sessions = store.sessions(user)
    return jsonify({"exams": [_exam_view(e, sessions, today) for e in store.exams(user)]})


@bp.post("/exams")
def add_exam():
    user = uid()
    e = parse_exam(body())
    eid = db.new_id()
    with db.tx() as c:
        c.execute("INSERT INTO exams(id,user_id,subject,title,chapters,difficult,date,time,priority,preparation,minutes_per_day,status,created_at,updated_at) "
                  "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                  (eid, user, e["subject"], e["title"], e["chapters"], e["difficult"], e["date"], e["time"], e["priority"],
                   e["preparation"], e["minutes_per_day"], e["status"], db.utcnow(), db.utcnow()))
    return jsonify({"exam": {**e, "id": eid}, "plan": replan(user)}), 201


@bp.put("/exams/<exam_id>")
def edit_exam(exam_id):
    user = uid()
    old = _owned("exams", user, exam_id)
    e = parse_exam({**old, **body()})
    with db.tx() as c:
        c.execute("UPDATE exams SET subject=?,title=?,chapters=?,difficult=?,date=?,time=?,priority=?,preparation=?,"
                  "minutes_per_day=?,status=?,updated_at=? WHERE id=? AND user_id=?",
                  (e["subject"], e["title"], e["chapters"], e["difficult"], e["date"], e["time"], e["priority"],
                   e["preparation"], e["minutes_per_day"], e["status"], db.utcnow(), exam_id, user))
    return jsonify({"exam": {**e, "id": exam_id}, "plan": replan(user)})


@bp.delete("/exams/<exam_id>")
def delete_exam(exam_id):
    user = uid()
    _owned("exams", user, exam_id)
    with db.tx() as c:
        c.execute("DELETE FROM exams WHERE id=? AND user_id=?", (exam_id, user))
    return jsonify({"deleted": True, "plan": replan(user)})


@bp.post("/exams/<exam_id>/coach")
def coach(exam_id):
    user = uid()
    e = _owned("exams", user, exam_id)
    data = body()
    lang = data.get("lang") if data.get("lang") in ("fr", "en", "tn") else store.get_settings(user)["notif_lang"]
    today = sch.now().date()
    prog = revision.progress(e, store.sessions(user))
    info = {  # only what the coach needs: no identity, no free-text journal
        "lang": lang, "subject": e["subject"], "exam": e["title"],
        "chapters": revision.split_list(e["chapters"]), "difficult": revision.split_list(e["difficult"]),
        "days_left": (Date.fromisoformat(e["date"]) - today).days if e.get("date") else None,
        "preparation": e["preparation"], "percent": prog["percent"],
        "minutes_done": prog["done"], "minutes_planned": prog["planned"],
    }
    result, ai_used, error = None, False, None
    if config.ai_enabled():
        try:
            result = validate_coach(ai_service.exam_coach(info))
            ai_used = True
        except (ai_service.AIError, ValidationError) as exc:
            error = str(exc)
            log.warning("Falling back to demo coach: %s", error)
    if result is None:
        result = demo_coach(info)
    result["source"] = {"mode": "ai" if ai_used else "demo", "provider": config.provider_name() if ai_used else None,
                        "model": config.AI_MODEL if ai_used else None, "fallback_reason": error}
    return jsonify(result)


# ------------------------------------------------------------------ revisions
@bp.get("/revisions")
def list_revisions():
    user = uid()
    today = sch.now().date()
    exams = store.exams(user)
    sessions = store.sessions(user)
    subjects = {e["id"]: e["subject"] for e in exams}
    return jsonify({
        "sessions": [{**s, "subject": subjects.get(s["exam_id"], "")} for s in sessions],
        "progress": [{**revision.progress(e, sessions), "subject": e["subject"], "date": e["date"]}
                     for e in revision.active_exams(exams, today)],
        "today": today.isoformat(),
    })


@bp.post("/revisions/plan")
def make_plan():
    return jsonify(replan(uid()))


@bp.patch("/revisions/<session_id>")
def patch_session(session_id):
    user = uid()
    s = _owned("revision_sessions", user, session_id)
    p = parse_session_patch(body())
    plan, rescheduled = None, None
    if "date" in p:
        start = sch.to_min(p["start"])
        cand = {"date": p["date"], "start": p["start"], "end": sch.to_hm(start + p["minutes"])}
        ctx = store.context(user)
        conflicts = revision.session_conflicts(ctx["entries"], ctx["exceptions"], ctx["sessions"], cand, ignore_id=session_id)
        if conflicts and not p["force"]:
            return jsonify({"error": "conflict", "conflicts": conflicts}), 409
        with db.tx() as c:
            c.execute('UPDATE revision_sessions SET date=?, start=?, "end"=?, minutes=?, locked=1, status=\'planned\', updated_at=? '
                      "WHERE id=? AND user_id=?", (cand["date"], cand["start"], cand["end"], p["minutes"], db.utcnow(), session_id, user))
    if "status" in p:
        with db.tx() as c:
            c.execute("UPDATE revision_sessions SET status=?, updated_at=? WHERE id=? AND user_id=?",
                      (p["status"], db.utcnow(), session_id, user))
        if p["status"] == "missed":
            plan = replan(user)
            nxt = [x for x in store.sessions(user) if x["exam_id"] == s["exam_id"] and x["status"] == "planned"]
            settings = store.get_settings(user)
            exam = _owned("exams", user, s["exam_id"])
            if nxt:
                rescheduled = nxt[0]
                lang = settings["notif_lang"]
                notifications.deliver(user, {
                    "kind": "rescheduled", "dedupe_key": f"resched:{session_id}", "link": "#revisions",
                    "title": t(lang, "resched_title"),
                    "body": pick(lang, "resched", session_id, subject=exam["subject"], date=Date.fromisoformat(nxt[0]["date"]).strftime("%d/%m"), start=nxt[0]["start"]),
                }, settings)
    return jsonify({"session": _owned("revision_sessions", user, session_id), "plan": plan, "rescheduled": rescheduled})


@bp.delete("/revisions/<session_id>")
def delete_session(session_id):
    user = uid()
    _owned("revision_sessions", user, session_id)
    with db.tx() as c:
        c.execute("DELETE FROM revision_sessions WHERE id=? AND user_id=?", (session_id, user))
    return jsonify({"deleted": True})


# ------------------------------------------------------------------ notifications
@bp.get("/notifications")
def list_notifications():
    user = uid()
    notifications.tick(only_user=user)
    items = notifications.list_for(user)
    ctx = store.context(user)
    return jsonify({"items": items, "unread": sum(1 for i in items if not i["read"]),
                    "upcoming": notifications.upcoming(ctx, sch.now())})


@bp.post("/notifications/<nid>/read")
def read_notification(nid):
    user = uid()
    _owned("notifications", user, nid)
    with db.tx() as c:
        c.execute("UPDATE notifications SET read=1 WHERE id=? AND user_id=?", (nid, user))
    return jsonify({"read": True})


@bp.post("/notifications/read-all")
def read_all():
    user = uid()
    with db.tx() as c:
        c.execute("UPDATE notifications SET read=1 WHERE user_id=?", (user,))
    return jsonify({"read": True})


@bp.delete("/notifications/<nid>")
def delete_notification(nid):
    user = uid()
    _owned("notifications", user, nid)
    with db.tx() as c:
        c.execute("DELETE FROM notifications WHERE id=? AND user_id=?", (nid, user))
    return jsonify({"deleted": True})


@bp.post("/notifications/test")
def test_notification():
    user = uid()
    settings = store.get_settings(user)
    lang = settings["notif_lang"]
    item = {"kind": "test", "dedupe_key": f"test:{db.new_id()}", "link": "#notifications",
            "title": t(lang, "test_title"), "body": t(lang, "test_body")}
    _, sent = notifications.deliver(user, item, settings)
    return jsonify({"created": True, "pushed": sent, "subscriptions": len(push.subscriptions(user))})


# ------------------------------------------------------------------ web push
@bp.get("/push/public-key")
def push_key():
    uid()
    return jsonify({"available": push.AVAILABLE and bool(push.public_key()), "public_key": push.public_key()})


@bp.post("/push/subscribe")
def push_subscribe():
    user = uid()
    sub = parse_subscription(body())
    push.save_subscription(user, sub)
    settings = {**store.get_settings(user), "push_enabled": True}
    store.save_settings(user, settings)
    return jsonify({"subscribed": True, "settings": settings})


@bp.post("/push/unsubscribe")
def push_unsubscribe():
    user = uid()
    endpoint = body().get("endpoint")
    push.remove_subscription(user, endpoint if isinstance(endpoint, str) else None)
    settings = store.get_settings(user)
    if not push.subscriptions(user):
        settings["push_enabled"] = False
        store.save_settings(user, settings)
    return jsonify({"subscribed": False, "settings": settings})


# ------------------------------------------------------------------ dashboard
@bp.get("/dashboard")
def dashboard():
    user = uid()
    now, today, nm = _now_parts()
    ctx = store.context(user)
    subjects = {e["id"]: e["subject"] for e in ctx["exams"]}
    next_items = []
    for offset in range(0, 7):
        d = today + timedelta(days=offset)
        for i in sch.effective_day(ctx["entries"], ctx["exceptions"], d):
            if i["cancelled"] or (offset == 0 and sch.to_min(i["end"]) <= nm):
                continue
            next_items.append({"date": d.isoformat(), "title": i["title"], "kind": i["kind"], "start": i["start"], "end": i["end"]})
        if len(next_items) >= 3:
            break
    active = [_exam_view(e, ctx["sessions"], today) for e in ctx["exams"] if e["status"] == "upcoming" and e.get("date") and e["date"] >= today.isoformat()]
    future = [s for s in ctx["sessions"] if s["status"] == "planned" and (s["date"] > today.isoformat() or (s["date"] == today.isoformat() and s["end"] > sch.to_hm(nm)))]
    prog = [revision.progress(e, ctx["sessions"]) for e in revision.active_exams(ctx["exams"], today)]
    with db.tx() as c:
        unread = c.execute("SELECT COUNT(*) n FROM notifications WHERE user_id=? AND read=0", (user,)).fetchone()["n"]
    return jsonify({
        "profile": ctx["settings"]["profile"], "onboarded": ctx["settings"]["onboarded"],
        "has_schedule": bool(ctx["entries"]), "has_exams": bool(ctx["exams"]),
        "next_items": next_items[:3],
        "next_exam": active[0] if active else None,
        "next_sessions": [{**s, "subject": subjects.get(s["exam_id"], "")} for s in future[:3]],
        "progress": {"done": sum(p["done"] for p in prog), "needed": sum(max(p["needed"], p["done"]) for p in prog)},
        "unread": unread,
    })
