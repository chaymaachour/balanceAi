"""BalanceAI - Flask backend.

Serves the frontend and exposes a small JSON API. The AI API key stays on the
server and is never sent to the browser.
"""
from __future__ import annotations

import logging

from flask import Flask, jsonify, request, send_from_directory

import ai_service
import auth
import chat_api
import config
import db
import scheduler
from school_api import bp as school_bp
from demo_fallback import demo_analysis, demo_plan
from safety import crisis_message, detect_crisis
from validators import (ValidationError, add_times, parse_checkin, parse_plan_request,
                        validate_analysis, validate_plan)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("balanceai")

app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024
db.init()
app.register_blueprint(auth.bp)
app.register_blueprint(school_bp)
app.register_blueprint(chat_api.bp)
app.before_request(auth.guard)


@app.errorhandler(auth.AuthError)
def _auth_error(exc):
    return jsonify({"error": str(exc)}), exc.status


@app.errorhandler(404)
def _404(exc):
    if request.path.startswith("/api/"):
        return jsonify({"error": "Not found."}), 404
    return exc


@app.errorhandler(413)
def _413(exc):
    return jsonify({"error": "Request too large."}), 413


@app.errorhandler(500)
def _500(exc):
    log.exception("Unhandled error")
    return jsonify({"error": "Server error."}), 500


def _source(ai_used: bool, error: str | None = None) -> dict:
    return {
        "mode": "ai" if ai_used else "demo",
        "provider": config.provider_name() if ai_used else None,
        "model": config.AI_MODEL if ai_used else None,
        "fallback_reason": error,
    }


@app.get("/api/status")
def status():
    enabled = config.ai_enabled()
    return jsonify({
        "ai_enabled": enabled,
        "provider": config.provider_name() if enabled else None,
        "model": config.AI_MODEL if enabled else None,
    })


@app.post("/api/analyze")
def analyze():
    try:
        checkin = parse_checkin(request.get_json(silent=True))
    except ValidationError as exc:
        return jsonify({"error": str(exc)}), 400

    crisis = detect_crisis(checkin["text"])
    result, ai_used, error = None, False, None
    if config.ai_enabled():
        try:
            result = validate_analysis(ai_service.analyze_checkin(checkin))
            ai_used = True
        except (ai_service.AIError, ValidationError) as exc:
            error = str(exc)
            log.warning("Falling back to demo analysis: %s", error)
    if result is None:
        result = demo_analysis(checkin)

    if crisis or result["crisis"]:
        result["crisis"] = True
        result["crisis_message"] = crisis_message(checkin["lang"])
    result["source"] = _source(ai_used, error)
    return jsonify(result)


@app.post("/api/plan")
def plan():
    try:
        req = parse_plan_request(request.get_json(silent=True))
    except ValidationError as exc:
        return jsonify({"error": str(exc)}), 400

    result, ai_used, error = None, False, None
    if config.ai_enabled():
        try:
            result = validate_plan(ai_service.generate_plan(req), req)
            ai_used = True
        except (ai_service.AIError, ValidationError) as exc:
            error = str(exc)
            log.warning("Falling back to demo plan: %s", error)
    if result is None:
        result = demo_plan(req)

    result = add_times(result, req["start_time"])
    if result["total_minutes"] > req["available_minutes"] * 1.1:
        result["overload"] = True
    
    result["source"] = _source(ai_used, error)
    return jsonify(result)


@app.get("/")
def index():
    return send_from_directory(config.FRONTEND_DIR, "index.html")


@app.get("/<path:path>")
def static_files(path):
    resp = send_from_directory(config.FRONTEND_DIR, path)
    if path == "sw.js":
        resp.headers["Cache-Control"] = "no-cache"
        resp.headers["Service-Worker-Allowed"] = "/"
    return resp


@app.after_request
def security_headers(resp):
    if request.path.startswith("/api/"):
        resp.headers["Cache-Control"] = "no-store"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "same-origin"
    resp.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'")
    return resp


if __name__ == "__main__":
    mode = f"REAL AI ({config.provider_name()} / {config.AI_MODEL})" if config.ai_enabled() else "DEMO MODE (no API key)"
    scheduler.start()
    print(f"\n  BalanceAI running on http://localhost:{config.PORT}  -  {mode}\n")
    app.run(host=config.HOST, port=config.PORT, debug=False)
