"""Bot logic tests without Telegram: SQLite in memory + fake message/bot/queue objects."""

import json
from types import SimpleNamespace

import pytest
import pytest_asyncio

from app import repo
from app.bot.handlers import start_check
from app.channel_input import ChannelRequest, parse_price, parse_text
from app.config import Settings
from app.db import Check, User, init_db, make_engine, make_sessionmaker
from app.i18n import LOCALES_DIR, pick_language, t
from app.products import PACKS, invoice_payload, parse_payload
from app.render import cpm, full, summary
from app.worker.main import classify

REPORT = {
    "channel": {"username": "demo", "title": "Demo", "subscribers": 10000, "verified": False, "preview_available": True},
    "verdict": "yellow", "confidence": "high", "posts_analyzed": 100, "mature_posts": 90,
    "first_post": "2026-10-01T00:00:00+00:00", "last_post": "2026-11-20T00:00:00+00:00",
    "posts_per_day": 1.6, "median_views": 2000, "mean_views": 2100, "err": 0.2, "views_cv": 0.3,
    "reaction_rate": 0.02, "ad_share": 0.1, "ad_median_views": 1800, "promoted_channels": [["partner", 2]],
    "forwarded_share": 0.0, "price": None, "cpm": None, "err_factor": 0.75,
    "flags": [{"level": "green", "code": "good_err", "params": {"pct": 20.0}},
              {"level": "yellow", "code": "frequent_posting", "params": {"ppd": 1.6}}],
    "top_posts": [{"id": 10, "views": 5000}],
}


# --- fakes -------------------------------------------------------------------

class FakeBot:
    async def me(self):
        return SimpleNamespace(username="ChannelCheckerBot")


class FakeMessage:
    def __init__(self):
        self.bot = FakeBot()
        self.sent = []
        self.chat = SimpleNamespace(id=1)

    async def answer(self, text, reply_markup=None):
        self.sent.append(text)
        return SimpleNamespace(chat=SimpleNamespace(id=1), message_id=len(self.sent))


class FakeArq:
    def __init__(self):
        self.jobs, self.counters = [], {}

    async def enqueue_job(self, name, *args):
        self.jobs.append((name, args))

    async def incr(self, key):
        self.counters[key] = self.counters.get(key, 0) + 1
        return self.counters[key]

    async def expire(self, key, seconds):
        return True


@pytest_asyncio.fixture
async def sm():
    engine = make_engine("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    yield make_sessionmaker(engine)
    await engine.dispose()


SETTINGS = Settings(bot_token="x", checks_per_hour_limit=10, free_checks_on_start=1)


async def new_user(sm, uid=1, lang="en"):
    async with sm() as s:
        user, _ = await repo.get_or_create_user(s, uid, lang, 1)
        return user


# --- credits and payments ----------------------------------------------------

@pytest.mark.asyncio
async def test_reserve_free_then_paid_then_none(sm):
    await new_user(sm)
    async with sm() as s:
        await repo.add_paid_checks(s, 1, 1)
        assert await repo.reserve_credit(s, 1) == "free"
        assert await repo.reserve_credit(s, 1) == "paid"
        assert await repo.reserve_credit(s, 1) is None
        await repo.return_credit(s, 1, "paid")
        user = await s.get(User, 1)
        await s.refresh(user)
        assert user.paid_checks_left == 1


@pytest.mark.asyncio
async def test_payment_is_idempotent_and_refund_takes_checks_back(sm):
    await new_user(sm)
    async with sm() as s:
        assert await repo.record_payment(s, 1, "p5", 5, 200, "charge-1") is True
        assert await repo.record_payment(s, 1, "p5", 5, 200, "charge-1") is False  # Telegram re-sent the update
        user = await s.get(User, 1)
        await s.refresh(user)
        assert user.paid_checks_left == 5
        payment = await repo.mark_refunded(s, "charge-1")
        assert payment and payment.status == "refunded"
        await s.refresh(user)
        assert user.paid_checks_left == 0
        assert await repo.mark_refunded(s, "charge-1") is None


def test_invoice_payload_roundtrip():
    pack = PACKS["p20"]
    parsed = parse_payload(invoice_payload(pack, 42))
    assert parsed == (pack, 42)
    assert parse_payload("pack:nope:1") is None and parse_payload("garbage") is None


# --- the check flow ----------------------------------------------------------

@pytest.mark.asyncio
async def test_free_check_is_queued_then_no_credits(sm):
    user = await new_user(sm)
    msg, arq = FakeMessage(), FakeArq()
    await start_check(msg, user, ChannelRequest("demo"), sm, SETTINGS, arq)
    assert arq.jobs and arq.jobs[0][0] == "run_check"
    assert "demo" in msg.sent[-1]
    await start_check(msg, user, ChannelRequest("other_channel"), sm, SETTINGS, arq)
    assert msg.sent[-1] == t("en", "no_credits")
    assert len(arq.jobs) == 1


@pytest.mark.asyncio
async def test_own_repeat_is_free_and_cache_skips_the_queue(sm):
    user = await new_user(sm, 1)
    other = await new_user(sm, 2, "ru")
    async with sm() as s:
        await repo.create_check(s, user_id=1, channel_username="demo", status="ok", verdict="yellow",
                                report=REPORT, credit_kind="free")
    msg, arq = FakeMessage(), FakeArq()
    # same user, same channel: free repeat, no credit spent, nothing queued
    await start_check(msg, user, ChannelRequest("demo"), sm, SETTINGS, arq)
    assert t("en", "repeat_free_note") in msg.sent[-1] and not arq.jobs
    # another user: served from cache, one credit spent, nothing queued
    await start_check(msg, other, ChannelRequest("demo", price=60), sm, SETTINGS, arq)
    assert "⚡" in msg.sent[-1] and "30,0" in msg.sent[-1] and not arq.jobs  # ru user: decimal comma
    async with sm() as s:
        assert (await s.get(User, 2)).free_checks_left == 0


@pytest.mark.asyncio
async def test_rate_limit(sm):
    user = await new_user(sm)
    msg, arq = FakeMessage(), FakeArq()
    limited = Settings(bot_token="x", checks_per_hour_limit=1)
    await start_check(msg, user, ChannelRequest("aaaa_one"), sm, limited, arq)
    await start_check(msg, user, ChannelRequest("bbbb_two"), sm, limited, arq)
    assert msg.sent[-1] == t("en", "rate_limited")


# --- input, rendering, locales, worker mapping ------------------------------

@pytest.mark.parametrize("text,channel,price", [
    ("@durov", "durov", None), ("https://t.me/durov", "durov", None), ("t.me/s/durov/123", "durov", None),
    ("@durov 50", "durov", 50.0), ("durov 1 500 руб", "durov", 1500.0), ("@durov 49.90$", "durov", 49.9),
])
def test_parse_text(text, channel, price):
    req = parse_text(text)
    assert req.username == channel and req.price == price


@pytest.mark.parametrize("text", ["hello there", "", "https://t.me/+AbCdEf", "@ab"])
def test_parse_text_rejects(text):
    assert parse_text(text) is None


def test_parse_price():
    assert parse_price("1 200,50") == 1200.5 and parse_price("abc") is None and parse_price("0") is None


def test_render_summary_and_full_both_languages():
    assert cpm(REPORT, 60) == 30.0
    for lang, price_text in (("en", "30.0"), ("ru", "30,0")):
        short = summary(REPORT, lang, 60)
        long = full(REPORT, lang, 60)
        assert "Demo" in short and price_text in short and "2 000" in short
        assert "@partner" in long and "t.me/demo/10" in long
    assert "Есть сомнения" in summary(REPORT, "ru") and "Mixed signals" in summary(REPORT, "en")
    assert summary(REPORT, "xx").startswith("📊")  # unknown language falls back to English


def test_locales_have_the_same_keys_and_valid_placeholders():
    files = sorted(LOCALES_DIR.glob("*.json"))
    keys = [set(json.loads(f.read_text(encoding="utf-8"))) for f in files]
    assert len(files) >= 2 and all(k == keys[0] for k in keys)


def test_pick_language():
    assert pick_language("ru") == "ru" and pick_language("en-US") == "en" and pick_language("pt-br") == "en"
    assert pick_language(None) == "en"


def test_classify_engine_results():
    assert classify(REPORT, None) is None
    no_preview = {"channel": {"preview_available": False, "subscribers": 500}}
    a_person = {"channel": {"preview_available": False, "subscribers": None}}
    assert classify(no_preview, None) == "error_no_preview"
    assert classify(a_person, None) == "error_private"
    assert classify(None, Exception("Channel not found. Check the username.")) == "error_not_found"
    assert classify(None, Exception("Network error while loading")) == "error_network"
    assert classify(None, Exception("boom")) == "error_generic"


# --- worker --------------------------------------------------------------------

class FakeWorkerBot(FakeBot):
    def __init__(self):
        self.edits = []

    async def edit_message_text(self, chat_id, message_id, text, reply_markup=None):
        self.edits.append(text)

    async def send_message(self, chat_id, text, reply_markup=None):
        self.edits.append(text)


@pytest.mark.asyncio
async def test_worker_success_saves_report_and_snapshot(sm, monkeypatch):
    import app.worker.main as worker
    from app.db import ChannelSnapshot
    from sqlalchemy import select
    await new_user(sm)
    async with sm() as s:
        assert await repo.reserve_credit(s, 1) == "free"
        check = await repo.create_check(s, user_id=1, channel_username="demo", status="queued",
                                        credit_kind="free", chat_id=1, message_id=5)
    monkeypatch.setattr(worker, "run_engine", lambda channel, max_posts, price: REPORT)
    bot = FakeWorkerBot()
    await worker.run_check({"bot": bot, "sessionmaker": sm}, check.id)
    assert "Mixed signals" in bot.edits[-1]
    async with sm() as s:
        saved = await s.get(Check, check.id)
        assert saved.status == "ok" and saved.verdict == "yellow"
        assert (await s.execute(select(ChannelSnapshot))).scalars().first().subscribers == 10000
        assert (await s.get(User, 1)).free_checks_left == 0  # spent only because the report was delivered


@pytest.mark.asyncio
async def test_worker_error_returns_the_credit(sm, monkeypatch):
    import app.worker.main as worker
    from tgcheck.fetch import FetchError
    await new_user(sm)
    async with sm() as s:
        await repo.reserve_credit(s, 1)
        check = await repo.create_check(s, user_id=1, channel_username="ghost_channel", status="queued",
                                        credit_kind="free", chat_id=1, message_id=5)

    def boom(channel, max_posts, price):
        raise FetchError("Channel not found. Check the username.")

    monkeypatch.setattr(worker, "run_engine", boom)
    bot = FakeWorkerBot()
    await worker.run_check({"bot": bot, "sessionmaker": sm}, check.id)
    assert bot.edits[-1] == t("en", "error_not_found", channel="ghost_channel")
    async with sm() as s:
        assert (await s.get(Check, check.id)).status == "error"
        assert (await s.get(User, 1)).free_checks_left == 1


# --- UX: demo, start buttons, keyboards, formats, link previews ---------------

def _callbacks(markup):
    return [b.callback_data for row in markup.inline_keyboard for b in row if b.callback_data]


@pytest.mark.asyncio
async def test_demo_fresh_check_does_not_spend_the_free_check(sm):
    user = await new_user(sm)
    msg, arq = FakeMessage(), FakeArq()
    await start_check(msg, user, ChannelRequest("durov"), sm, SETTINGS, arq, demo=True)
    assert arq.jobs and arq.jobs[0][0] == "run_check"
    async with sm() as s:
        assert (await s.get(User, 1)).free_checks_left == 1
        check = await s.get(Check, arq.jobs[0][1][0])
        assert check.credit_kind == "none"


@pytest.mark.asyncio
async def test_demo_from_cache_is_free_and_has_no_cache_note(sm):
    await new_user(sm, 2)
    user = await new_user(sm, 1)
    async with sm() as s:
        await repo.create_check(s, user_id=2, channel_username="durov", status="ok", verdict="yellow",
                                report=REPORT, credit_kind="free")
    msg, arq = FakeMessage(), FakeArq()
    await start_check(msg, user, ChannelRequest("durov"), sm, SETTINGS, arq, demo=True)
    assert not arq.jobs and "⚡" not in msg.sent[-1] and msg.sent[-1].startswith("📊")
    async with sm() as s:
        assert (await s.get(User, 1)).free_checks_left == 1
    # the real free check is still there for the user's own channel
    await start_check(msg, user, ChannelRequest("my_channel"), sm, SETTINGS, arq)
    assert arq.jobs


@pytest.mark.asyncio
async def test_worker_error_on_demo_does_not_add_credits(sm, monkeypatch):
    import app.worker.main as worker
    from tgcheck.fetch import FetchError
    await new_user(sm)
    async with sm() as s:
        check = await repo.create_check(s, user_id=1, channel_username="durov", status="queued",
                                        credit_kind="none", chat_id=1, message_id=5)

    def boom(channel, max_posts, price):
        raise FetchError("Network error while loading")

    monkeypatch.setattr(worker, "run_engine", boom)
    await worker.run_check({"bot": FakeWorkerBot(), "sessionmaker": sm}, check.id)
    async with sm() as s:
        user = await s.get(User, 1)
        assert user.free_checks_left == 1 and user.paid_checks_left == 0


def test_start_message_offers_the_shop_only_when_the_balance_is_empty():
    from app.bot.handlers import start_message
    empty = User(id=1, language="ru", free_checks_left=0, paid_checks_left=0)
    text, kb = start_message(empty)
    assert _callbacks(kb) == ["buymenu", "example"] and t("ru", "start_empty") in text
    fresh = User(id=2, language="ru", free_checks_left=1, paid_checks_left=0)
    text, kb = start_message(fresh)
    assert _callbacks(kb) == ["example"] and "бесплатная проверка" in text
    paid = User(id=3, language="en", free_checks_left=0, paid_checks_left=3)
    text, kb = start_message(paid)
    assert _callbacks(kb) == ["example"] and "3 paid" in text


def test_keyboards_under_full_report_and_after_payment():
    from app.keyboards import check_channel_keyboard, full_keyboard
    kb = full_keyboard("ru", "ChannelCheckerBot")
    assert _callbacks(kb) == ["another"]
    assert any(b.url and "ChannelCheckerBot" in b.url for row in kb.inline_keyboard for b in row)
    assert _callbacks(check_channel_keyboard("en")) == ["another"]


def test_russian_dates_and_decimal_commas():
    ru, en = full(REPORT, "ru"), full(REPORT, "en")
    assert "01.10.2026 – 20.11.2026" in ru and "20,0%" in ru and "2,00%" in ru and "1,6" in ru
    assert "2026-10-01 → 2026-11-20" in en and "20.0%" in en and "2.00%" in en
    assert "видят 20,0% подписчиков" in ru and "reaches 20.0% of subscribers" in en


def test_bot_disables_link_previews_by_default():
    from app.botfactory import make_bot
    bot = make_bot("123456:ABCdefGhIJKlmnoPQRstuVWXyz")
    assert bot.default.link_preview_is_disabled is True


# --- small fixes after launch: plural forms, how to buy Stars ---------------------------------

@pytest.mark.parametrize("n,word", [(1, "проверка"), (2, "проверки"), (5, "проверок"), (11, "проверок"),
                                    (20, "проверок"), (21, "проверка"), (22, "проверки"), (112, "проверок")])
def test_russian_plural(n, word):
    from app.i18n import plural
    assert plural("ru", "w_checks", n) == word


def test_english_plural_and_paid_message():
    from app.i18n import plural
    assert plural("en", "w_checks", 1) == "check" and plural("en", "w_checks", 5) == "checks"
    text = t("ru", "paid_ok", checks=1, checks_word=plural("ru", "w_checks", 1), paid=1)
    assert "+1 проверка." in text


def test_russian_buy_prompt_explains_how_to_get_stars():
    assert "за рубли" in t("ru", "buy_prompt") and "за рубли" in t("ru", "no_credits")
