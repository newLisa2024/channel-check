"""Usage:
    python -m tgcheck durov
    python -m tgcheck https://t.me/somechannel --price 50 --lang ru
    python -m tgcheck somechannel --save-html debug/     # keep raw pages for debugging
    python -m tgcheck somechannel --from-html debug/     # re-run offline on saved pages
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .fetch import ChannelFetcher, FetchError, normalize_channel
from .metrics import analyze
from .parse import ChannelInfo, parse_channel_card, parse_preview, post_ids
from .report import render, to_dict


def collect_online(name: str, max_posts: int, save_dir: Path | None):
    fetcher = ChannelFetcher(save_dir=save_dir)
    try:
        card_html = fetcher.channel_page(name)
        pages = fetcher.preview_pages(name, max_posts, post_ids)
    finally:
        fetcher.close()
    return card_html, pages


def collect_offline(name: str, folder: Path):
    card = folder / f"{name}_card.html"
    if not card.exists():
        raise FetchError(f"{card} not found")
    pages = sorted(folder.glob(f"{name}_preview_*.html"), key=lambda p: int(p.stem.rsplit("_", 1)[1]))
    return card.read_text(encoding="utf-8"), [p.read_text(encoding="utf-8") for p in pages]


def check(name: str, card_html: str, pages: list[str], max_posts: int, price: float | None):
    info: ChannelInfo = parse_channel_card(card_html, name)
    if not info.title and "tgme_page_title" not in card_html:
        raise FetchError("Channel not found. Check the username.")

    posts, seen = [], set()
    header: dict = {}
    for html in pages:
        page_posts, page_header = parse_preview(html, name)
        header = header or page_header
        for p in page_posts:
            if p.id not in seen:
                seen.add(p.id)
                posts.append(p)
    posts = sorted(posts, key=lambda p: p.id, reverse=True)[:max_posts]

    if not posts and not header:
        info.preview_available = False
    if info.subscribers is None:
        info.subscribers = header.get("subscribers")
    if not info.title:
        info.title = header.get("title", "")
    return analyze(info, posts, price=price)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tgcheck", description="Should you buy an ad in this Telegram channel?")
    parser.add_argument("channel", help="@name, name or t.me link of a public channel")
    parser.add_argument("--posts", type=int, default=100, help="how many recent posts to analyze (default 100)")
    parser.add_argument("--price", type=float, help="the price the admin asks for one ad post")
    parser.add_argument("--lang", default="en", choices=["en", "ru"])
    parser.add_argument("--json", type=Path, help="also save the full result as JSON")
    parser.add_argument("--save-html", type=Path, help="save downloaded pages to this folder")
    parser.add_argument("--from-html", type=Path, help="analyze pages saved earlier instead of downloading")
    args = parser.parse_args(argv)

    try:
        name = normalize_channel(args.channel)
        if args.from_html:
            card_html, pages = collect_offline(name, args.from_html)
        else:
            card_html, pages = collect_online(name, args.posts, args.save_html)
        report = check(name, card_html, pages, args.posts, args.price)
    except FetchError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 1

    print(render(report, args.lang))
    if args.json:
        args.json.write_text(json.dumps(to_dict(report), ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        print(f"\nJSON saved to {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
