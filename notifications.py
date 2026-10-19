"""Reminder engine: decides which notifications are due, stores them in the
in-app notification centre (deduplicated) and sends Web Push when enabled."""
from __future__ import annotations

import logging
from datetime import date as Date, datetime, timedelta, timezone

import db
import push
import revision
import schedule as sch
import store
from messages import encouragement, pick, t

EXPIRE_DAYS = 3
log = logging.getLogger("balanceai.notifications")
CATCH_UP_MINUTES = 180
EMPTY_PLAN_DAYS = 21


def _days_left(exam: dict, today: Date):
    return (Date.fromisoformat(exam["date"]) - today).days if exam.get("date") else None


def compute_due(ctx: dict, today: Date) -> list[dict]:
    """All reminders for `today` with their time (minutes of day). Pure logic."""
    s = ctx["settings"]
    if not s.get("notifications_enabled", True):
        return []
    lang = s.get("notif_lang", "fr")
    ds = today.isoformat()
    items_today = sch.effective_day(ctx["entries"], ctx["exceptions"], today)
    exams = {e["id"]: e for e in ctx["exams"]}
    upcoming = [e for e in ctx["exams"] if e["status"] == "upcoming" and e.get("date") and e["date"] >= ds]
    out = []

    def add(kind, at, key, title, body, link):
        if at is None or at < 0 or at >= 24 * 60 or sch.in_quiet_hours(at, s):
            return
        out.append({"kind": kind, "at": at, "dedupe_key": key, "title": title, "body": body, "link": link})

    # 1. End-of-day check-in (after classes + way home + rest), with exam-aware encouragement
    rem = sch.day_end_reminder(s, items_today, today)
    if rem["at"] is not None:
        if rem["reason"] == "wellness":
            title, body = t(lang, "wellness_title"), pick(lang, "wellness", ds)
        else:
            title, body = t(lang, "day_end_title"), pick(lang, "day_end", ds)
        soon = [e for e in upcoming if 0 < _days_left(e, today) <= 7]
        if soon and s.get("exam_reminders", True):
            e = min(soon, key=lambda x: x["date"])
            pct = revision.progress(e, ctx["sessions"])["percent"]
            body += " " + encouragement(lang, _days_left(e, today), pct, e["subject"], seed=ds + e["id"])
        add("day_end", rem["at"], f"day_end:{ds}", title, body, "#checkin")

    if s.get("exam_reminders", True):
        for e in upcoming:
            dl = _days_left(e, today)
            if dl == 0:  # exam day: morning wish, before the exam
                at = sch.to_min(s["quiet_end"]) if s.get("quiet_end") else 7 * 60
                if e.get("time"):
                    at = min(at, sch.to_min(e["time"]) - 30)
                add("exam_day", at, f"examday:{e['id']}:{ds}", t(lang, "examday_title"),
                    pick(lang, "examday", e["id"], subject=e["subject"]), "#exams")
            elif dl <= EMPTY_PLAN_DAYS:
                has_plan = any(x["exam_id"] == e["id"] and x["status"] in ("planned", "done") for x in ctx["sessions"])
                if not has_plan:  # suggest creating a plan instead of a useless reminder
                    at = rem["at"] if rem["at"] is not None else 18 * 60
                    add("empty_plan", at, f"empty:{e['id']}", t(lang, "empty_title"),
                        pick(lang, "empty", e["id"], subject=e["subject"]), "#revisions")

    # 2. Revision sessions of today (only for exams that are still upcoming)
    for x in ctx["sessions"]:
        if x["date"] != ds or x["status"] != "planned":
            continue
        e = exams.get(x["exam_id"])
        if not e or e["status"] != "upcoming":
            continue
        start, end = sch.to_min(x["start"]), sch.to_min(x["end"])
        if s.get("session_reminders", True):
            add("session", start - 10, f"session:{x['id']}:{ds}:{x['start']}", t(lang, "session_title"),
                pick(lang, "session", x["id"], subject=e["subject"], start=x["start"], minutes=x["minutes"]), "#revisions")
            add("session_check", end + 15, f"check:{x['id']}:{ds}:{x['start']}", t(lang, "check_title"),
                pick(lang, "check", x["id"], subject=e["subject"]), "#revisions")
    out.sort(key=lambda i: i["at"])
    return out


def create(uid: str, item: dict, scheduled_for: str | None = None) -> str | None:
    """Insert a notification; returns its id, or None if it already existed (dedupe)."""
    nid = db.new_id()
    with db.tx() as c:
        cur = c.execute(
            "INSERT OR IGNORE INTO notifications(id,user_id,kind,title,body,link,scheduled_for,created_at,dedupe_key) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (nid, uid, item["kind"], item["title"], item["body"], item.get("link", "#home"), scheduled_for,
             db.utcnow(), item["dedupe_key"]))
    return nid if cur.rowcount else None


def deliver(uid: str, item: dict, settings: dict, scheduled_for: str | None = None) -> tuple[bool, int]:
    nid = create(uid, item, scheduled_for)
    if not nid:
        return False, 0
    sent = push.send_to_user(uid, item, settings)
    if sent:
        with db.tx() as c:
            c.execute("UPDATE notifications SET pushed=1 WHERE id=?", (nid,))
    return True, sent


def tick(now: datetime | None = None, only_user: str | None = None) -> dict:
    """Create (and push) every reminder that is due now. Safe to call often."""
    now = now or sch.now()
    today, nm = now.date(), now.hour * 60 + now.minute
    created = pushed = 0
    for uid in ([only_user] if only_user else store.all_user_ids()):
        try:
            ctx = store.context(uid)
            for item in compute_due(ctx, today):
                if nm - CATCH_UP_MINUTES <= item["at"] <= nm:
                    ok, sent = deliver(uid, item, ctx["settings"], f"{today.isoformat()}T{sch.to_hm(item['at'])}")
                    created += ok
                    pushed += sent
        except Exception:  # one broken user must not stop the others
            log.exception("Reminder tick failed for a user")
    return {"created": created, "pushed": pushed}


def upcoming(ctx: dict, now: datetime) -> list[dict]:
    """Reminders still to come today and tomorrow (for the notification centre)."""
    nm = now.hour * 60 + now.minute
    out = []
    for offset in (0, 1):
        d = now.date() + timedelta(days=offset)
        for item in compute_due(ctx, d):
            if offset or item["at"] > nm:
                out.append({"kind": item["kind"], "title": item["title"], "date": d.isoformat(),
                            "time": sch.to_hm(item["at"])})
    return out[:12]


def _status(row: dict) -> str:
    """read | sent | expired. (Pending reminders are computed live and never stored; see upcoming().)"""
    if row["read"]:
        return "read"
    try:
        age = datetime.now(timezone.utc) - datetime.fromisoformat(row["created_at"])
        return "expired" if age > timedelta(days=EXPIRE_DAYS) else "sent"
    except ValueError:
        return "sent"


def list_for(uid: str, limit: int = 50) -> list[dict]:
    with db.tx() as c:
        rows = db.rows(c.execute("SELECT id,kind,title,body,link,scheduled_for,created_at,read,pushed FROM notifications "
                                 "WHERE user_id=? ORDER BY created_at DESC, rowid DESC LIMIT ?", (uid, limit)))
    for r in rows:
        r["status"] = _status(r)
    return rows
