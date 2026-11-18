"""Usage:
    python -m tgcheck durov
    python -m tgcheck https://t.me/somechannel --price 50 --lang ru
    python -m tgcheck somechannel --save-html debug/     # keep raw pages for debugging
    python -m tgcheck somechannel --from-html debug/     # re-run offline on saved pages
    python -m tgcheck --batch channels.txt --csv results.csv   # many channels -> one table
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
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


CSV_FIELDS = [
    "username", "title", "subscribers", "posts_analyzed", "posts_per_day", "median_views", "err",
    "err_factor", "views_cv", "reaction_rate", "ad_share", "verdict", "confidence", "flags", "error",
]


def read_batch(path: Path) -> list[str]:
    channels = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            channels.append(line)
    return channels


def run_one(raw: str, args):
    name = normalize_channel(raw)
    if args.from_html:
        card_html, pages = collect_offline(name, args.from_html)
    else:
        card_html, pages = collect_online(name, args.posts, args.save_html)
    return check(name, card_html, pages, args.posts, args.price)


def run_batch(args) -> int:
    channels = read_batch(args.batch)
    if not channels:
        print("❌ The batch file has no channels.", file=sys.stderr)
        return 1
    out = args.csv or args.batch.with_suffix(".csv")
    rows = []
    for index, raw in enumerate(channels, start=1):
        print(f"[{index}/{len(channels)}] {raw} ... ", end="", flush=True)
        row = {field: "" for field in CSV_FIELDS}
        row["username"] = raw
        try:
            report = run_one(raw, args)
            data = to_dict(report)
            row.update({
                "username": data["channel"]["username"], "title": data["channel"]["title"],
                "subscribers": data["channel"]["subscribers"],
                **{k: data[k] for k in ("posts_analyzed", "posts_per_day", "median_views", "err", "err_factor",
                                        "views_cv", "reaction_rate", "ad_share", "verdict", "confidence")},
                "flags": " ".join(f"{f['level']}:{f['code']}" for f in data["flags"]),
            })
            for key in ("err", "views_cv", "reaction_rate", "ad_share"):
                if isinstance(row[key], float):
                    row[key] = round(row[key], 4)
            print(f"{row['verdict']} (reach {row['err']})")
        except FetchError as exc:
            row["error"] = str(exc)
            print(f"error: {exc}")
        rows.append(row)
        if not args.from_html and index < len(channels):
            time.sleep(args.batch_delay)  # be polite to t.me between channels

    # utf-8-sig so Excel opens Cyrillic and emoji correctly
    with out.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nSaved {len(rows)} rows to {out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tgcheck", description="Should you buy an ad in this Telegram channel?")
    parser.add_argument("channel", nargs="?", help="@name, name or t.me link of a public channel")
    parser.add_argument("--posts", type=int, default=100, help="how many recent posts to analyze (default 100)")
    parser.add_argument("--price", type=float, help="the price the admin asks for one ad post")
    parser.add_argument("--lang", default="en", choices=["en", "ru"])
    parser.add_argument("--json", type=Path, help="also save the full result as JSON")
    parser.add_argument("--save-html", type=Path, help="save downloaded pages to this folder")
    parser.add_argument("--from-html", type=Path, help="analyze pages saved earlier instead of downloading")
    parser.add_argument("--batch", type=Path, help="text file with one channel per line (# for comments)")
    parser.add_argument("--csv", type=Path, help="where to save the batch table (default: <batch file>.csv)")
    parser.add_argument("--batch-delay", type=float, default=3.0, help="pause between channels in batch mode, seconds")
    args = parser.parse_args(argv)

    if args.batch:
        return run_batch(args)
    if not args.channel:
        parser.error("give a channel or --batch FILE")

    try:
        report = run_one(args.channel, args)
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
