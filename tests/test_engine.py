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
    assert {"low_err", "uniform_views", "ad_heavy"} <= codes
