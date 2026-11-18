"""Parses the HTML of t.me/<name> and t.me/s/<name> pages."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

from bs4 import BeautifulSoup

# Explicit ad labels. Russian law requires "Реклама" + an ad id (erid) on paid posts,
# so these are reliable for RU channels; English channels use #ad / sponsored.
AD_MARKERS = re.compile(
    r"(#реклама|#промо|\bреклама\b|на правах рекламы|партн[её]рск\w* (пост|материал)|\berid\b"
    r"|#ad\b|#ads\b|#sponsored|\bsponsored\b|\bpaid partnership\b|\badvertisement\b)",
    re.IGNORECASE,
)
# Calls to subscribe to *another* channel: typical for cross-promotion posts.
SUBSCRIBE_CALL = re.compile(
    r"(?<!\w)(подпиш\w*|подписыва\w*|subscribe(?!\w)|join (us|the channel|now|here)(?!\w)"
    r"|follow (us|me|the channel)(?!\w)|follow @)",
    re.IGNORECASE,
)
CHANNEL_LINK = re.compile(r"(?:t\.me/|telegram\.me/)(\+?[A-Za-z0-9_]{4,})", re.IGNORECASE)
MENTION = re.compile(r"(?<![\w@])@([A-Za-z][A-Za-z0-9_]{3,31})")


@dataclass
class ChannelInfo:
    username: str
    title: str = ""
    description: str = ""
    subscribers: int | None = None
    verified: bool = False
    preview_available: bool = True


@dataclass
class Post:
    id: int
    date: datetime | None
    views: int | None
    reactions: int = 0
    has_reactions_block: bool = False
    forwarded: bool = False
    text: str = ""
    explicit_ad: bool = False
    promo_of: list[str] = field(default_factory=list)  # other channels promoted in the post

    @property
    def likely_ad(self) -> bool:
        return self.explicit_ad or bool(self.promo_of)


def parse_count(text: str | None) -> int | None:
    """'987' -> 987, '1.2K' -> 1200, '3,4M' -> 3400000, '12 345' -> 12345."""
    if not text:
        return None
    value = text.strip().replace("\u00a0", " ").replace(" ", "")
    match = re.match(r"^([\d.,]+)([KkMmКкМм]?)", value)
    if not match:
        return None
    number, suffix = match.groups()
    suffix = suffix.upper().replace("К", "K").replace("М", "M")
    if suffix:
        number = number.replace(",", ".")
        multiplier = 1_000 if suffix == "K" else 1_000_000
        try:
            return int(round(float(number) * multiplier))
        except ValueError:
            return None
    digits = re.sub(r"\D", "", number)
    return int(digits) if digits else None


def parse_channel_card(html: str, username: str) -> ChannelInfo:
    soup = BeautifulSoup(html, "html.parser")
    info = ChannelInfo(username=username)
    title = soup.select_one(".tgme_page_title")
    if title:
        info.verified = bool(title.select_one(".verified-icon"))
        info.title = _clean_title(title)
    description = soup.select_one(".tgme_page_description")
    if description:
        info.description = description.get_text(" ", strip=True)
    extra = soup.select_one(".tgme_page_extra")
    if extra:
        text = extra.get_text(" ", strip=True)
        # "12 345 subscribers" / "12 345 members" (groups); take the number before the word
        match = re.search(r"([\d\s\u00a0.,KkMm]+)\s*(subscribers|members|подписчик)", text)
        if match:
            info.subscribers = parse_count(match.group(1))
    return info


def _clean_title(node) -> str:
    """Channel title without the verified badge (the badge is reported separately)."""
    for badge in node.select(".verified-icon, .scam-icon, .fake-icon"):
        badge.decompose()
    return node.get_text(" ", strip=True).replace("\u2714", "").replace("\ufe0f", "").strip()


def post_ids(html: str) -> list[int]:
    soup = BeautifulSoup(html, "html.parser")
    ids = []
    for node in soup.select(".tgme_widget_message[data-post]"):
        try:
            ids.append(int(node["data-post"].rsplit("/", 1)[1]))
        except (ValueError, IndexError):
            continue
    return ids


def parse_preview(html: str, username: str) -> tuple[list[Post], dict]:
    """Returns posts and header info (title / subscribers) from a t.me/s page."""
    soup = BeautifulSoup(html, "html.parser")
    header: dict = {}
    counters = soup.select(".tgme_channel_info_counter")
    for counter in counters:
        kind = counter.select_one(".counter_type")
        value = counter.select_one(".counter_value")
        if kind and value and kind.get_text(strip=True).lower().startswith(("subscriber", "подпис")):
            header["subscribers"] = parse_count(value.get_text(strip=True))
    title = soup.select_one(".tgme_channel_info_header_title")
    if title:
        header["title"] = _clean_title(title)

    posts: list[Post] = []
    own = username.lower()
    for node in soup.select(".tgme_widget_message[data-post]"):
        try:
            post_id = int(node["data-post"].rsplit("/", 1)[1])
        except (ValueError, IndexError):
            continue
        if "service_message" in (node.get("class") or []):
            continue

        time_tag = node.select_one(".tgme_widget_message_date time[datetime]") or node.select_one("time[datetime]")
        date = None
        if time_tag:
            try:
                date = datetime.fromisoformat(time_tag["datetime"])
            except ValueError:
                date = None

        views_tag = node.select_one(".tgme_widget_message_views")
        views = parse_count(views_tag.get_text(strip=True)) if views_tag else None

        reactions_block = node.select_one(".tgme_widget_message_reactions")
        reactions = 0
        if reactions_block:
            for reaction in reactions_block.select(".tgme_reaction"):
                reactions += parse_count(reaction.get_text(" ", strip=True).split()[-1]) or 0

        text_tag = node.select_one(".tgme_widget_message_text")
        text = text_tag.get_text(" ", strip=True) if text_tag else ""
        links = [a.get("href", "") for a in node.select(".tgme_widget_message_text a[href]")]

        promoted: set[str] = set()
        for source in links + [text]:
            for match in CHANNEL_LINK.findall(source):
                if match.lower() not in (own, "s", "share", "proxy", "addstickers", "c") and not match.lower().startswith(own + "/"):
                    promoted.add(match.split("/")[0])
        for match in MENTION.findall(text):
            if match.lower() != own:
                promoted.add(match)
        # A link to another channel is only treated as promotion together with a call to subscribe.
        promo_of = sorted(promoted) if promoted and SUBSCRIBE_CALL.search(text) else []

        posts.append(Post(
            id=post_id,
            date=date,
            views=views,
            reactions=reactions,
            has_reactions_block=reactions_block is not None,
            forwarded=node.select_one(".tgme_widget_message_forwarded_from") is not None,
            text=text[:500],
            explicit_ad=bool(AD_MARKERS.search(text)),
            promo_of=promo_of,
        ))
    return posts, header
