"""AI chat assistant. Every query is scoped to the authenticated user's id."""
from __future__ import annotations

import json
import logging
from datetime import date as Date

from flask import Blueprint, g, jsonify, request

import ai_service
import config
import db
import store
from safety import crisis_message, detect_crisis

log = logging.getLogger("balanceai.chat")
bp = Blueprint("chat", __name__, url_prefix="/api/chat")


def _conv(c, conv_id: str):
    row = c.execute("SELECT * FROM chat_conversations WHERE id=? AND user_id=?", (conv_id, g.user_id)).fetchone()
    return dict(row) if row else None


def _user_data() -> str:
    """Strictly necessary facts only: no e-mail, no name, no free-text notes."""
    uid = g.user_id
    today = Date.today()
    exams = []
    for e in store.exams(uid):
        if e["status"] == "upcoming" and e.get("date") and e["date"] >= today.isoformat():
            exams.append({"subject": e["subject"], "date": e["date"], "days_left": (Date.fromisoformat(e["date"]) - today).days,
                          "preparation_percent": e["preparation"], "difficult_chapters": e["difficult"][:200]})
    sessions = [{"date": s["date"], "start": s["start"], "end": s["end"], "status": s["status"]}
                for s in store.sessions(uid) if s["date"] >= today.isoformat() and s["status"] == "planned"][:6]
    return json.dumps({"today": today.isoformat(), "upcoming_exams": exams[:6], "next_revision_sessions": sessions},
                      ensure_ascii=False)


def _demo_reply(lang: str, use_context: bool) -> str:
    fr = lang == "fr"
    head = "[MODE DÉMO - réponse préenregistrée, pas une IA] " if fr else "[DEMO MODE - canned reply, not a real AI] "
    body = ("Pour avancer : choisis une seule tâche, travaille 25 minutes, puis fais 5 minutes de pause. "
            "Tu peux aussi essayer l'exercice de respiration dans la page Relax. "
            "Ajoute une clé API pour obtenir de vraies réponses personnalisées.") if fr else (
            "To move forward: pick one task, work 25 minutes, then take a 5-minute break. "
            "You can also try the breathing exercise on the Relax page. "
            "Add an API key to get real personalised answers.")
    if use_context:
        n = len(json.loads(_user_data())["upcoming_exams"])
        body += (f" (Examens à venir dans ton compte : {n}.)" if fr else f" (Upcoming exams in your account: {n}.)")
    return head + body


@bp.get("/conversations")
def list_conversations():
    with db.tx() as c:
        rows = db.rows(c.execute("SELECT id,title,updated_at FROM chat_conversations WHERE user_id=? "
                                 "ORDER BY updated_at DESC LIMIT 50", (g.user_id,)))
    return jsonify({"conversations": rows})


@bp.post("/conversations")
def create_conversation():
    cid, now = db.new_id(), db.utcnow()
    with db.tx() as c:
        c.execute("INSERT INTO chat_conversations(id,user_id,title,created_at,updated_at) VALUES(?,?,?,?,?)",
                  (cid, g.user_id, "", now, now))
    return jsonify({"id": cid}), 201


@bp.get("/conversations/<conv_id>")
def get_conversation(conv_id):
    with db.tx() as c:
        if not _conv(c, conv_id):
            return jsonify({"error": "Not found."}), 404
        msgs = db.rows(c.execute("SELECT id,role,content,mode,created_at FROM chat_messages WHERE conv_id=? AND user_id=? "
                                 "ORDER BY created_at, rowid", (conv_id, g.user_id)))
    return jsonify({"messages": msgs})


@bp.delete("/conversations/<conv_id>")
def delete_conversation(conv_id):
    with db.tx() as c:
        if not _conv(c, conv_id):
            return jsonify({"error": "Not found."}), 404
        c.execute("DELETE FROM chat_conversations WHERE id=? AND user_id=?", (conv_id, g.user_id))
    return jsonify({"deleted": True})


@bp.delete("/conversations")
def delete_all():
    with db.tx() as c:
        n = c.execute("DELETE FROM chat_conversations WHERE user_id=?", (g.user_id,)).rowcount
    return jsonify({"deleted": n})


@bp.post("/conversations/<conv_id>/messages")
def send(conv_id):
    data = request.get_json(silent=True)
    data = data if isinstance(data, dict) else {}
    text = str(data.get("content") or "").strip()
    lang = data.get("lang") if data.get("lang") in ("fr", "en", "tn") else "en"
    use_context = bool(data.get("use_context", False))
    if not text:
        return jsonify({"error": "Message is empty."}), 400
    if len(text) > config.CHAT_MAX_CHARS:
        return jsonify({"error": f"Message too long (max {config.CHAT_MAX_CHARS} characters)."}), 400
    with db.tx() as c:
        if not _conv(c, conv_id):
            return jsonify({"error": "Not found."}), 404
        count = c.execute("SELECT COUNT(*) n FROM chat_messages WHERE conv_id=?", (conv_id,)).fetchone()["n"]
        if count >= config.CHAT_MAX_MESSAGES:
            return jsonify({"error": "This conversation is full. Please start a new one."}), 400
        hist = db.rows(c.execute("SELECT role,content FROM chat_messages WHERE conv_id=? ORDER BY created_at DESC, rowid DESC LIMIT ?",
                                 (conv_id, config.CHAT_HISTORY_SENT)))[::-1]
    crisis = detect_crisis(text)
    mode, error = "demo", None
    if crisis:
        reply, mode = crisis_message(lang), "safety"
    elif config.ai_enabled():
        extra = "USER_DATA (facts only, may be empty): " + (_user_data() if use_context else "not shared by the user")
        try:
            reply = ai_service.chat_reply(extra, [{"role": h["role"], "content": h["content"]} for h in hist]
                                          + [{"role": "user", "content": text}])
            mode = "ai"
        except ai_service.AIError as exc:
            error = str(exc)
            log.warning("Chat fell back to demo: %s", error)
            reply = _demo_reply(lang, use_context)
    else:
        reply = _demo_reply(lang, use_context)
    now = db.utcnow()
    with db.tx() as c:
        c.execute("INSERT INTO chat_messages(id,conv_id,user_id,role,content,mode,created_at) VALUES(?,?,?,?,?,?,?)",
                  (db.new_id(), conv_id, g.user_id, "user", text, "", now))
        c.execute("INSERT INTO chat_messages(id,conv_id,user_id,role,content,mode,created_at) VALUES(?,?,?,?,?,?,?)",
                  (db.new_id(), conv_id, g.user_id, "assistant", reply, mode, db.utcnow()))
        c.execute("UPDATE chat_conversations SET updated_at=?, title=CASE WHEN title='' THEN ? ELSE title END WHERE id=?",
                  (db.utcnow(), text[:60], conv_id))
    return jsonify({"reply": reply, "mode": mode, "crisis": crisis, "fallback_reason": error,
                    "provider": config.provider_name() if mode == "ai" else None})
