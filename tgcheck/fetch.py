"""Downloads the public web pages of a Telegram channel.

Only public pages are used (no Telegram account, no session):
  https://t.me/<name>     - channel card: title, exact subscriber count
  https://t.me/s/<name>   - web preview: the latest posts, ~20 per page,
                            older pages via ?before=<post_id>
"""

from __future__ import annotations

import re
import time
from pathlib import Path

import httpx

BASE = "https://t.me"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; ChannelCheck/0.1)",
    # English labels make the numbers ("12 345 subscribers") easier to parse.
    "Accept-Language": "en-US,en;q=0.9",
}
NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{3,31}$")


class FetchError(Exception):
    """The channel can't be read (doesn't exist, private, preview disabled, network)."""


def normalize_channel(raw: str) -> str:
    """Accepts '@name', 'name', 't.me/name', 'https://t.me/s/name/123' and returns 'name'."""
    value = raw.strip()
    value = re.sub(r"^https?://", "", value)
    value = re.sub(r"^(www\.)?(t|telegram)\.(me|dog)/", "", value)
    value = value.lstrip("@")
    if value.startswith("s/"):
        value = value[2:]
    value = value.split("/")[0].split("?")[0]
    if value.startswith("+") or value.startswith("joinchat"):
        raise FetchError("This is a private invite link. Only public channels (t.me/name) can be checked.")
    if not NAME_RE.match(value):
        raise FetchError(f"'{raw}' doesn't look like a public channel username.")
    return value


class ChannelFetcher:
    def __init__(self, delay: float = 1.0, timeout: float = 20.0, save_dir: Path | None = None):
        self.delay = delay  # be polite: pause between page requests
        self.save_dir = save_dir  # optional: keep raw HTML for debugging
        self.client = httpx.Client(headers=HEADERS, timeout=timeout, follow_redirects=True)

    def close(self) -> None:
        self.client.close()

    def _get(self, url: str, label: str) -> str:
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                response = self.client.get(url)
                if response.status_code == 429:  # rate limited: wait and retry
                    time.sleep(5 * (attempt + 1))
                    continue
                response.raise_for_status()
                html = response.text
                if self.save_dir:
                    self.save_dir.mkdir(parents=True, exist_ok=True)
                    (self.save_dir / f"{label}.html").write_text(html, encoding="utf-8")
                return html
            except httpx.HTTPError as exc:
                last_error = exc
                time.sleep(2 * (attempt + 1))
        raise FetchError(f"Network error while loading {url}: {last_error}")

    def channel_page(self, name: str) -> str:
        return self._get(f"{BASE}/{name}", f"{name}_card")

    def preview_pages(self, name: str, max_posts: int, parse_page) -> list[str]:
        """Loads preview pages until max_posts posts are collected or history ends.

        parse_page(html) must return the list of post ids found on that page;
        it is passed in so this module stays independent from the parser.
        """
        pages: list[str] = []
        seen: set[int] = set()
        url = f"{BASE}/s/{name}"
        for page_no in range(1, 50):
            html = self._get(url, f"{name}_preview_{page_no}")
            ids = [i for i in parse_page(html) if i not in seen]
            if page_no == 1 and not ids:
                # t.me/s/<name> redirects to t.me/<name> when the web preview is off.
                return [html]
            if not ids:
                break
            pages.append(html)
            seen.update(ids)
            if len(seen) >= max_posts:
                break
            url = f"{BASE}/s/{name}?before={min(ids)}"
            time.sleep(self.delay)
        return pages
