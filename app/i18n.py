"""Interface texts. Each language is a JSON file in app/locales; English is the fallback."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

LOCALES_DIR = Path(__file__).parent / "locales"
DEFAULT = "en"


@lru_cache
def load(lang: str) -> dict[str, str]:
    path = LOCALES_DIR / f"{lang}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def available() -> list[str]:
    return sorted(p.stem for p in LOCALES_DIR.glob("*.json"))


def pick_language(code: str | None) -> str:
    """Telegram language_code like 'ru', 'en-US', 'pt-br' -> one of our locales."""
    base = (code or DEFAULT).split("-")[0].lower()
    return base if base in available() else DEFAULT


def t(lang: str, key: str, **params) -> str:
    text = load(lang).get(key) or load(DEFAULT).get(key) or key
    return text.format(**params) if params else text
