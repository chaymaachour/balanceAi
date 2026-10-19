
"""Simple local RAG for BalanceAI knowledge documents."""

from pathlib import Path
import re

KNOWLEDGE_DIR = Path(__file__).resolve().parent / "knowledge"


def _tokens(text: str) -> set[str]:
    return {
        word
        for word in re.findall(r"\w+", text.lower())
        if len(word) > 1
    }


def retrieve_context(question: str, top_k: int = 3) -> dict:
    """Retrieve relevant paragraphs from local text documents."""

    if not KNOWLEDGE_DIR.exists():
        return {"context": "", "sources": []}

    question_words = _tokens(question)
    if not question_words:
        return {"context": "", "sources": []}

    passages = []

    for path in KNOWLEDGE_DIR.glob("*.txt"):
        try:
            document = path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError):
            continue

        for paragraph in re.split(r"\n\s*\n", document):
            paragraph = paragraph.strip()
            if not paragraph:
                continue

            paragraph_words = _tokens(paragraph)
            score = len(question_words & paragraph_words)

            if score:
                passages.append((score, path.name, paragraph))

    passages.sort(key=lambda item: item[0], reverse=True)
    selected = passages[:top_k]

    context = "\n\n".join(
        f"[Source: {filename}]\n{paragraph}"
        for _, filename, paragraph in selected
    )

    sources = list(dict.fromkeys(
        filename for _, filename, _ in selected
    ))

    return {"context": context, "sources": sources}
