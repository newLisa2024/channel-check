"""Understands what the user sent: '@name', 't.me/name', a link with a post id,
'@name 50' (channel + ad price), or a post forwarded from a channel."""

from __future__ import annotations

import re
from dataclasses import dataclass

from tgcheck.fetch import FetchError, normalize_channel

PRICE_RE = re.compile(r"(?<![\w/])(\d{1,7}(?:[.,]\d{1,2})?)\s*(?:\$|usd|руб|rub|₽|€|eur|stars|⭐)?\s*$", re.IGNORECASE)


@dataclass
class ChannelRequest:
    username: str
    price: float | None = None


def parse_price(text: str) -> float | None:
    value = text.strip().replace(" ", "").replace(",", ".")
    value = re.sub(r"[^\d.]", "", value)
    try:
        price = float(value)
    except ValueError:
        return None
    return price if 0 < price < 10_000_000 else None


def parse_text(text: str) -> ChannelRequest | None:
    """Returns None when the text has no public channel in it."""
    text = (text or "").strip()
    if not text:
        return None
    first, _, rest = text.partition(" ")
    explicit = first.startswith("@") or "t.me/" in first or "telegram.me/" in first
    try:
        username = normalize_channel(first)
    except FetchError:
        return None
    rest = re.sub(r"(?<=\d)[\s\u00a0](?=\d)", "", rest.strip())  # "1 500" -> "1500"
    price = None
    if rest:
        match = PRICE_RE.search(rest)
        if match:
            price = parse_price(match.group(1))
        elif not explicit:
            return None  # a plain phrase like "hello there" is not a channel
    return ChannelRequest(username=username, price=price)


def from_forward(message) -> ChannelRequest | None:
    """A post forwarded from a public channel carries the channel in forward_origin."""
    origin = getattr(message, "forward_origin", None)
    chat = getattr(origin, "chat", None)
    username = getattr(chat, "username", None)
    if username:
        try:
            return ChannelRequest(username=normalize_channel(username))
        except FetchError:
            return None
    return None
