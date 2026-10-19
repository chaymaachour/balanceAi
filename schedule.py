"""Timetable logic: ready-made templates, effective day view (cancellations,
moved classes, days off), conflict detection, free time slots and the
end-of-day reminder time. Pure functions with no database access so that the
rules are easy to test."""
from __future__ import annotations

from datetime import date as Date, datetime, timedelta
from zoneinfo import ZoneInfo

import config

TZ = ZoneInfo(config.TIMEZONE)
KINDS = ("course", "club", "activity", "break")
AWAY_KINDS = ("course", "club", "activity")  # things that keep you away from home
MIN_SLOT = 25
DAY_NAMES = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def now() -> datetime:
    return datetime.now(TZ)


def to_min(hm: str) -> int:
    h, m = hm.split(":")
    return int(h) * 60 + int(m)


def to_hm(minutes: int) -> str:
    minutes = max(0, min(int(minutes), 24 * 60 - 1))
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def overlaps(a0: int, a1: int, b0: int, b1: int) -> bool:
    return a0 < b1 and b0 < a1


def in_quiet_hours(minute: int, settings: dict) -> bool:
    qs, qe = settings.get("quiet_start"), settings.get("quiet_end")
    if not qs or not qe:
        return False
    s, e = to_min(qs), to_min(qe)
    if s == e:
        return False
    return s <= minute < e if s < e else (minute >= s or minute < e)


# ------------------------------------------------------------------ templates
# Typical Tunisian timetables, only used as an editable starting point.
LYCEE_SUBJECTS = ["Mathématiques", "Français", "Physique", "Arabe", "Anglais", "Sciences (SVT)",
                  "Philosophie", "Informatique", "Histoire-Géo", "Éducation physique"]
LYCEE_SLOTS = [
    (0, "08:00", "10:00", 0), (0, "10:00", "12:00", 1), (0, "14:00", "16:00", 2),
    (1, "08:00", "10:00", 3), (1, "10:00", "12:00", 4), (1, "14:00", "16:00", 5),
    (2, "08:00", "10:00", 0), (2, "10:00", "12:00", 6),
    (3, "08:00", "10:00", 2), (3, "10:00", "12:00", 7), (3, "14:00", "16:00", 9),
    (4, "08:00", "10:00", 3), (4, "10:00", "12:00", 0), (4, "14:00", "16:00", 8),
    (5, "08:00", "10:00", 4), (5, "10:00", "12:00", 5),
]
UNI_SUBJECTS = ["Module 1", "Module 2", "Module 3", "Module 4", "Anglais"]
UNI_SLOTS = [  # Tunisian university "séances" of 1h30
    (0, "08:30", "10:00", 0, "Cours"), (0, "10:10", "11:40", 0, "TD"), (0, "14:00", "15:30", 1, "Cours"),
    (1, "08:30", "10:00", 2, "Cours"), (1, "10:10", "11:40", 1, "TP"), (1, "11:50", "13:20", 4, ""),
    (2, "08:30", "10:00", 3, "Cours"), (2, "10:10", "11:40", 2, "TD"),
    (3, "10:10", "11:40", 0, "Cours"), (3, "14:00", "15:30", 3, "TP"), (3, "15:40", "17:10", 1, "TD"),
    (4, "08:30", "10:00", 1, "TD"), (4, "10:10", "11:40", 2, "Cours"),
]


def template_entries(profile: str, subjects: list[str] | None = None) -> list[dict]:
    """Return an editable weekly template. The user's own subjects replace the
    generic names when provided."""
    out = []
    if profile == "lycee":
        names = subjects or LYCEE_SUBJECTS
        for day, start, end, idx in LYCEE_SLOTS:
            out.append({"kind": "course", "title": names[idx % len(names)], "day": day, "start": start, "end": end})
    elif profile == "universite":
        names = subjects or UNI_SUBJECTS
        for day, start, end, idx, prefix in UNI_SLOTS:
            name = names[idx % len(names)]
            out.append({"kind": "course", "title": f"{prefix} — {name}" if prefix else name,
                        "day": day, "start": start, "end": end})
    for e in out:
        e.update(location="", recurring=True, date=None)
    return out


# ------------------------------------------------------------------ day view
def effective_day(entries: list[dict], exceptions: list[dict], d: Date) -> list[dict]:
    """Entries that apply on date d, with cancellations / moves / days off applied."""
    ds, wd = d.isoformat(), d.weekday()
    day_off = any(x["kind"] == "day_off" and x["date"] == ds for x in exceptions)
    out = []
    for e in entries:
        if e["recurring"]:
            if e["day"] != wd:
                continue
        elif e.get("date") != ds:
            continue
        item = {**e, "cancelled": False, "moved": False, "exception_id": None}
        if day_off and e["kind"] == "course":
            item["cancelled"] = True
        for x in exceptions:
            if x["date"] == ds and x.get("entry_id") == e["id"]:
                item["exception_id"] = x["id"]
                if x["kind"] == "cancel":
                    item["cancelled"] = True
                elif x["kind"] == "move":
                    item.update(start=x["start"], end=x["end"], moved=True)
        out.append(item)
    out.sort(key=lambda i: i["start"])
    return out


def is_day_off(exceptions: list[dict], d: Date) -> bool:
    return any(x["kind"] == "day_off" and x["date"] == d.isoformat() for x in exceptions)


def _same_day(a: dict, b: dict) -> bool:
    if a["recurring"] and b["recurring"]:
        return a["day"] == b["day"]
    if a["recurring"]:
        return a["day"] == Date.fromisoformat(b["date"]).weekday()
    if b["recurring"]:
        return b["day"] == Date.fromisoformat(a["date"]).weekday()
    return a["date"] == b["date"]


def find_conflicts(entries: list[dict], candidate: dict, ignore_id: str | None = None) -> list[dict]:
    """Entries overlapping the candidate on the same day (time conflicts)."""
    c0, c1 = to_min(candidate["start"]), to_min(candidate["end"])
    return [e for e in entries
            if e["id"] != ignore_id and _same_day(e, candidate)
            and overlaps(c0, c1, to_min(e["start"]), to_min(e["end"]))]


# ------------------------------------------------------------------ outings / free time
def _outings(day_items: list[dict], settings: dict) -> list[tuple[int, int]]:
    """Group away-from-home activities into outings (you do not go home for a short gap)."""
    commute = int(settings.get("commute_minutes", 30))
    items = sorted((to_min(i["start"]), to_min(i["end"])) for i in day_items
                   if not i["cancelled"] and i["kind"] in AWAY_KINDS)
    groups: list[list[int]] = []
    for s, e in items:
        if groups and s - groups[-1][1] < 2 * commute + 60:
            groups[-1][1] = max(groups[-1][1], e)
        else:
            groups.append([s, e])
    return [(s, e) for s, e in groups]


def arrival_home(settings: dict, day_items: list[dict]) -> int | None:
    """Estimated time the user is back home after the last outing of the day."""
    outings = _outings(day_items, settings)
    if not outings:
        return None
    last_start, last_end = outings[-1]
    arrival = last_end + int(settings.get("commute_minutes", 30))
    home = settings.get("home_time")
    if home and to_min(home) > last_start:
        arrival = max(arrival, to_min(home))
    return arrival


def free_slots(settings: dict, day_items: list[dict], extra_busy=(), not_before: int | None = None) -> list[tuple[int, int]]:
    """Free study slots inside the study window, after travel and rest time."""
    ws, we = to_min(settings["study_start"]), to_min(settings["study_end"])
    commute = int(settings.get("commute_minutes", 30))
    rest = int(settings.get("rest_minutes", 45))
    busy = [(to_min(i["start"]), to_min(i["end"])) for i in day_items if not i["cancelled"]]
    outings = _outings(day_items, settings)
    for idx, (s, e) in enumerate(outings):
        end = e + commute + rest
        if idx == len(outings) - 1:
            end = arrival_home(settings, day_items) + rest
        busy.append((s - commute, end))
    busy.extend(extra_busy)
    if not_before is not None:
        busy.append((0, not_before))
    busy.sort()
    slots, cursor = [], ws
    for s, e in busy:
        if e <= cursor:
            continue
        if s > cursor:
            slots.append((cursor, min(s, we)))
        cursor = max(cursor, e)
        if cursor >= we:
            break
    if cursor < we:
        slots.append((cursor, we))
    return [(s, e) for s, e in slots if e - s >= MIN_SLOT]


# ------------------------------------------------------------------ end-of-day reminder
def day_end_reminder(settings: dict, day_items: list[dict], d: Date) -> dict:
    """When to send the end-of-day check-in reminder for date d.

    Returns {"at": minutes-of-day or None, "reason": str, "arrival": ...}.
    Rule: last class/activity end + commute (or usual home time) + rest delay,
    never before the preferred check-in time, never during quiet hours.
    """
    res = {"at": None, "reason": "", "arrival": None}
    if not settings.get("notifications_enabled", True) or not settings.get("day_end_enabled", True):
        res["reason"] = "disabled"
        return res
    if d.weekday() not in settings.get("reminder_days", []):
        res["reason"] = "day_not_allowed"
        return res
    arrival = arrival_home(settings, day_items)
    preferred = to_min(settings["checkin_time"]) if settings.get("checkin_time") else None
    if arrival is None:
        if not settings.get("wellness_reminder"):
            res["reason"] = "no_classes"
            return res
        at = preferred if preferred is not None else 19 * 60
        res["reason"] = "wellness"
    else:
        res["arrival"] = arrival
        at = arrival + int(settings.get("rest_minutes", 45))
        if preferred is not None:
            at = max(at, preferred)
        res["reason"] = "after_classes"
    if at >= 24 * 60:
        res.update(at=None, reason="too_late")
        return res
    if in_quiet_hours(at, settings):
        res.update(at=None, reason="quiet_hours")
        return res
    res["at"] = at
    return res


def week_dates(start: Date) -> list[Date]:
    monday = start - timedelta(days=start.weekday())
    return [monday + timedelta(days=i) for i in range(7)]
