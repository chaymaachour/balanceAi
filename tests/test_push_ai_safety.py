import base64
import json
import os
import re
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def j(r):
    return json.loads(r.data)


def fake_subscription(endpoint="https://push.example.com/abc"):
    key = ec.generate_private_key(ec.SECP256R1())
    pub = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    b64 = lambda b: base64.urlsafe_b64encode(b).rstrip(b"=").decode()
    return {"endpoint": endpoint, "keys": {"p256dh": b64(pub), "auth": b64(os.urandom(16))}}


class Resp:
    def __init__(self, code):
        self.status_code, self.text, self.headers, self.reason = code, "", {}, "status"


def test_push_subscribe_send_and_expired(client, monkeypatch):
    import pywebpush
    h = client.h
    k = j(client.get("/api/push/public-key", headers=h))
    assert k["available"] and len(k["public_key"]) > 80
    assert client.post("/api/push/subscribe", json={"subscription": {"endpoint": "http://x"}}, headers=h).status_code == 400
    r = client.post("/api/push/subscribe", json={"subscription": fake_subscription()}, headers=h)
    assert j(r)["settings"]["push_enabled"]
    calls = []
    monkeypatch.setattr(pywebpush.requests, "post", lambda url, **kw: calls.append((url, kw)) or Resp(201))
    r = j(client.post("/api/notifications/test", headers=h))
    assert r["pushed"] == 1 and calls[0][1]["headers"]["Authorization"].startswith("vapid")  # VAPID signed + encrypted
    monkeypatch.setattr(pywebpush.requests, "post", lambda url, **kw: Resp(410))
    r = j(client.post("/api/notifications/test", headers=h))
    assert r["pushed"] == 0 and r["subscriptions"] == 0  # expired subscription removed
    r = client.post("/api/push/unsubscribe", json={}, headers=h)
    assert j(r)["settings"]["push_enabled"] is False


def test_push_payload_is_private_by_default():
    import push
    item = {"kind": "session", "title": "Maths 18:00", "body": "secret detail", "link": "#revisions"}
    p = push.payload(item, {"notif_lang": "fr", "push_private": True})
    assert "Maths" not in p["title"] + p["body"]
    assert push.payload(item, {"push_private": False})["body"] == "secret detail"


def test_demo_mode_and_coach(client):
    h = client.h
    r = j(client.post("/api/analyze", json={"mood": "stressed", "text": "examen ghodwa", "lang": "fr"}, headers=client.h))
    assert r["source"]["mode"] == "demo"
    eid = j(client.post("/api/exams", json={"subject": "Physique", "difficult": "Optique"}, headers=h))["exam"]["id"]
    c = j(client.post(f"/api/exams/{eid}/coach", json={"lang": "fr"}, headers=h))
    assert c["source"]["mode"] == "demo" and "Optique" in c["steps"][0]["title"]


def test_ai_provider_used_and_outage_fallback(client, monkeypatch):
    import ai_service
    import config
    monkeypatch.setattr(config, "AI_API_KEY", "test-key")
    sent = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        sent["body"] = json
        content = '{"message": "Tu avances bien.", "steps": [{"title": "Optique: fiche", "minutes": 30}], "tip": "Pause"}'
        r = Resp(200)
        r.json = lambda: {"choices": [{"message": {"content": content}}]}
        r.raise_for_status = lambda: None
        r.ok = True
        return r

    monkeypatch.setattr(ai_service.requests, "post", fake_post)
    eid = j(client.post("/api/exams", json={"subject": "Physique", "difficult": "Optique"}, headers=client.h))["exam"]["id"]
    c = j(client.post(f"/api/exams/{eid}/coach", json={"lang": "fr"}, headers=client.h))
    assert c["source"]["mode"] == "ai" and c["message"] == "Tu avances bien."
    assert client.uid not in json.dumps(sent["body"])  # no identifier sent to the provider

    def down(*a, **kw):
        raise ai_service.requests.ConnectionError("down")

    monkeypatch.setattr(ai_service.requests, "post", down)
    c = j(client.post(f"/api/exams/{eid}/coach", json={"lang": "fr"}, headers=client.h))
    assert c["source"]["mode"] == "demo" and c["source"]["fallback_reason"]
    r = j(client.post("/api/analyze", json={"mood": "okay", "text": "", "lang": "en"}, headers=client.h))
    assert r["source"]["mode"] == "demo"


def test_safety_preserved(client):
    r = j(client.post("/api/analyze", json={"mood": "overwhelmed", "text": "je veux mourir", "lang": "fr"}, headers=client.h))
    assert r["crisis"] and "190" in json.dumps(r["crisis_message"])
    assert client.post("/api/analyze", json={"mood": "nope"}, headers=client.h).status_code == 400
    assert client.post("/api/analyze", json={"mood": "okay", "text": "x" * 3000}, headers=client.h).status_code == 400


def test_no_secrets_in_frontend_or_repo():
    root = Path(__file__).resolve().parent.parent
    pattern_hits = []
    for p in list((root / "frontend").rglob("*")) + [root / ".env.example"]:
        if p.is_file() and p.suffix in (".js", ".html", ".css", ".example", ".json") and "vendor" not in p.parts:
            text = p.read_text(encoding="utf-8", errors="ignore")
            for pat in (r"AIza[0-9A-Za-z_-]{30,}", r"\bsk-[A-Za-z0-9_-]{20,}", r"\bgsk_[A-Za-z0-9]{20,}"):
                if re.search(pat, text):
                    pattern_hits.append((p.name, pat))
            if p.name != ".env.example" and ("VAPID_PRIVATE" in text or "AI_API_KEY" in text):
                pattern_hits.append((p.name, "secret variable"))
    assert pattern_hits == []
    gi = (root / ".gitignore").read_text()
    assert ".env" in gi and "data/" in gi
