"""Validation and normalisation of user input and AI output.

AI output is never trusted blindly: every field is type-checked, trimmed and
clamped before it is sent to the browser.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta

MOODS = {"happy", "calm", "okay", "stressed", "overwhelmed", "tired", "frustrated"}
CONTEXTS = {"studies", "work", "career", "family", "personal", "other"}
PRIORITIES = ("high", "medium", "low")
CONFIDENCE = ("low", "medium", "high")
BLOCK_TYPES = ("task", "break", "habit")
MAX_TEXT = 2000


class ValidationError(ValueError):
    pass


def _str(value, max_len: int = 400, default: str = "") -> str:
    if value is None:
        return default
    if not isinstance(value, str):
        value = str(value)
    value = re.sub(r"\s+", " ", value).strip()
    return value[:max_len]


def _int(value, lo: int, hi: int, default: int) -> int:
    try:
        n = int(round(float(value)))
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, n))


def _choice(value, options, default):
    value = _str(value, 20).lower()
    return value if value in options else default


def _list(value, limit: int):
    return value[:limit] if isinstance(value, list) else []


# ---------------------------------------------------------------- user input

def parse_checkin(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ValidationError("Invalid request body.")
    mood = _choice(payload.get("mood"), MOODS, "")
    if not mood:
        raise ValidationError("Please choose a mood.")
    contexts = [c for c in _list(payload.get("contexts"), 6) if c in CONTEXTS]
    text = payload.get("text") or ""
    if not isinstance(text, str):
        raise ValidationError("Description must be text.")
    text = text.strip()
    if len(text) > MAX_TEXT:
        raise ValidationError(f"Description is too long (max {MAX_TEXT} characters).")
    lang = _choice(payload.get("lang"), ("en", "fr"), "en")
    return {"mood": mood, "contexts": contexts, "text": text, "lang": lang}


def parse_plan_request(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ValidationError("Invalid request body.")
    tasks = []
    for i, t in enumerate(_list(payload.get("tasks"), 15)):
        if not isinstance(t, dict):
            continue
        title = _str(t.get("title"), 120)
        if not title:
            continue
        tasks.append({
            "id": _str(t.get("id"), 40) or f"t{i + 1}",
            "title": title,
            "priority": _choice(t.get("priority"), PRIORITIES, "medium"),
            "minutes": _int(t.get("minutes"), 5, 480, 30),
            "deadline": _str(t.get("deadline"), 20) or None,
        })
    if not tasks:
        raise ValidationError("Add at least one task.")
    start = _str(payload.get("start_time"), 5) or datetime.now().strftime("%H:%M")
    if not re.fullmatch(r"\d{2}:\d{2}", start):
        start = "09:00"
    insight = payload.get("insight") if isinstance(payload.get("insight"), dict) else {}
    return {
        "tasks": tasks,
        "available_minutes": _int(payload.get("available_minutes"), 30, 960, 240),
        "break_minutes": _int(payload.get("break_minutes"), 3, 30, 10),
        "stress_level": _int(payload.get("stress_level"), 1, 10, 5),
        "start_time": start,
        "lang": _choice(payload.get("lang"), ("en", "fr"), "en"),
        "insight": {
            "summary": _str(insight.get("summary"), 300),
            "emotions": [_str(e, 40) for e in _list(insight.get("emotions"), 4)],
            "mood": _choice(insight.get("mood"), MOODS, ""),
        },
    }


# ---------------------------------------------------------------- AI output

def validate_analysis(data: dict) -> dict:
    if not isinstance(data, dict):
        raise ValidationError("AI response is not an object.")
    emotions = []
    for e in _list(data.get("emotions"), 5):
        if isinstance(e, dict) and _str(e.get("name"), 40):
            emotions.append({
                "name": _str(e.get("name"), 40),
                "confidence": _choice(e.get("confidence"), CONFIDENCE, "medium"),
                "evidence": _str(e.get("evidence"), 250),
            })
    signals = []
    for s in _list(data.get("stress_signals"), 5):
        if isinstance(s, dict) and _str(s.get("quote"), 200):
            signals.append({"quote": _str(s.get("quote"), 200), "why": _str(s.get("why"), 250)})
    recs = []
    for r in _list(data.get("recommendations"), 3):
        if isinstance(r, dict) and _str(r.get("title"), 80):
            recs.append({
                "title": _str(r.get("title"), 80),
                "detail": _str(r.get("detail"), 400),
                "duration": _str(r.get("duration"), 30),
            })
    tasks = []
    for t in _list(data.get("suggested_tasks"), 6):
        if isinstance(t, dict) and _str(t.get("title"), 120):
            tasks.append({
                "title": _str(t.get("title"), 120),
                "priority": _choice(t.get("priority"), PRIORITIES, "medium"),
                "minutes": _int(t.get("minutes"), 5, 240, 30),
            })
    summary = _str(data.get("summary"), 600)
    next_step = _str(data.get("next_step"), 300)
    if not summary or not recs or not next_step:
        raise ValidationError("AI response is missing required fields.")
    return {
        "language": _str(data.get("language"), 20) or "unknown",
        "summary": summary,
        "emotions": emotions,
        "stress_signals": signals,
        "challenges": [_str(c, 200) for c in _list(data.get("challenges"), 5) if _str(c, 200)],
        "recommendations": recs,
        "next_step": next_step,
        "suggested_tasks": tasks,
        "support_note": _str(data.get("support_note"), 500) or None,
        "crisis": bool(data.get("crisis") is True),
    }


def validate_plan(data: dict, req: dict) -> dict:
    if not isinstance(data, dict):
        raise ValidationError("AI plan is not an object.")
    task_ids = {t["id"] for t in req["tasks"]}
    blocks = []
    for b in _list(data.get("blocks"), 30):
        if not isinstance(b, dict):
            continue
        btype = _choice(b.get("type"), BLOCK_TYPES, "task")
        title = _str(b.get("title"), 120)
        if not title:
            continue
        task_id = _str(b.get("task_id"), 40)
        task_id = task_id if btype == "task" and task_id in task_ids else None
        blocks.append({
            "type": btype,
            "title": title,
            "minutes": _int(b.get("minutes"), 3, 120, 25),
            "task_id": task_id,
            "note": _str(b.get("note"), 200),
        })
    if not any(b["type"] == "task" for b in blocks):
        raise ValidationError("AI plan contains no task blocks.")
    postponed = []
    for p in _list(data.get("postponed"), 15):
        if isinstance(p, dict) and _str(p.get("task_id"), 40) in task_ids:
            postponed.append({"task_id": _str(p.get("task_id"), 40), "reason": _str(p.get("reason"), 200)})
    return {
        "overview": _str(data.get("overview"), 500),
        "overload": bool(data.get("overload") is True),
        "overload_advice": _str(data.get("overload_advice"), 400),
        "blocks": blocks,
        "postponed": postponed,
        "tips": [_str(t, 200) for t in _list(data.get("tips"), 4) if _str(t, 200)],
    }


def add_times(plan: dict, start_time: str) -> dict:
    """Ordinary application logic: compute clock times for each block."""
    current = datetime.strptime(start_time, "%H:%M")
    for i, block in enumerate(plan["blocks"]):
        end = current + timedelta(minutes=block["minutes"])
        block["start"] = current.strftime("%H:%M")
        block["end"] = end.strftime("%H:%M")
        block["id"] = f"b{i + 1}"
        current = end
    plan["total_minutes"] = sum(b["minutes"] for b in plan["blocks"])
    return plan


# ---------------------------------------------------------------- school / calendar input

TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
PROFILES = ("lycee", "universite", "autre")
NOTIF_LANGS = ("fr", "en", "tn")
ENTRY_KINDS = ("course", "club", "activity", "break")
EXCEPTION_KINDS = ("cancel", "move", "day_off")
EXAM_STATUS = ("upcoming", "done")
SESSION_STATUS = ("planned", "done", "missed")

DEFAULT_SETTINGS = {
    "onboarded": False, "profile": "autre", "institution": "", "subjects": [],
    "ui_lang": "fr", "notif_lang": "fr",
    "notifications_enabled": True, "day_end_enabled": True, "wellness_reminder": False,
    "session_reminders": True, "exam_reminders": True,
    "reminder_days": [0, 1, 2, 3, 4, 5],
    "home_time": "", "commute_minutes": 30, "rest_minutes": 45, "checkin_time": "",
    "quiet_start": "22:00", "quiet_end": "07:30",
    "push_enabled": False, "push_private": True,
    "study_start": "09:00", "study_end": "21:30", "daily_study_minutes": 120,
    "session_minutes": 45, "break_minutes": 10,
}
_BOOL_SETTINGS = ("onboarded", "notifications_enabled", "day_end_enabled", "wellness_reminder",
                  "session_reminders", "exam_reminders", "push_enabled", "push_private")
_INT_SETTINGS = {"commute_minutes": (0, 180), "rest_minutes": (0, 240), "daily_study_minutes": (30, 360),
                 "session_minutes": (25, 90), "break_minutes": (5, 30)}


def _body(payload) -> dict:
    if not isinstance(payload, dict):
        raise ValidationError("Invalid request body.")
    return payload


def parse_time(value, field: str, required: bool = True) -> str:
    value = _str(value, 5)
    if not value and not required:
        return ""
    if not TIME_RE.match(value):
        raise ValidationError(f"Invalid time for {field} (expected HH:MM).")
    return value


def parse_date(value, field: str, required: bool = True) -> str | None:
    value = _str(value, 10)
    if not value and not required:
        return None
    try:
        if not DATE_RE.match(value):
            raise ValueError
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        raise ValidationError(f"Invalid date for {field} (expected YYYY-MM-DD).") from None
    return value


def _mins(hm: str) -> int:
    return int(hm[:2]) * 60 + int(hm[3:])


def parse_settings(payload, current: dict) -> dict:
    """Merge known, validated keys into the current settings."""
    payload = _body(payload)
    out = {**DEFAULT_SETTINGS, **current}
    for key in _BOOL_SETTINGS:
        if key in payload:
            out[key] = bool(payload[key])
    for key, (lo, hi) in _INT_SETTINGS.items():
        if key in payload:
            out[key] = _int(payload[key], lo, hi, out[key])
    if "profile" in payload:
        out["profile"] = _choice(payload["profile"], PROFILES, out["profile"])
    if "notif_lang" in payload:
        out["notif_lang"] = _choice(payload["notif_lang"], NOTIF_LANGS, out["notif_lang"])
    if "ui_lang" in payload:
        out["ui_lang"] = _choice(payload["ui_lang"], ("en", "fr"), out["ui_lang"])
    if "institution" in payload:
        out["institution"] = _str(payload["institution"], 80)
    if "subjects" in payload:
        subs = payload["subjects"]
        if isinstance(subs, str):
            subs = re.split(r"[,;\n]+", subs)
        out["subjects"] = [s for s in (_str(x, 40) for x in _list(subs, 15)) if s]
    if "reminder_days" in payload:
        days = payload["reminder_days"]
        out["reminder_days"] = sorted({int(d) for d in _list(days, 7) if str(d).isdigit() and 0 <= int(d) <= 6})
    for key in ("home_time", "checkin_time"):
        if key in payload:
            out[key] = parse_time(payload[key], key, required=False)
    for key in ("quiet_start", "quiet_end", "study_start", "study_end"):
        if key in payload:
            out[key] = parse_time(payload[key], key, required=key.startswith("study"))
    if _mins(out["study_end"]) <= _mins(out["study_start"]):
        raise ValidationError("Study end time must be after the start time.")
    if _mins(out["study_end"]) > 23 * 60 + 30:
        raise ValidationError("Study end time must be 23:30 at the latest (sleep matters).")
    return out


def parse_entry(payload) -> dict:
    payload = _body(payload)
    title = _str(payload.get("title"), 80)
    if not title:
        raise ValidationError("Please give this class or activity a name.")
    start = parse_time(payload.get("start"), "start")
    end = parse_time(payload.get("end"), "end")
    if _mins(end) <= _mins(start):
        raise ValidationError("End time must be after start time.")
    recurring = bool(payload.get("recurring", True))
    date = None
    if recurring:
        day = _int(payload.get("day"), -1, 6, -1)
        if day < 0:
            raise ValidationError("Please choose a day of the week.")
    else:
        date = parse_date(payload.get("date"), "date")
        day = datetime.strptime(date, "%Y-%m-%d").weekday()
    return {"kind": _choice(payload.get("kind"), ENTRY_KINDS, "course"), "title": title, "day": day,
            "start": start, "end": end, "location": _str(payload.get("location"), 80),
            "recurring": recurring, "date": date}


def parse_exception(payload) -> dict:
    payload = _body(payload)
    kind = _choice(payload.get("kind"), EXCEPTION_KINDS, "")
    if not kind:
        raise ValidationError("Unknown change type.")
    out = {"kind": kind, "date": parse_date(payload.get("date"), "date"), "entry_id": None,
           "start": None, "end": None, "note": _str(payload.get("note"), 120)}
    if kind in ("cancel", "move"):
        out["entry_id"] = _str(payload.get("entry_id"), 40)
        if not out["entry_id"]:
            raise ValidationError("Which class is concerned?")
    if kind == "move":
        out["start"] = parse_time(payload.get("start"), "start")
        out["end"] = parse_time(payload.get("end"), "end")
        if _mins(out["end"]) <= _mins(out["start"]):
            raise ValidationError("End time must be after start time.")
    return out


def parse_exam(payload) -> dict:
    payload = _body(payload)
    subject = _str(payload.get("subject"), 80)
    if not subject:
        raise ValidationError("Please enter the subject of the exam.")
    return {
        "subject": subject,
        "title": _str(payload.get("title"), 120),
        "chapters": _str(payload.get("chapters"), 600),
        "difficult": _str(payload.get("difficult"), 300),
        "date": parse_date(payload.get("date"), "date", required=False),
        "time": parse_time(payload.get("time"), "time", required=False) or None,
        "priority": _choice(payload.get("priority"), PRIORITIES, "medium"),
        "preparation": _int(payload.get("preparation"), 0, 100, 0),
        "minutes_per_day": _int(payload.get("minutes_per_day"), 0, 360, 0),
        "status": _choice(payload.get("status"), EXAM_STATUS, "upcoming"),
    }


def parse_session_patch(payload) -> dict:
    payload = _body(payload)
    out = {"force": bool(payload.get("force"))}
    if "status" in payload:
        out["status"] = _choice(payload.get("status"), SESSION_STATUS, "")
        if not out["status"]:
            raise ValidationError("Unknown session status.")
    if "date" in payload or "start" in payload:
        out["date"] = parse_date(payload.get("date"), "date")
        out["start"] = parse_time(payload.get("start"), "start")
        out["minutes"] = _int(payload.get("minutes"), 15, 180, 45)
        if _mins(out["start"]) + out["minutes"] > 24 * 60 - 1:
            raise ValidationError("A session must end before midnight.")
    if len(out) == 1:
        raise ValidationError("Nothing to change.")
    return out


def parse_subscription(payload) -> dict:
    payload = _body(payload)
    sub = payload.get("subscription")
    if not isinstance(sub, dict) or not isinstance(sub.get("keys"), dict):
        raise ValidationError("Invalid push subscription.")
    endpoint = sub.get("endpoint") if isinstance(sub.get("endpoint"), str) else ""
    p256dh, auth = sub["keys"].get("p256dh"), sub["keys"].get("auth")
    if not endpoint.startswith("https://") or len(endpoint) > 1000:
        raise ValidationError("Invalid push endpoint.")
    if not all(isinstance(k, str) and 8 <= len(k) <= 200 for k in (p256dh, auth)):
        raise ValidationError("Invalid push keys.")
    return {"endpoint": endpoint, "p256dh": p256dh, "auth": auth}


def validate_coach(data: dict) -> dict:
    if not isinstance(data, dict):
        raise ValidationError("AI coach output is not an object.")
    message = _str(data.get("message"), 600)
    steps = []
    for s in _list(data.get("steps"), 8):
        if isinstance(s, dict) and _str(s.get("title"), 160):
            steps.append({"title": _str(s.get("title"), 160), "minutes": _int(s.get("minutes"), 5, 120, 25)})
    if not message or not steps:
        raise ValidationError("AI coach output is missing fields.")
    return {"message": message, "steps": steps, "tip": _str(data.get("tip"), 300)}
