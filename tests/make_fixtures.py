"""Generates HTML pages that mimic the structure of t.me/<name> and t.me/s/<name>.

Used to test the parser and metrics without network access.
Run:  python tests/make_fixtures.py
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

OUT = Path(__file__).parent / "fixtures"


def card(name: str, title: str, subs: int) -> str:
    return f"""<html><body><div class="tgme_page">
<div class="tgme_page_photo"></div>
<div class="tgme_page_title" dir="auto"><span dir="auto">{title}</span><i class="verified-icon"><b>✔</b></i></div>
<div class="tgme_page_extra">{subs:,} subscribers</div>
<div class="tgme_page_description" dir="auto">Test channel description</div>
</div></body></html>""".replace(",", " ")


def message(name: str, post_id: int, when: datetime, views: str, text: str, reactions: list[tuple[str, str]] | None,
            forwarded: bool = False) -> str:
    reactions_html = ""
    if reactions is not None:
        items = "".join(f'<span class="tgme_reaction"><i class="emoji"><b>{e}</b></i>{c}</span>' for e, c in reactions)
        reactions_html = f'<div class="tgme_widget_message_reactions js-message_reactions">{items}</div>'
    fwd = '<div class="tgme_widget_message_forwarded_from accent_color">Forwarded from <a>Other</a></div>' if forwarded else ""
    return f"""<div class="tgme_widget_message_wrap js-widget_message_wrap">
<div class="tgme_widget_message text_not_supported_wrap js-widget_message" data-post="{name}/{post_id}" data-view="x">
<div class="tgme_widget_message_bubble">{fwd}
<div class="tgme_widget_message_text js-message_text" dir="auto">{text}</div>
{reactions_html}
<div class="tgme_widget_message_footer compact js-message_footer"><div class="tgme_widget_message_info short js-message_info">
<span class="tgme_widget_message_views">{views}</span><span class="copyonly"> views</span>
<span class="tgme_widget_message_meta"><a class="tgme_widget_message_date" href="https://t.me/{name}/{post_id}"><time datetime="{when.isoformat()}" class="time">{when:%H:%M}</time></a></span>
</div></div></div></div></div>"""


def preview(name: str, title: str, subs_short: str, messages: list[str], before: int | None) -> str:
    more = f'<a class="tme_messages_more js-messages_more" data-before="{before}" href="/s/{name}?before={before}"></a>' if before else ""
    return f"""<html><body>
<div class="tgme_channel_info_header_title"><span dir="auto">{title}</span></div>
<div class="tgme_channel_info_counters">
<div class="tgme_channel_info_counter"><span class="counter_value">{subs_short}</span> <span class="counter_type">subscribers</span></div>
</div>
<section class="tgme_channel_history js-message_history">{more}{''.join(messages)}</section>
</body></html>"""


def short(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 10_000:
        return f"{n / 1000:.1f}K"
    return str(n)


def build(name, title, subs, n_posts, view_fn, reaction_fn, ad_every, now, hours_step=14):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{name}_card.html").write_text(card(name, title, subs), encoding="utf-8")
    posts = []
    for i in range(n_posts):
        post_id = 1000 - i
        when = now - timedelta(hours=10 + i * hours_step)
        views = view_fn(i)
        if ad_every and i % ad_every == ad_every - 1:
            text = "Реклама. ООО Ромашка. erid: 2SDnje. Подписывайтесь на наш канал <a href='https://t.me/promo_partner'>@promo_partner</a>"
        else:
            text = f"Regular post number {post_id} with useful content."
        posts.append(message(name, post_id, when, short(views), text, reaction_fn(views), forwarded=(i == 7)))
    # t.me/s shows ~20 posts per page, newest at the bottom of the page
    pages = [posts[k:k + 20] for k in range(0, len(posts), 20)]
    for page_no, chunk in enumerate(pages, start=1):
        before = 1000 - (page_no * 20) + 1 if page_no < len(pages) else None
        html = preview(name, title, short(subs), list(reversed(chunk)), before)
        (OUT / f"{name}_preview_{page_no}.html").write_text(html, encoding="utf-8")


def main():
    random.seed(42)
    now = datetime.now(timezone.utc)
    # Healthy: 12 345 subscribers, views vary 2-6K, ~1.5% reactions, an ad every ~10 posts.
    build("healthy_test", "Healthy Test Channel", 12345, 60,
          lambda i: random.randint(2000, 6000),
          lambda v: [("👍", str(int(v * 0.01))), ("🔥", str(int(v * 0.005)))], 10, now)
    # Suspicious: 50 000 subscribers but ~400 almost identical views, almost no reactions, many ads.
    build("suspicious_test", "Suspicious Test Channel", 50000, 60,
          lambda i: 400 + random.randint(-8, 8),
          lambda v: [("👍", "1")], 2, now)
    # Sleepy (like a channel grown with ads/giveaways): 40 000 subscribers, ~2K natural views (5% reach),
    # lively readers with ~5% reactions. Should be yellow "inactive subscribers", not red.
    build("sleepy_test", "Sleepy Test Channel", 40000, 60,
          lambda i: random.randint(1400, 2800),
          lambda v: [("❤", str(int(v * 0.04))), ("🔥", str(int(v * 0.01)))], 10, now)
    # Frequent: 3+ posts a day with 7% reach and natural numbers. Should be yellow, not red.
    build("frequent_test", "Frequent Test Channel", 8000, 90,
          lambda i: random.randint(400, 750),
          lambda v: [("👍", str(max(int(v * 0.01), 1)))], 0, now, hours_step=7)
    print(f"Fixtures written to {OUT}")


if __name__ == "__main__":
    main()
