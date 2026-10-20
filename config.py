"""Application configuration, read from environment variables (.env supported)."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

AI_API_KEY = os.getenv("AI_API_KEY", "").strip()
AI_BASE_URL = os.getenv(
    "AI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai"
).strip().rstrip("/")
AI_MODEL = os.getenv("AI_MODEL", "gemini-2.5-flash").strip()
AI_TIMEOUT_SECONDS = float(os.getenv("AI_TIMEOUT_SECONDS", "45"))
PORT = int(os.getenv("PORT", "5000"))
HOST = os.getenv("HOST", "127.0.0.1")  # use 0.0.0.0 only behind a proper reverse proxy
FRONTEND_DIR = ROOT_DIR / "frontend"

# Persistent storage (SQLite file, created automatically, ignored by Git)
DATA_DIR = Path(os.getenv("DATA_DIR", str(ROOT_DIR / "data")))
DB_PATH = Path(os.getenv("DB_PATH", str(DATA_DIR / "balanceai.db")))
TIMEZONE = os.getenv("APP_TIMEZONE", "Africa/Tunis")

# Web Push (browser notifications). If the keys are empty, a key pair is
# generated once and stored in data/vapid.json (never committed).
VAPID_PUBLIC_KEY = os.getenv("VAPID_PUBLIC_KEY", "").strip()
VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY", "").strip()
VAPID_SUBJECT = os.getenv("VAPID_SUBJECT", "mailto:balanceai@example.com").strip()

# Background reminder scheduler (runs inside the Flask process)
SCHEDULER_ENABLED = os.getenv("SCHEDULER_ENABLED", "1").strip() != "0"
SCHEDULER_INTERVAL_SECONDS = max(15, int(os.getenv("SCHEDULER_INTERVAL_SECONDS", "60")))

# Accounts and limits
SESSION_HOURS = int(os.getenv("SESSION_HOURS", "168"))
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "0").strip() == "1"   # set to 1 behind HTTPS
AI_RATE_PER_HOUR = int(os.getenv("AI_RATE_PER_HOUR", "40"))
CHAT_MAX_CHARS = 1500
CHAT_MAX_MESSAGES = 100
CHAT_HISTORY_SENT = 12

PLACEHOLDER_KEYS = {"", "your_api_key_here", "changeme"}


def ai_enabled() -> bool:
    return AI_API_KEY not in PLACEHOLDER_KEYS


def provider_name() -> str:
    url = AI_BASE_URL.lower()
    if "googleapis" in url:
        return "Google Gemini"
    if "groq" in url:
        return "Groq"
    if "openai.com" in url:
        return "OpenAI"
    if "openrouter" in url:
        return "OpenRouter"
    if "localhost" in url or "127.0.0.1" in url:
        return "Local model"
    return "OpenAI-compatible API"
