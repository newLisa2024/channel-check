"""Offline tests: python -m pytest -q  (fixtures are regenerated automatically)."""

import subprocess
import sys
from pathlib import Path

import pytest

from tgcheck.__main__ import check, collect_offline
from tgcheck.fetch import FetchError, normalize_channel
from tgcheck.parse import parse_count

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session", autouse=True)
def fixtures():
    subprocess.run([sys.executable, str(Path(__file__).parent / "make_fixtures.py")], check=True)


def run(name, price=None):
    card, pages = collect_offline(name, FIXTURES)
    return check(name, card, pages, 100, price)


@pytest.mark.parametrize("raw,expected", [
    ("durov", "durov"), ("@durov", "durov"), ("https://t.me/durov", "durov"),
    ("t.me/s/durov", "durov"), ("https://t.me/durov/123", "durov"), ("telegram.me/durov?x=1", "durov"),
])
def test_normalize(raw, expected):
    assert normalize_channel(raw) == expected


def test_private_link_rejected():
    with pytest.raises(FetchError):
        normalize_channel("https://t.me/+AbCdEf123")


@pytest.mark.parametrize("text,value", [
    ("987", 987), ("1.2K", 1200), ("15.3K", 15300), ("1,1M", 1_100_000), ("12 345", 12345), ("12\u00a0345", 12345),
])
def test_parse_count(text, value):
    assert parse_count(text) == value


def test_healthy_channel_is_green():
    r = run("healthy_test", price=60)
    assert r.channel.subscribers == 12345
    assert r.posts_analyzed == 60
    assert r.verdict == "green"
    assert 0.15 < r.err < 0.5
    assert r.cpm and r.cpm > 0
    assert ("promo_partner", 6) in r.promoted_channels


def test_suspicious_channel_is_red():
    r = run("suspicious_test")
    codes = {f.code for f in r.flags}
    assert r.verdict == "red"
    assert {"very_low_err", "uniform_views", "ad_heavy"} <= codes


def test_title_without_badge():
    r = run("healthy_test")
    assert r.channel.title == "Healthy Test Channel"
    assert r.channel.verified is True


@pytest.mark.parametrize("text,is_promo", [
    ("Subscribe to @partner_channel for daily news", True),
    ("Подписывайтесь на @partner_channel", True),
    ("We will follow up with @partner_channel next week", False),
    ("Thanks to @partner_channel for the data, following the release", False),
    ("Access is limited to subscribers. Thanks @partner_channel", False),
    ("Our subscribers loved the @partner_channel report", False),
    ("Спасибо подписчикам канала @partner_channel", False),
    ("Already subscribed to @partner_channel", False),
])
def test_promo_detection(text, is_promo):
    from tgcheck.parse import parse_preview
    html = ('<div class="tgme_widget_message" data-post="me_channel/1">'
            f'<div class="tgme_widget_message_text">{text}</div></div>')
    posts, _ = parse_preview(html, "me_channel")
    assert bool(posts[0].promo_of) is is_promo


def test_sleepy_channel_is_yellow_not_red():
    r = run("sleepy_test")
    codes = {f.code for f in r.flags}
    assert r.verdict == "yellow"
    assert "inactive_subs" in codes
    assert not any(f.level == "red" for f in r.flags)


def test_frequent_posting_softens_thresholds():
    r = run("frequent_test")
    codes = {f.code for f in r.flags}
    assert r.posts_per_day >= 3
    assert r.err_factor < 1
    assert "frequent_posting" in codes
    assert r.verdict != "red"


def test_reach_headline_and_price():
    from tgcheck.report import render
    r = run("healthy_test", price=60)
    text = render(r, "ru")
    assert "увидят около" in text and "за 1000 реальных просмотров" in text


def test_batch_mode_writes_csv(tmp_path):
    import csv
    from tgcheck.__main__ import main
    batch = tmp_path / "channels.txt"
    batch.write_text("# test list\nhealthy_test\n@suspicious_test\nt.me/+private_invite\n", encoding="utf-8")
    out = tmp_path / "out.csv"
    assert main(["--batch", str(batch), "--csv", str(out), "--from-html", str(FIXTURES)]) == 0
    rows = list(csv.DictReader(out.open(encoding="utf-8-sig")))
    assert [r["verdict"] for r in rows[:2]] == ["green", "red"]
    assert rows[2]["error"]  # private link is reported, not crashing the batch


# --- calibration 21.11: thresholds tuned on 24 real channels ---------------------------------

from datetime import datetime, timedelta, timezone

from tgcheck.metrics import analyze, frequency_factor
from tgcheck.parse import ChannelInfo, Post

NOW = datetime(2026, 11, 21, 12, tzinfo=timezone.utc)


def _posts(views, per_day=1.0, **kw):
    """Posts from oldest to newest, all older than 48 h, `per_day` posts a day."""
    step = timedelta(days=1 / per_day)
    start = NOW - timedelta(days=3) - step * len(views)
    return [Post(id=i + 1, date=start + step * i, views=v, **kw) for i, v in enumerate(views)]


def _codes(report):
    return {f.code for f in report.flags}


def test_very_frequent_channels_get_a_softer_factor():
    assert frequency_factor(9.6) == 0.5
    assert frequency_factor(5) == 0.6


def test_uniform_views_alone_is_a_warning_not_red():
    # Small loyal channel: healthy reach, views within a few percent of each other.
    views = [11_000 + (i % 5) * 100 for i in range(40)]
    r = analyze(ChannelInfo("loyal", subscribers=40_000), _posts(views), now=NOW)
    assert "uniform_views_check" in _codes(r) and "uniform_views" not in _codes(r)
    assert r.verdict != "red"


def test_uniform_views_with_weak_reach_is_red():
    views = [1_500 + (i % 5) * 10 for i in range(40)]
    r = analyze(ChannelInfo("botted", subscribers=60_000), _posts(views), now=NOW)
    assert "uniform_views" in _codes(r) and r.verdict == "red"


def test_high_reach_and_views_above_subscribers_are_flagged():
    varied = [int(30_000 * (0.6 + (i % 7) / 7)) for i in range(40)]
    high = analyze(ChannelInfo("high", subscribers=50_000), _posts(varied), now=NOW)
    assert "high_err" in _codes(high) and "views_exceed_subs" not in _codes(high)
    above = analyze(ChannelInfo("above", subscribers=20_000), _posts(varied), now=NOW)
    assert "views_exceed_subs" in _codes(above)


def test_own_footer_links_are_not_counted_as_ads():
    # Every post ends with "Подписывайтесь на наш чат @my_chat"; two posts are real ads.
    posts = _posts([5_000] * 20, promo_of=["my_chat"])
    posts[3].promo_of = ["my_chat", "partner_one"]
    posts[9].strong_ad = True
    r = analyze(ChannelInfo("footer", subscribers=20_000), posts, now=NOW)
    assert r.ad_share == 2 / 20
    assert ("my_chat", 1) not in r.promoted_channels and ("partner_one", 1) in r.promoted_channels
    assert "ad_heavy" not in _codes(r)


def test_footer_word_reklama_is_ignored_but_erid_counts():
    # "Реклама: @manager" in every post's footer; one post has an erid.
    posts = _posts([5_000] * 20, explicit_ad=True)
    posts[5].strong_ad = True
    r = analyze(ChannelInfo("footer2", subscribers=20_000), posts, now=NOW)
    assert r.ad_share == 1 / 20


def test_preview_pages_keeps_paging_until_enough_mature_posts():
    from tgcheck.fetch import ChannelFetcher

    fetcher = ChannelFetcher(delay=0)
    pages_served = []

    def fake_get(url, label):
        before = int(url.split("before=")[1]) if "before=" in url else 1000
        ids = list(range(before - 20, before))
        pages_served.append(ids)
        return ",".join(map(str, ids))

    fetcher._get = fake_get
    parse_ids = lambda html: [int(x) for x in html.split(",") if x]
    try:
        pages = fetcher.preview_pages("busy", 100, parse_ids, enough=lambda got: len(got) >= 8, hard_max=300)
        assert len(pages) == 8                       # went past max_posts until enough() said yes
        pages_served.clear()
        pages = fetcher.preview_pages("busy", 100, parse_ids, enough=lambda got: False, hard_max=300)
        assert len(pages) == 15                      # but never beyond the hard limit (15 x 20 = 300)
        pages = fetcher.preview_pages("busy", 100, parse_ids)
        assert len(pages) == 5                       # without enough(): old behaviour
    finally:
        fetcher.close()
