import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
os.environ["SCHEDULER_ENABLED"] = "0"
os.environ["AI_API_KEY"] = ""

import pytest  # noqa: E402


def make_client(app, email, password="Sup3rSecret99"):
    """A test client with its own cookie jar, signed up and logged in."""
    c = app.test_client()
    r = c.post("/api/auth/signup", json={"email": email, "password": password})
    assert r.status_code == 201, r.get_json()
    c.csrf = r.get_json()["csrf"]
    c.h = {"X-CSRF-Token": c.csrf}
    import db
    with db.tx() as conn:
        c.uid = conn.execute("SELECT user_id FROM accounts WHERE email=?", (email,)).fetchone()["user_id"]
    return c


@pytest.fixture()
def client(tmp_path, monkeypatch):
    import auth
    import config
    import db
    import push
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "AI_API_KEY", "")
    monkeypatch.setattr(push, "_keys", None)
    db.set_path(tmp_path / "test.db")
    db.init()
    auth.limiter.reset()
    from app import app
    app.config["TESTING"] = True
    app.make_client = lambda email, password="Sup3rSecret99": make_client(app, email, password)
    c = make_client(app, "main@example.com")
    c.app = app
    return c


BASE_SETTINGS = {
    "notifications_enabled": True, "day_end_enabled": True, "wellness_reminder": False,
    "session_reminders": True, "exam_reminders": True, "reminder_days": [0, 1, 2, 3, 4, 5, 6],
    "home_time": "", "commute_minutes": 30, "rest_minutes": 45, "checkin_time": "",
    "quiet_start": "22:00", "quiet_end": "07:30", "study_start": "09:00", "study_end": "21:30",
    "daily_study_minutes": 120, "session_minutes": 45, "break_minutes": 10, "notif_lang": "fr",
}
