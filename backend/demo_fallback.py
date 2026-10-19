"""DEMO MODE - simple local rules used ONLY when no AI API key is configured
or when the AI provider fails. This is NOT artificial intelligence: it uses a
small keyword list and a fixed scheduling algorithm, and the UI labels it as such.
"""
from __future__ import annotations

import re

PRIORITY_RANK = {"high": 0, "medium": 1, "low": 2}

# keyword -> (emotion key, challenge key)
_LEXICON = {
    "exam": ("pressure", "exams"), "examen": ("pressure", "exams"), "partiel": ("pressure", "exams"),
    "imti7an": ("pressure", "exams"), "امتحان": ("pressure", "exams"), "revision": ("pressure", "exams"),
    "pfe": ("pressure", "thesis"), "thesis": ("pressure", "thesis"), "mémoire": ("pressure", "thesis"),
    "memoire": ("pressure", "thesis"), "rapport": ("pressure", "thesis"), "soutenance": ("worry", "thesis"),
    "job": ("worry", "career"), "emploi": ("worry", "career"), "travail": ("pressure", "work"),
    "khedma": ("worry", "career"), "خدمة": ("worry", "career"), "interview": ("worry", "career"),
    "entretien": ("worry", "career"), "cv": ("worry", "career"), "chômage": ("worry", "career"),
    "boss": ("pressure", "work"), "manager": ("pressure", "work"), "deadline": ("pressure", "deadline"),
    "délai": ("pressure", "deadline"), "family": ("tension", "family"), "famille": ("tension", "family"),
    "parents": ("tension", "family"), "3ayla": ("tension", "family"), "عائلة": ("tension", "family"),
    "tired": ("fatigue", "sleep"), "fatigué": ("fatigue", "sleep"), "fatiguée": ("fatigue", "sleep"),
    "ta3ban": ("fatigue", "sleep"), "ta3bana": ("fatigue", "sleep"), "تعبان": ("fatigue", "sleep"),
    "sleep": ("fatigue", "sleep"), "dormir": ("fatigue", "sleep"), "sommeil": ("fatigue", "sleep"),
    "alone": ("loneliness", None), "seule": ("loneliness", None), "wa7di": ("loneliness", None),
    "stress": ("pressure", None), "stressé": ("pressure", None), "stressée": ("pressure", None),
    "mestressi": ("pressure", None), "mestressia": ("pressure", None), "overwhelmed": ("overwhelm", None),
    "débordée": ("overwhelm", None), "débordé": ("overwhelm", None), "trop": ("overwhelm", None),
    "too much": ("overwhelm", None), "barcha": ("overwhelm", None), "angry": ("frustration", None),
    "énervée": ("frustration", None), "m9alla9": ("frustration", None), "m9al9a": ("frustration", None),
}

_MOOD_EMOTION = {
    "happy": "joy", "calm": "calm", "okay": "neutral", "stressed": "pressure",
    "overwhelmed": "overwhelm", "tired": "fatigue", "frustrated": "frustration",
}

_T = {
    "en": {
        "emotions": {
            "joy": "Joy", "calm": "Calm", "neutral": "Mixed / okay", "pressure": "Pressure",
            "overwhelm": "Overwhelm", "fatigue": "Tiredness", "frustration": "Frustration",
            "worry": "Worry", "tension": "Tension", "loneliness": "Loneliness",
        },
        "challenges": {
            "exams": "Upcoming exams or revision", "thesis": "Final-year project / thesis work",
            "career": "Job search and career uncertainty", "work": "Workplace pressure",
            "deadline": "A close deadline", "family": "Family expectations or responsibilities",
            "sleep": "Low energy or lack of sleep",
        },
        "from_mood": "You selected this mood in your check-in.",
        "keyword": "The word \"{w}\" appears in your message.",
        "keyword_why": "This word is in the demo keyword list linked to {e}.",
        "summary": "Thank you for checking in. You said you feel {mood}{ctx}. "
                   "This is a simple demo summary - connect an AI key for a personalised reading of your message.",
        "ctx": ", mostly around {c}",
        "recs": [
            {"title": "Write down the top 3", "detail": "List everything on your mind, then circle only the 3 things that truly matter today.", "duration": "5 min"},
            {"title": "One 25-minute focus session", "detail": "Pick the smallest piece of your most important task and work on it for 25 minutes, phone away.", "duration": "25 min"},
            {"title": "Breathing break", "detail": "Try the box-breathing exercise in the Relax page to calm your body before continuing.", "duration": "3 min"},
        ],
        "rec_rest": {"title": "Protect your rest", "detail": "Tiredness makes everything feel heavier. Plan a real break and a reasonable bedtime tonight.", "duration": "tonight"},
        "next": "Drink a glass of water, then write your top 3 priorities on a piece of paper.",
        "support": "If this stress lasts for weeks or feels too heavy, talking to a trusted person, a doctor or your university counselling service can really help.",
        "plan_overview": "Demo plan built with a fixed local algorithm: important tasks first, short sessions and regular breaks.",
        "overload_advice": "Your tasks don't fit in the time available. That's okay - the less urgent ones have been moved to later. Consider asking for help or an extension.",
        "postpone_reason": "Doesn't fit in today's available time - move it to tomorrow.",
        "postpone_partial": "Started today - the remaining {m} min can wait until tomorrow.",
        "break": "Break - stand up, stretch, drink water", "habit_mid": "Short walk or fresh air",
        "habit_end": "Wind down - a calm moment just for you", "part": "part {i}/{n}",
        "tips": ["Start with the first block only - you don't need to see the whole day at once.",
                 "Silence notifications during focus sessions."],
        "tip_stress": "Your stress level is high, so sessions are shorter. Doing less, well, is still progress.",
    },
    "fr": {
        "emotions": {
            "joy": "Joie", "calm": "Calme", "neutral": "Mitigé / ça va", "pressure": "Pression",
            "overwhelm": "Débordement", "fatigue": "Fatigue", "frustration": "Frustration",
            "worry": "Inquiétude", "tension": "Tension", "loneliness": "Solitude",
        },
        "challenges": {
            "exams": "Examens ou révisions à venir", "thesis": "Projet de fin d'études / mémoire",
            "career": "Recherche d'emploi et incertitude professionnelle", "work": "Pression au travail",
            "deadline": "Une échéance proche", "family": "Attentes ou responsabilités familiales",
            "sleep": "Manque d'énergie ou de sommeil",
        },
        "from_mood": "Tu as choisi cette humeur lors de ton check-in.",
        "keyword": "Le mot « {w} » apparaît dans ton message.",
        "keyword_why": "Ce mot fait partie de la liste de mots-clés du mode démo, associée à : {e}.",
        "summary": "Merci d'avoir pris ce moment. Tu te sens {mood}{ctx}. "
                   "Ceci est un résumé de démonstration - configure une clé IA pour une lecture personnalisée de ton message.",
        "ctx": ", surtout à cause de : {c}",
        "recs": [
            {"title": "Note tes 3 priorités", "detail": "Écris tout ce qui te préoccupe, puis entoure seulement les 3 choses vraiment importantes aujourd'hui.", "duration": "5 min"},
            {"title": "Une session de 25 minutes", "detail": "Choisis la plus petite partie de ta tâche la plus importante et travaille 25 minutes, téléphone loin de toi.", "duration": "25 min"},
            {"title": "Pause respiration", "detail": "Essaie la respiration carrée dans la page Détente pour apaiser ton corps avant de continuer.", "duration": "3 min"},
        ],
        "rec_rest": {"title": "Protège ton repos", "detail": "La fatigue rend tout plus lourd. Prévois une vraie pause et une heure de coucher raisonnable ce soir.", "duration": "ce soir"},
        "next": "Bois un verre d'eau, puis écris tes 3 priorités sur une feuille.",
        "support": "Si ce stress dure depuis des semaines ou te semble trop lourd, en parler à une personne de confiance, à un médecin ou au service d'écoute de ton université peut vraiment aider.",
        "plan_overview": "Plan de démonstration créé par un algorithme local fixe : tâches importantes d'abord, sessions courtes et pauses régulières.",
        "overload_advice": "Tes tâches ne tiennent pas dans le temps disponible. Ce n'est pas grave - les moins urgentes ont été reportées. Pense à demander de l'aide ou un délai.",
        "postpone_reason": "Ne tient pas dans le temps disponible aujourd'hui - à reporter à demain.",
        "postpone_partial": "Commencée aujourd'hui - les {m} min restantes peuvent attendre demain.",
        "break": "Pause - lève-toi, étire-toi, bois de l'eau", "habit_mid": "Petite marche ou air frais",
        "habit_end": "Moment calme rien que pour toi", "part": "partie {i}/{n}",
        "tips": ["Commence seulement par le premier bloc - pas besoin de voir toute la journée d'un coup.",
                 "Coupe les notifications pendant les sessions de concentration."],
        "tip_stress": "Ton niveau de stress est élevé, donc les sessions sont plus courtes. Faire moins, mais bien, c'est déjà avancer.",
    },
}

_MOOD_LABEL = {
    "en": {"happy": "happy", "calm": "calm", "okay": "okay", "stressed": "stressed",
           "overwhelmed": "overwhelmed", "tired": "tired", "frustrated": "frustrated"},
    "fr": {"happy": "heureuse/heureux", "calm": "calme", "okay": "ça va", "stressed": "stressé·e",
           "overwhelmed": "débordé·e", "tired": "fatigué·e", "frustrated": "frustré·e"},
}
_CTX_LABEL = {
    "en": {"studies": "studies", "work": "work", "career": "career", "family": "family",
           "personal": "personal life", "other": "other things"},
    "fr": {"studies": "les études", "work": "le travail", "career": "la carrière", "family": "la famille",
           "personal": "la vie personnelle", "other": "d'autres choses"},
}


def demo_analysis(checkin: dict) -> dict:
    lang = checkin["lang"]
    t = _T[lang]
    text = checkin["text"].lower()
    emotions, signals, challenges = {}, [], []

    base = _MOOD_EMOTION[checkin["mood"]]
    emotions[base] = {"name": t["emotions"][base], "confidence": "medium", "evidence": t["from_mood"]}
    for word, (emo, chal) in _LEXICON.items():
        if re.search(r"(?<!\w)" + re.escape(word) + r"(?!\w)", text):
            if emo not in emotions and len(emotions) < 4:
                emotions[emo] = {"name": t["emotions"][emo], "confidence": "low",
                                 "evidence": t["keyword"].format(w=word)}
            if len(signals) < 3:
                signals.append({"quote": word, "why": t["keyword_why"].format(e=t["emotions"][emo])})
            if chal and t["challenges"][chal] not in challenges:
                challenges.append(t["challenges"][chal])

    ctx = ", ".join(_CTX_LABEL[lang][c] for c in checkin["contexts"])
    recs = list(t["recs"])
    if checkin["mood"] == "tired" or "fatigue" in emotions:
        recs = [recs[0], t["rec_rest"], recs[2]]
    heavy = checkin["mood"] in ("overwhelmed", "stressed", "frustrated")
    return {
        "language": lang,
        "summary": t["summary"].format(mood=_MOOD_LABEL[lang][checkin["mood"]],
                                       ctx=t["ctx"].format(c=ctx) if ctx else ""),
        "emotions": list(emotions.values()),
        "stress_signals": signals,
        "challenges": challenges,
        "recommendations": recs,
        "next_step": t["next"],
        "suggested_tasks": [],
        "support_note": t["support"] if heavy else None,
        "crisis": False,
    }


def demo_plan(req: dict) -> dict:
    t = _T[req["lang"]]
    stress = req["stress_level"]
    session = 25 if stress >= 7 else (40 if stress >= 4 else 50)
    brk = req["break_minutes"] + (5 if stress >= 8 else 0)
    budget = req["available_minutes"]
    if stress >= 8:
        budget = int(budget * 0.75)

    tasks = sorted(req["tasks"], key=lambda x: (PRIORITY_RANK[x["priority"]], x["deadline"] or "9999"))
    blocks, postponed, used, focus_count = [], [], 0, 0
    end_habit = 15

    for task in tasks:
        remaining = task["minutes"]
        n_parts = max(1, -(-remaining // session))
        part = 0
        while remaining > 0:
            gap = brk if blocks else 0
            room = budget - used - end_habit - gap
            chunk = min(session, remaining, room)
            if chunk < 15 and chunk < remaining:
                break
            if chunk <= 0:
                break
            if blocks:
                focus_count += 1
                is_habit = focus_count % 3 == 0
                blocks.append({"type": "habit" if is_habit else "break",
                               "title": t["habit_mid"] if is_habit else t["break"],
                               "minutes": brk, "task_id": None, "note": ""})
                used += brk
            part += 1
            remaining -= chunk
            title = task["title"] + (f" ({t['part'].format(i=part, n=n_parts)})" if n_parts > 1 else "")
            blocks.append({"type": "task", "title": title, "minutes": chunk, "task_id": task["id"], "note": ""})
            used += chunk
        if remaining > 0:
            reason = t["postpone_partial"].format(m=remaining) if part else t["postpone_reason"]
            postponed.append({"task_id": task["id"], "reason": reason})

    if not any(b["type"] == "task" for b in blocks):
        first = tasks[0]
        postponed = [p for p in postponed if p["task_id"] != first["id"]]
        blocks.append({"type": "task", "title": first["title"], "minutes": min(session, first["minutes"]),
                       "task_id": first["id"], "note": ""})
    blocks.append({"type": "habit", "title": t["habit_end"], "minutes": end_habit, "task_id": None, "note": ""})

    tips = list(t["tips"])
    if stress >= 7:
        tips.insert(0, t["tip_stress"])
    overload = bool(postponed)
    return {
        "overview": t["plan_overview"],
        "overload": overload,
        "overload_advice": t["overload_advice"] if overload else "",
        "blocks": blocks,
        "postponed": postponed,
        "tips": tips[:3],
    }


def demo_coach(info: dict) -> dict:
    """DEMO MODE study breakdown: splits the chapters in a fixed order (difficult
    ones first). Not AI - the UI labels it as demo."""
    from messages import encouragement, t

    lang = info.get("lang", "fr")
    chapters = info.get("difficult", []) + [c for c in info.get("chapters", []) if c not in info.get("difficult", [])]
    days = info.get("days_left")
    short = days is not None and days <= 2
    steps = []
    for ch in chapters[: (3 if short else 5)]:
        steps.append({"title": t(lang, "coach_step_chapter").format(ch=ch), "minutes": 30 if short else 45})
    if not steps:
        steps = [{"title": t(lang, k), "minutes": m} for k, m in
                 (("coach_generic_1", 20), ("coach_generic_2", 40), ("coach_generic_3", 30))]
    steps.append({"title": t(lang, "coach_step_selftest"), "minutes": 20})
    return {"message": encouragement(lang, days, info.get("percent", 0), info.get("subject", ""), seed=info.get("subject", "")),
            "steps": steps, "tip": t(lang, "coach_tip")}
