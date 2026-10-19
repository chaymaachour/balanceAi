"""Deterministic revision planner.

Places revision sessions only inside genuinely free slots (after classes,
travel and rest; inside the study window that protects sleep), prioritising
exams by proximity, priority, difficulty and preparation. The AI never decides
times: this module guarantees there are no overlaps, and it is covered by tests.
"""
from __future__ import annotations

import math
import re
from datetime import date as Date, timedelta

import schedule as sch

PRIORITY_WEIGHT = {"high": 1.5, "medium": 1.0, "low": 0.7}
BASE_MINUTES = {"high": 600, "medium": 420, "low": 240}
NO_DATE_HORIZON = 14
MAX_HORIZON = 60


def split_list(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"[,;\n]+", text or "") if p.strip()]


def needed_minutes(exam: dict) -> int:
    """Total revision time an exam needs, from priority, difficult chapters and preparation."""
    base = BASE_MINUTES.get(exam["priority"], 420) + 60 * len(split_list(exam.get("difficult", "")))
    need = base * (100 - max(0, min(100, exam.get("preparation", 0)))) / 100
    return int(math.ceil(need / 15) * 15)


def exam_deadline(exam: dict, today: Date) -> Date:
    return Date.fromisoformat(exam["date"]) if exam.get("date") else today + timedelta(days=NO_DATE_HORIZON)


def active_exams(exams: list[dict], today: Date) -> list[dict]:
    return [e for e in exams if e["status"] == "upcoming" and (not e.get("date") or Date.fromisoformat(e["date"]) > today)]


def progress(exam: dict, sessions: list[dict]) -> dict:
    mine = [s for s in sessions if s["exam_id"] == exam["id"]]
    done = sum(s["minutes"] for s in mine if s["status"] == "done")
    planned = sum(s["minutes"] for s in mine if s["status"] == "planned")
    need = needed_minutes(exam)
    target = max(need, done) or 1
    return {"exam_id": exam["id"], "needed": need, "done": done, "planned": planned,
            "missed": sum(1 for s in mine if s["status"] == "missed"),
            "percent": min(100, round(100 * done / target)) if need else 100}


def plan(exams, entries, exceptions, settings, sessions, today: Date, now_min: int | None = None) -> dict:
    """Build new planned sessions. `sessions` are existing sessions to keep
    (done, missed, and locked planned ones). Returns new sessions + shortfalls."""
    active = active_exams(exams, today)
    keep = [s for s in sessions if s["status"] == "done" or (s["status"] == "planned" and s.get("locked"))]
    remaining, chapters, chap_idx, deadline = {}, {}, {}, {}
    for e in active:
        used = sum(s["minutes"] for s in keep if s["exam_id"] == e["id"])
        remaining[e["id"]] = max(0, needed_minutes(e) - used)
        chapters[e["id"]] = split_list(e.get("difficult", "")) + [c for c in split_list(e.get("chapters", ""))
                                                                  if c not in split_list(e.get("difficult", ""))]
        chap_idx[e["id"]] = 0
        deadline[e["id"]] = exam_deadline(e, today)
    by_id = {e["id"]: e for e in active}
    if not active:
        return {"sessions": [], "shortfalls": [], "exams": 0}

    horizon_end = min(max(deadline.values()), today + timedelta(days=MAX_HORIZON))
    session_len = int(settings["session_minutes"])
    brk = int(settings["break_minutes"])
    new = []
    d = today
    while d < horizon_end:
        items = sch.effective_day(entries, exceptions, d)
        kept_today = [s for s in keep if s["date"] == d.isoformat()]
        missed_today = [s for s in sessions if s["status"] == "missed" and s["date"] == d.isoformat()]
        extra = [(sch.to_min(s["start"]), sch.to_min(s["end"]) + brk) for s in kept_today + missed_today]
        nb = None
        if d == today and now_min is not None:
            nb = int(math.ceil((now_min + 10) / 5) * 5)
        capacity = int(settings["daily_study_minutes"]) - sum(s["minutes"] for s in kept_today)
        per_exam_today: dict[str, int] = {}
        per_exam_minutes: dict[str, int] = {}
        for s0, s1 in sch.free_slots(settings, items, extra, nb):
            cursor = s0
            while capacity >= sch.MIN_SLOT and s1 - cursor >= sch.MIN_SLOT:
                best, best_score = None, -1.0
                for eid, rem in remaining.items():
                    if rem <= 0 or deadline[eid] <= d:
                        continue
                    days_left = (deadline[eid] - d).days
                    cap = 3 if days_left <= 3 else 2
                    if per_exam_today.get(eid, 0) >= cap:
                        continue
                    daily_cap = by_id[eid].get("minutes_per_day") or 0
                    if daily_cap and per_exam_minutes.get(eid, 0) >= daily_cap:
                        continue
                    score = PRIORITY_WEIGHT.get(by_id[eid]["priority"], 1.0) * rem / days_left
                    if score > best_score or (score == best_score and deadline[eid] < deadline[best]):
                        best, best_score = eid, score
                if best is None:
                    break
                length = min(session_len, capacity, s1 - cursor, max(sch.MIN_SLOT, remaining[best]))
                daily_cap = by_id[best].get("minutes_per_day") or 0
                if daily_cap:
                    length = min(length, daily_cap - per_exam_minutes.get(best, 0))
                if length < sch.MIN_SLOT:
                    per_exam_today[best] = 99
                    continue
                chs = chapters[best]
                focus = chs[chap_idx[best] % len(chs)] if chs else ""
                chap_idx[best] += 1
                new.append({"exam_id": best, "date": d.isoformat(), "start": sch.to_hm(cursor),
                            "end": sch.to_hm(cursor + length), "minutes": length, "focus": focus,
                            "status": "planned", "locked": 0})
                remaining[best] = max(0, remaining[best] - length)
                capacity -= length
                per_exam_today[best] = per_exam_today.get(best, 0) + 1
                per_exam_minutes[best] = per_exam_minutes.get(best, 0) + length
                cursor += length + brk
        d += timedelta(days=1)

    shortfalls = [{"exam_id": eid, "missing_minutes": rem} for eid, rem in remaining.items() if rem > 0]
    return {"sessions": new, "shortfalls": shortfalls, "exams": len(active)}


def session_conflicts(entries, exceptions, sessions, candidate: dict, ignore_id: str | None = None) -> list[str]:
    """Reasons why a (moved) session would overlap classes or other sessions."""
    d = Date.fromisoformat(candidate["date"])
    c0, c1 = sch.to_min(candidate["start"]), sch.to_min(candidate["end"])
    reasons = [f'{i["title"]} {i["start"]}-{i["end"]}' for i in sch.effective_day(entries, exceptions, d)
               if not i["cancelled"] and sch.overlaps(c0, c1, sch.to_min(i["start"]), sch.to_min(i["end"]))]
    reasons += [f'session {s["start"]}-{s["end"]}' for s in sessions
                if s["id"] != ignore_id and s["date"] == candidate["date"] and s["status"] != "missed"
                and sch.overlaps(c0, c1, sch.to_min(s["start"]), sch.to_min(s["end"]))]
    return reasons
