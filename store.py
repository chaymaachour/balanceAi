"""Data access helpers shared by the API and the reminder scheduler."""
from __future__ import annotations

import json

import db
from validators import DEFAULT_SETTINGS


def ensure_user(uid: str) -> None:
    with db.tx() as c:
        now = db.utcnow()
        c.execute("INSERT OR IGNORE INTO users(id, settings, created_at, updated_at) VALUES(?,?,?,?)",
                  (uid, json.dumps(DEFAULT_SETTINGS), now, now))


def get_settings(uid: str) -> dict:
    with db.tx() as c:
        row = c.execute("SELECT settings FROM users WHERE id=?", (uid,)).fetchone()
    stored = db.load_json(row["settings"], {}) if row else {}
    return {**DEFAULT_SETTINGS, **stored}


def save_settings(uid: str, settings: dict) -> None:
    with db.tx() as c:
        c.execute("UPDATE users SET settings=?, updated_at=? WHERE id=?",
                  (json.dumps(settings, ensure_ascii=False), db.utcnow(), uid))


def all_user_ids() -> list[str]:
    with db.tx() as c:
        return [r["id"] for r in c.execute("SELECT id FROM users")]


def delete_user(uid: str) -> None:
    with db.tx() as c:
        c.execute("DELETE FROM users WHERE id=?", (uid,))


def entries(uid: str) -> list[dict]:
    with db.tx() as c:
        out = db.rows(c.execute("SELECT * FROM schedule_entries WHERE user_id=? ORDER BY day, start", (uid,)))
    for e in out:
        e["recurring"] = bool(e["recurring"])
    return out


def exceptions(uid: str) -> list[dict]:
    with db.tx() as c:
        return db.rows(c.execute("SELECT * FROM schedule_exceptions WHERE user_id=? ORDER BY date", (uid,)))


def exams(uid: str) -> list[dict]:
    with db.tx() as c:
        return db.rows(c.execute("SELECT * FROM exams WHERE user_id=? ORDER BY date IS NULL, date, time", (uid,)))


def sessions(uid: str) -> list[dict]:
    with db.tx() as c:
        return db.rows(c.execute("SELECT * FROM revision_sessions WHERE user_id=? ORDER BY date, start", (uid,)))


def context(uid: str) -> dict:
    return {"uid": uid, "settings": get_settings(uid), "entries": entries(uid), "exceptions": exceptions(uid),
            "exams": exams(uid), "sessions": sessions(uid)}


def insert_entry(c, uid: str, e: dict) -> str:
    eid = db.new_id()
    c.execute('INSERT INTO schedule_entries(id,user_id,kind,title,day,start,"end",location,recurring,date,created_at) '
              "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
              (eid, uid, e["kind"], e["title"], e["day"], e["start"], e["end"], e.get("location", ""),
               1 if e["recurring"] else 0, e.get("date"), db.utcnow()))
    return eid
