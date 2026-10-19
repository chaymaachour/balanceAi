"""Safety helpers: detect possible disclosures of immediate danger.

This is a deliberately conservative keyword screen used *in addition to* the
AI model, so that crisis guidance is shown even if the AI is unavailable.
It is not a diagnostic tool.
"""
import re
import unicodedata

_CRISIS_PATTERNS = [
    # English
    r"\bkill (myself|me)\b", r"\bsuicid", r"\bend (my|it) (life|all)\b",
    r"\bwant to die\b", r"\bdon'?t want to (live|be alive)\b", r"\bself[- ]?harm",
    r"\bhurt(ing)? myself\b", r"\bno reason to live\b", r"\bbetter off dead\b",
    # French
    r"\bme suicider\b", r"\bme tuer\b", r"\benvie de mourir\b", r"\bveux mourir\b",
    r"\ben finir\b", r"\bme faire du mal\b", r"\bplus envie de vivre\b",
    r"\bm'?automutil", r"\bme scarifi",
    # Tunisian Arabizi
    r"\bn(o|e)?heb nmout\b", r"\bnheb nmout\b", r"\bnmout rou?h?i\b",
    r"\bnaktel rou?h?i\b", r"\bnektel rou?h?i\b", r"\bnoktel rou?h?i\b",
    r"\bntiha\b", r"\bmanhebch n3ich\b", r"\bma3adch nheb n3ich\b",
    # Arabic
    "انتحار", "ننتحر", "انتحر", "نقتل روحي", "نحب نموت", "نموت روحي",
    "اقتل نفسي", "أقتل نفسي", "أريد أن أموت", "اريد ان اموت", "ما نحبش نعيش",
]
_COMPILED = [re.compile(p, re.IGNORECASE) for p in _CRISIS_PATTERNS]


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    return text.replace("’", "'").lower()


def detect_crisis(text: str) -> bool:
    norm = _normalize(text)
    return any(p.search(norm) for p in _COMPILED)


CRISIS_MESSAGES = {
    "en": (
        "It sounds like you may be going through something really painful right now. "
        "You deserve immediate support from a real person. If you are in danger or "
        "thinking about ending your life, please call emergency services now "
        "(in Tunisia: SAMU 190) or go to the nearest emergency department. "
        "If you can, reach out right now to someone you trust - a friend, a family "
        "member, a doctor, or your university's counselling service - and tell them "
        "how you feel. You don't have to go through this alone."
    ),
    "fr": (
        "On dirait que tu traverses quelque chose de très douloureux en ce moment. "
        "Tu mérites un soutien immédiat de la part d'une vraie personne. Si tu es en "
        "danger ou si tu penses à mettre fin à ta vie, appelle les urgences maintenant "
        "(en Tunisie : SAMU 190) ou rends-toi aux urgences les plus proches. Si tu peux, "
        "contacte tout de suite une personne de confiance - un·e ami·e, un membre de ta "
        "famille, un médecin ou le service d'écoute de ton université - et dis-lui ce que "
        "tu ressens. Tu n'as pas à traverser cela seul·e."
    ),
}


def crisis_message(lang: str) -> str:
    return CRISIS_MESSAGES.get(lang, CRISIS_MESSAGES["en"])
