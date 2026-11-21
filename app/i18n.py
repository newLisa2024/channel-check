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


def plural(lang: str, key: str, n: int) -> str:
    """Word form for a number. The locale value lists the forms separated by "|":
    ru: one|few|many ("проверка|проверки|проверок"), en: one|other ("check|checks")."""
    forms = t(lang, key).split("|")
    if lang == "ru" and len(forms) == 3:
        n10, n100 = n % 10, n % 100
        if n10 == 1 and n100 != 11:
            return forms[0]
        if 2 <= n10 <= 4 and not 12 <= n100 <= 14:
            return forms[1]
        return forms[2]
    return forms[0] if n == 1 or len(forms) == 1 else forms[-1]


def t(lang: str, key: str, **params) -> str:
    text = load(lang).get(key) or load(DEFAULT).get(key) or key
    return text.format(**params) if params else text
