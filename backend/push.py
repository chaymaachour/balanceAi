"""Web Push (real browser notifications, delivered even when the BalanceAI tab is closed,
as long as the browser is running and this server is running).

VAPID keys come from .env; if absent, a key pair is generated once and saved in
data/vapid.json (ignored by Git). The private key never reaches the frontend.
"""
from __future__ import annotations

import base64
import json
import logging
import os

import config
import db

log = logging.getLogger("balanceai.push")

try:
    from pywebpush import WebPushException, webpush
    AVAILABLE = True
except ImportError:  # pragma: no cover - optional dependency
    AVAILABLE = False

_keys: dict | None = None


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def keys() -> dict | None:
    global _keys
    if _keys is not None or not AVAILABLE:
        return _keys
    if config.VAPID_PUBLIC_KEY and config.VAPID_PRIVATE_KEY:
        _keys = {"public": config.VAPID_PUBLIC_KEY, "private": config.VAPID_PRIVATE_KEY}
        return _keys
    path = config.DATA_DIR / "vapid.json"
    if path.exists():
        _keys = json.loads(path.read_text())
        return _keys
    from cryptography.hazmat.primitives import serialization
    from py_vapid import Vapid01

    v = Vapid01()
    v.generate_keys()
    pub = v.public_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    priv = v.private_key.private_numbers().private_value.to_bytes(32, "big")
    _keys = {"public": _b64(pub), "private": _b64(priv)}
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_keys))
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    log.info("Generated VAPID keys in %s", path)
    return _keys


def public_key() -> str | None:
    k = keys()
    return k["public"] if k else None


def save_subscription(uid: str, sub: dict) -> None:
    with db.tx() as c:
        c.execute("DELETE FROM push_subscriptions WHERE endpoint=?", (sub["endpoint"],))
        c.execute("INSERT INTO push_subscriptions(id,user_id,endpoint,p256dh,auth,created_at) VALUES(?,?,?,?,?,?)",
                  (db.new_id(), uid, sub["endpoint"], sub["p256dh"], sub["auth"], db.utcnow()))


def remove_subscription(uid: str, endpoint: str | None = None) -> int:
    with db.tx() as c:
        if endpoint:
            cur = c.execute("DELETE FROM push_subscriptions WHERE user_id=? AND endpoint=?", (uid, endpoint))
        else:
            cur = c.execute("DELETE FROM push_subscriptions WHERE user_id=?", (uid,))
        return cur.rowcount


def subscriptions(uid: str) -> list[dict]:
    with db.tx() as c:
        return db.rows(c.execute("SELECT * FROM push_subscriptions WHERE user_id=?", (uid,)))


def payload(item: dict, settings: dict) -> dict:
    """Lock-screen safe payload: by default no personal details are shown."""
    from messages import t
    lang = settings.get("notif_lang", "fr")
    if settings.get("push_private", True):
        return {"title": t(lang, "private_title"), "body": t(lang, "private_body"), "link": item.get("link", "#home"),
                "tag": item.get("kind", "balanceai")}
    return {"title": item["title"], "body": item["body"], "link": item.get("link", "#home"), "tag": item.get("kind", "balanceai")}


def send(row: dict, data: dict) -> str:
    """Send one push. Returns 'ok', 'gone' (subscription removed) or 'error'."""
    k = keys()
    if not k:
        return "error"
    try:
        webpush(subscription_info={"endpoint": row["endpoint"], "keys": {"p256dh": row["p256dh"], "auth": row["auth"]}},
                data=json.dumps(data, ensure_ascii=False), vapid_private_key=k["private"],
                vapid_claims={"sub": config.VAPID_SUBJECT}, ttl=3600, timeout=10)
    except WebPushException as exc:
        code = getattr(exc.response, "status_code", None)
        with db.tx() as c:
            if code in (404, 410):
                c.execute("DELETE FROM push_subscriptions WHERE id=?", (row["id"],))
                log.info("Removed expired push subscription (%s)", code)
                return "gone"
            c.execute("UPDATE push_subscriptions SET failures=failures+1 WHERE id=?", (row["id"],))
            c.execute("DELETE FROM push_subscriptions WHERE id=? AND failures>=5", (row["id"],))
        log.warning("Push failed (%s): %s", code, exc)
        return "error"
    except Exception as exc:  # network errors, invalid keys...
        with db.tx() as c:
            c.execute("UPDATE push_subscriptions SET failures=failures+1 WHERE id=?", (row["id"],))
            c.execute("DELETE FROM push_subscriptions WHERE id=? AND failures>=5", (row["id"],))
        log.warning("Push failed: %s", exc)
        return "error"
    with db.tx() as c:
        c.execute("UPDATE push_subscriptions SET last_success=?, failures=0 WHERE id=?", (db.utcnow(), row["id"]))
    return "ok"


def send_to_user(uid: str, item: dict, settings: dict) -> int:
    if not AVAILABLE or not settings.get("push_enabled"):
        return 0
    data = payload(item, settings)
    return sum(1 for row in subscriptions(uid) if send(row, data) == "ok")
