import auth
import config
import ai_service


def J(r):
    return r.get_json()


def test_signup_validation_and_duplicate(client):
    app = client.application
    c = app.test_client()
    bad = [{"email": "nope", "password": "Abcdefgh12"}, {"email": "a@b.co", "password": "short1"},
           {"email": "a@b.co", "password": "onlyletterslong"}, {"email": "a@b.co", "password": "1234567890123"}]
    for b in bad:
        assert c.post("/api/auth/signup", json=b).status_code == 400
    assert c.post("/api/auth/signup", json={"email": " MAIN@Example.com ", "password": "Another1234"}).status_code == 409
    r = c.post("/api/auth/signup", json={"email": "New@Example.com", "password": "Another1234"})
    assert r.status_code == 201
    cookie = r.headers["Set-Cookie"]
    assert "HttpOnly" in cookie and "SameSite=Lax" in cookie
    import db
    with db.tx() as conn:
        h = conn.execute("SELECT password_hash FROM accounts WHERE email='new@example.com'").fetchone()[0]
    assert "Another1234" not in h and h.startswith("scrypt:")


def test_login_logout_and_session_invalidation(client):
    app = client.application
    c = app.test_client()
    assert c.post("/api/auth/login", json={"email": "main@example.com", "password": "bad-password1"}).status_code == 401
    assert c.post("/api/auth/login", json={"email": "ghost@example.com", "password": "bad-password1"}).get_json()["error"] == \
        c.post("/api/auth/login", json={"email": "main@example.com", "password": "bad-password1"}).get_json()["error"]
    r = c.post("/api/auth/login", json={"email": "main@example.com", "password": "Sup3rSecret99"})
    assert r.status_code == 200
    h = {"X-CSRF-Token": J(r)["csrf"]}
    assert c.get("/api/schedule").status_code == 200
    old_cookie = c.get_cookie("ba_session").value
    assert c.post("/api/auth/logout", headers=h).status_code == 200
    assert c.get("/api/schedule").status_code == 401
    # the old token is dead server side even if replayed
    c.set_cookie("ba_session", old_cookie)
    assert c.get("/api/schedule").status_code == 401


def test_csrf_and_origin(client):
    assert client.post("/api/exams", json={"subject": "Maths"}).status_code == 403          # no token
    assert client.post("/api/exams", json={"subject": "Maths"}, headers={"X-CSRF-Token": "x"}).status_code == 403
    h = dict(client.h, Origin="http://evil.example")
    assert client.post("/api/exams", json={"subject": "Maths"}, headers=h).status_code == 403


def test_brute_force_lockout(client):
    c = client.application.test_client()
    codes = [c.post("/api/auth/login", json={"email": "main@example.com", "password": "wrong-pass-1"}).status_code for _ in range(7)]
    assert codes[:5] == [401] * 5 and codes[5] == 429
    # even the right password is refused while locked
    assert c.post("/api/auth/login", json={"email": "main@example.com", "password": "Sup3rSecret99"}).status_code == 429


def test_session_expiry(client):
    import db
    with db.tx() as conn:
        conn.execute("UPDATE sessions SET expires_at='2000-01-01T00:00:00+00:00'")
    assert client.get("/api/schedule").status_code == 401


def test_data_isolation_between_accounts(client):
    other = client.application.make_client("other@example.com")
    exam = J(client.post("/api/exams", json={"subject": "Secret", "date": "2099-01-01"}, headers=client.h))["exam"]
    assert other.get("/api/exams").get_json()["exams"] == []
    assert other.put(f"/api/exams/{exam['id']}", json={"subject": "Hacked"}, headers=other.h).status_code == 404
    assert other.delete(f"/api/exams/{exam['id']}", headers=other.h).status_code == 404
    cid = J(client.post("/api/chat/conversations", headers=client.h))["id"]
    client.post(f"/api/chat/conversations/{cid}/messages", json={"content": "hello"}, headers=client.h)
    assert other.get(f"/api/chat/conversations/{cid}").status_code == 404
    assert other.post(f"/api/chat/conversations/{cid}/messages", json={"content": "x"}, headers=other.h).status_code == 404
    assert other.delete(f"/api/chat/conversations/{cid}", headers=other.h).status_code == 404
    assert J(other.get("/api/chat/conversations"))["conversations"] == []
    assert J(client.get(f"/api/chat/conversations/{cid}"))["messages"]


def test_chat_demo_mode_is_labelled(client):
    cid = J(client.post("/api/chat/conversations", headers=client.h))["id"]
    r = J(client.post(f"/api/chat/conversations/{cid}/messages", json={"content": "Help me plan", "lang": "en"}, headers=client.h))
    assert r["mode"] == "demo" and "DEMO" in r["reply"]
    assert client.post(f"/api/chat/conversations/{cid}/messages", json={"content": ""}, headers=client.h).status_code == 400
    assert client.post(f"/api/chat/conversations/{cid}/messages", json={"content": "x" * 2000}, headers=client.h).status_code == 400


def test_chat_ai_context_followup_and_privacy(client, monkeypatch):
    monkeypatch.setattr(config, "AI_API_KEY", "fake-key")
    seen = []

    def fake(extra, history):
        seen.append((extra, history))
        return "AI says hi"
    monkeypatch.setattr(ai_service, "chat_reply", fake)
    client.post("/api/exams", json={"subject": "Physique", "date": "2099-06-01"}, headers=client.h)
    cid = J(client.post("/api/chat/conversations", headers=client.h))["id"]
    u = f"/api/chat/conversations/{cid}/messages"
    r = J(client.post(u, json={"content": "q1", "use_context": True}, headers=client.h))
    assert r["mode"] == "ai"
    assert "Physique" in seen[0][0] and "main@example.com" not in seen[0][0]
    client.post(u, json={"content": "q2", "use_context": False}, headers=client.h)
    assert "not shared" in seen[1][0] and "Physique" not in seen[1][0]
    assert [m["content"] for m in seen[1][1]] == ["q1", "AI says hi", "q2"]     # context kept


def test_chat_provider_error_falls_back_and_crisis(client, monkeypatch):
    monkeypatch.setattr(config, "AI_API_KEY", "fake-key")

    def boom(extra, history):
        raise ai_service.AIError("timeout")
    monkeypatch.setattr(ai_service, "chat_reply", boom)
    cid = J(client.post("/api/chat/conversations", headers=client.h))["id"]
    u = f"/api/chat/conversations/{cid}/messages"
    r = J(client.post(u, json={"content": "hello"}, headers=client.h))
    assert r["mode"] == "demo" and r["fallback_reason"]
    r = J(client.post(u, json={"content": "je veux mourir", "lang": "fr"}, headers=client.h))
    assert r["crisis"] and "190" in r["reply"] and r["mode"] == "safety"


def test_ai_rate_limit(client, monkeypatch):
    monkeypatch.setattr(config, "AI_RATE_PER_HOUR", 3)
    codes = [client.post("/api/analyze", json={"mood": "okay", "text": "hi", "lang": "en"}, headers=client.h).status_code
             for _ in range(5)]
    assert codes[:3] == [200] * 3 and codes[3] == 429


def test_delete_account_removes_everything(client):
    import db
    cid = J(client.post("/api/chat/conversations", headers=client.h))["id"]
    client.post(f"/api/chat/conversations/{cid}/messages", json={"content": "hello"}, headers=client.h)
    assert client.post("/api/auth/delete-account", json={"password": "nope"}, headers=client.h).status_code == 403
    assert client.post("/api/auth/delete-account", json={"password": "Sup3rSecret99"}, headers=client.h).status_code == 200
    with db.tx() as c:
        for t in ("accounts", "users", "sessions", "chat_messages", "chat_conversations"):
            assert c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] == 0, t


def test_security_headers_and_legacy_claim(client):
    r = client.get("/")
    assert r.headers["X-Content-Type-Options"] == "nosniff" and "frame-ancestors 'none'" in r.headers["Content-Security-Policy"]
    import store
    legacy = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
    store.ensure_user(legacy)
    c = client.application.test_client()
    r = c.post("/api/auth/signup", json={"email": "legacy@example.com", "password": "Another1234", "legacy_device_id": legacy})
    assert r.status_code == 201
    import db
    with db.tx() as conn:
        assert conn.execute("SELECT user_id FROM accounts WHERE email='legacy@example.com'").fetchone()[0] == legacy
    # an already-claimed device id cannot be claimed twice
    c2 = client.application.test_client()
    c2.post("/api/auth/signup", json={"email": "thief@example.com", "password": "Another1234", "legacy_device_id": legacy})
    with db.tx() as conn:
        assert conn.execute("SELECT user_id FROM accounts WHERE email='thief@example.com'").fetchone()[0] != legacy


def test_notification_status_and_isolation(client):
    other = client.application.make_client("n2@example.com")
    assert client.post("/api/notifications/test", headers=client.h).status_code == 200
    items = J(client.get("/api/notifications"))["items"]
    assert items and items[0]["status"] == "sent"
    nid = items[0]["id"]
    assert other.post(f"/api/notifications/{nid}/read", headers=other.h).status_code == 404
    assert other.delete(f"/api/notifications/{nid}", headers=other.h).status_code == 404
    assert J(other.get("/api/notifications"))["items"] == []
    client.post(f"/api/notifications/{nid}/read", headers=client.h)
    assert J(client.get("/api/notifications"))["items"][0]["status"] == "read"


def test_reset_keeps_account(client):
    client.post("/api/exams", json={"subject": "Maths", "date": "2099-01-01"}, headers=client.h)
    assert client.post("/api/me/reset", headers=client.h).status_code == 200
    assert J(client.get("/api/exams"))["exams"] == []
    assert client.get("/api/auth/me").get_json()["authenticated"] is True


def test_migration_from_v2_keeps_data_and_makes_backup(tmp_path):
    import sqlite3
    import db
    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.executescript(db.MIGRATIONS[0])
    conn.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
    conn.execute("INSERT INTO meta VALUES('schema_version','1')")
    conn.execute("INSERT INTO users(id,settings,created_at,updated_at) VALUES('olduser','{}','t','t')")
    conn.execute("INSERT INTO exams(id,user_id,subject,created_at,updated_at) VALUES('e1','olduser','Maths','t','t')")
    conn.commit(); conn.close()
    previous = db._db_path
    try:
        db.set_path(path)
        assert db.init() == 2
    finally:
        db.set_path(previous)
    assert (tmp_path / "old.db.backup-v1").exists()
    conn = sqlite3.connect(path)
    assert conn.execute("SELECT subject FROM exams WHERE id='e1'").fetchone()[0] == "Maths"
    assert conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] == 0
