"""Accounts, sessions, CSRF and rate limiting.

* Passwords: scrypt via werkzeug (never stored in clear text).
* Sessions: random token in an HttpOnly cookie; only its SHA-256 is stored server side.
* CSRF: per-session token sent in the X-CSRF-Token header + Origin check + SameSite=Lax.
* Every private /api route is guarded by `guard()`; user ids come ONLY from the session.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import re
import secrets
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

from flask import Blueprint, g, jsonify, make_response, request
from werkzeug.security import check_password_hash, generate_password_hash

import config
import db
import store

log = logging.getLogger("balanceai.auth")
bp = Blueprint("auth", __name__, url_prefix="/api/auth")

COOKIE = "ba_session"
EMAIL_RE = re.compile(r"^[a-z0-9._%+\-]+@[a-z0-9\-]+(\.[a-z0-9\-]+)+$")
LEGACY_RE = re.compile(r"^[a-z0-9-]{16,40}$")
PUBLIC = {"/api/status", "/api/auth/signup", "/api/auth/login", "/api/auth/me"}
AI_PATHS = re.compile(r"^/api/(analyze|plan|chat/conversations/[a-z0-9]+/messages|exams/[a-z0-9]+/coach)$")
_DUMMY = generate_password_hash("not-a-real-password", method="scrypt")


class AuthError(Exception):
    def __init__(self, msg, status=400):
        super().__init__(msg)
        self.status = status


# ------------------------------------------------------------------ rate limiting
class Limiter:
    """Sliding-window limiter kept in memory (per server process)."""

    def __init__(self):
        self.hits = defaultdict(deque)
        self.lock = threading.Lock()

    def allow(self, key: str, limit: int, window: int, count: bool = True) -> bool:
        now = time.time()
        with self.lock:
            q = self.hits[key]
            while q and q[0] < now - window:
                q.popleft()
            if len(q) >= limit:
                return False
            if count:
                q.append(now)
            return True

    def reset(self):
        with self.lock:
            self.hits.clear()


limiter = Limiter()


def client_ip() -> str:
    return request.remote_addr or "?"


# ------------------------------------------------------------------ validation
def parse_credentials(data, signup: bool) -> tuple[str, str]:
    if not isinstance(data, dict):
        raise AuthError("Invalid request.")
    email = str(data.get("email") or "").strip().lower()
    password = str(data.get("password") or "")
    if len(email) > 254 or not EMAIL_RE.match(email):
        raise AuthError("Please enter a valid e-mail address.")
    if signup:
        if len(password) < 10 or len(password) > 128:
            raise AuthError("Password must be 10 to 128 characters long.")
        if not (re.search(r"[A-Za-z]", password) and re.search(r"\d", password)):
            raise AuthError("Password must contain at least one letter and one digit.")
    elif not password or len(password) > 128:
        raise AuthError("Invalid e-mail or password.", 401)
    return email, password


# ------------------------------------------------------------------ sessions
def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def create_session(user_id: str) -> tuple[str, str]:
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
    now = datetime.now(timezone.utc)
    with db.tx() as c:
        c.execute("DELETE FROM sessions WHERE expires_at < ?", (_iso(now),))
        c.execute("INSERT INTO sessions(token_hash,user_id,csrf,created_at,expires_at) VALUES(?,?,?,?,?)",
                  (_hash(token), user_id, csrf, _iso(now), _iso(now + timedelta(hours=config.SESSION_HOURS))))
    return token, csrf


def load_session():
    token = request.cookies.get(COOKIE)
    if not token or len(token) > 100:
        return None
    with db.tx() as c:
        row = c.execute("SELECT s.user_id, s.csrf, s.expires_at, a.email FROM sessions s "
                        "JOIN accounts a ON a.user_id = s.user_id WHERE s.token_hash=?", (_hash(token),)).fetchone()
    if not row or row["expires_at"] < _iso(datetime.now(timezone.utc)):
        return None
    return dict(row)


def destroy_session() -> None:
    token = request.cookies.get(COOKIE)
    if token:
        with db.tx() as c:
            c.execute("DELETE FROM sessions WHERE token_hash=?", (_hash(token),))


def destroy_all_sessions(user_id: str) -> None:
    with db.tx() as c:
        c.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))


def _set_cookie(resp, token: str):
    resp.set_cookie(COOKIE, token, max_age=config.SESSION_HOURS * 3600, httponly=True,
                    samesite="Lax", secure=config.COOKIE_SECURE, path="/")
    return resp


def _session_response(user_id: str, email: str, status: int = 200):
    token, csrf = create_session(user_id)
    resp = make_response(jsonify({"authenticated": True, "email": email, "csrf": csrf}), status)
    return _set_cookie(resp, token)


# ------------------------------------------------------------------ guard
def origin_ok() -> bool:
    origin = request.headers.get("Origin")
    if not origin:
        return True  # same-origin fetches from older browsers / tests; SameSite + CSRF token still apply
    return origin.split("://", 1)[-1] == request.host


def guard():
    """before_request hook: authentication, CSRF and AI rate limits for /api/*."""
    path = request.path
    if not path.startswith("/api/"):
        return None
    if request.method not in ("GET", "HEAD", "OPTIONS") and not origin_ok():
        return jsonify({"error": "Cross-origin request refused."}), 403
    if path in PUBLIC:
        return None
    sess = load_session()
    if not sess:
        return jsonify({"error": "Please sign in.", "auth_required": True}), 401
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        sent = request.headers.get("X-CSRF-Token", "")
        if not hmac.compare_digest(sent, sess["csrf"]):
            return jsonify({"error": "Invalid security token. Reload the page."}), 403
    g.user_id, g.email = sess["user_id"], sess["email"]
    if request.method == "POST" and AI_PATHS.match(path):
        if not limiter.allow(f"ai:{g.user_id}", config.AI_RATE_PER_HOUR, 3600):
            return jsonify({"error": "AI usage limit reached for this hour. Please try again later."}), 429
    return None


def current_user_id() -> str:
    return g.user_id


# ------------------------------------------------------------------ routes
@bp.errorhandler(AuthError)
def _err(exc):
    return jsonify({"error": str(exc)}), exc.status


@bp.post("/signup")
def signup():
    if not limiter.allow(f"signup:{client_ip()}", 10, 3600):
        raise AuthError("Too many sign-up attempts. Try again later.", 429)
    data = request.get_json(silent=True)
    email, password = parse_credentials(data, signup=True)
    with db.tx() as c:
        if c.execute("SELECT 1 FROM accounts WHERE email=?", (email,)).fetchone():
            raise AuthError("An account with this e-mail may already exist. Try signing in.", 409)
    user_id = None
    legacy = str((data or {}).get("legacy_device_id") or "").strip().lower()
    if LEGACY_RE.match(legacy):
        with db.tx() as c:
            owned = c.execute("SELECT 1 FROM accounts WHERE user_id=?", (legacy,)).fetchone()
            exists = c.execute("SELECT 1 FROM users WHERE id=?", (legacy,)).fetchone()
        if exists and not owned:
            user_id = legacy  # keeps the data created before accounts existed
    user_id = user_id or db.new_id() + db.new_id()
    store.ensure_user(user_id)
    try:
        with db.tx() as c:
            c.execute("INSERT INTO accounts(id,user_id,email,password_hash,created_at) VALUES(?,?,?,?,?)",
                      (db.new_id(), user_id, email, generate_password_hash(password, method="scrypt"), db.utcnow()))
    except Exception:
        raise AuthError("An account with this e-mail may already exist. Try signing in.", 409)
    log.info("Account created (user %s)", user_id[:6])
    return _session_response(user_id, email, 201)


@bp.post("/login")
def login():
    data = request.get_json(silent=True)
    email, password = parse_credentials(data, signup=False)
    ip_key, mail_key = f"login-ip:{client_ip()}", f"login-mail:{email}"
    if not (limiter.allow(ip_key, 30, 900, count=False) and limiter.allow(mail_key, 5, 900, count=False)):
        raise AuthError("Too many attempts. Please wait 15 minutes and try again.", 429)
    with db.tx() as c:
        row = c.execute("SELECT user_id, password_hash FROM accounts WHERE email=?", (email,)).fetchone()
    ok = check_password_hash(row["password_hash"] if row else _DUMMY, password) and row is not None
    if not ok:
        limiter.allow(ip_key, 30, 900)
        limiter.allow(mail_key, 5, 900)
        log.info("Failed sign-in attempt")
        raise AuthError("Invalid e-mail or password.", 401)
    return _session_response(row["user_id"], email)


@bp.post("/logout")
def logout():
    # Needs a valid session + CSRF only if one exists; always clears the cookie.
    sess = load_session()
    if sess and not hmac.compare_digest(request.headers.get("X-CSRF-Token", ""), sess["csrf"]):
        return jsonify({"error": "Invalid security token."}), 403
    destroy_session()
    resp = make_response(jsonify({"authenticated": False}))
    resp.delete_cookie(COOKIE, path="/")
    return resp


@bp.get("/me")
def me():
    sess = load_session()
    if not sess:
        return jsonify({"authenticated": False})
    return jsonify({"authenticated": True, "email": sess["email"], "csrf": sess["csrf"]})


@bp.post("/logout-all")
def logout_all():
    destroy_all_sessions(g.user_id)
    resp = make_response(jsonify({"authenticated": False}))
    resp.delete_cookie(COOKIE, path="/")
    return resp


@bp.post("/delete-account")
def delete_account():
    """Delete the account and ALL its data after re-checking the password."""
    password = str((request.get_json(silent=True) or {}).get("password") or "")
    with db.tx() as c:
        row = c.execute("SELECT password_hash FROM accounts WHERE user_id=?", (g.user_id,)).fetchone()
    if not row or not check_password_hash(row["password_hash"], password):
        raise AuthError("Password is incorrect.", 403)
    store.delete_user(g.user_id)  # cascades: profile, timetable, exams, notifications, chats, sessions
    resp = make_response(jsonify({"deleted": True}))
    resp.delete_cookie(COOKIE, path="/")
    return resp
