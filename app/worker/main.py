"""Worker: runs channel checks from the Redis queue.
Start: arq app.worker.main.WorkerSettings"""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot
from arq.connections import RedisSettings

from tgcheck.__main__ import check as engine_check, collect_online
from tgcheck.fetch import FetchError, normalize_channel
from tgcheck.report import to_dict

from .. import repo
from ..config import get_settings
from ..db import Check, User, init_db, make_engine, make_sessionmaker
from ..i18n import t
from ..keyboards import report_keyboard
from ..render import summary

log = logging.getLogger(__name__)
settings = get_settings()


def run_engine(channel: str, max_posts: int, price: float | None) -> dict:
    """Blocking: downloads public pages and analyzes them (runs in a thread)."""
    name = normalize_channel(channel)
    card_html, pages = collect_online(name, max_posts, None)
    return to_dict(engine_check(name, card_html, pages, max_posts, price))


def classify(report: dict | None, exc: Exception | None) -> str | None:
    """Maps engine results and errors to user-facing error codes. None = success."""
    if exc is not None:
        text = str(exc).lower()
        if "not found" in text:
            return "error_not_found"
        if "network" in text:
            return "error_network"
        if "private" in text or "doesn't look like" in text:
            return "error_private"
        return "error_generic"
    channel = (report or {}).get("channel") or {}
    if not channel.get("preview_available", True):
        return "error_private" if channel.get("subscribers") is None else "error_no_preview"
    return None




async def edit(bot: Bot, check: Check, text: str, markup=None) -> None:
    if not check.chat_id or not check.message_id:
        return
    try:
        await bot.edit_message_text(chat_id=check.chat_id, message_id=check.message_id, text=text, reply_markup=markup)
    except Exception:  # message deleted or not modified: send a new one instead
        await bot.send_message(check.chat_id, text, reply_markup=markup)


async def run_check(ctx, check_id: int) -> None:
    bot: Bot = ctx["bot"]
    sessionmaker = ctx["sessionmaker"]
    async with sessionmaker() as s:
        check = await s.get(Check, check_id)
        if not check or check.status != "queued":
            return
        user = await s.get(User, check.user_id)
        lang = user.language if user else "en"
        await edit(bot, check, t(lang, "checking_loading", channel=check.channel_username))

        report, error = None, None
        try:
            report = await asyncio.to_thread(run_engine, check.channel_username, settings.max_posts, check.price)
        except FetchError as exc:
            error = exc
        except Exception as exc:  # unexpected: alert the admin, never charge the user
            error = exc
            log.exception("check %s failed", check_id)
            if settings.alert_chat_id:
                await bot.send_message(settings.alert_chat_id, f"⚠️ check {check_id} @{check.channel_username}: {exc!r}"[:4000])

        code = classify(report, error)
        if code:
            await repo.finish_check_error(s, check, code, str(error or "no preview"))
            await repo.return_credit(s, check.user_id, check.credit_kind)
            await edit(bot, check, t(lang, code, channel=check.channel_username))
            return

        await repo.finish_check_ok(s, check, report)
        me = await bot.me()
        await edit(bot, check, summary(report, lang, check.price), report_keyboard(lang, check.id, me.username))


async def startup(ctx) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    engine = make_engine(settings.database_url)
    await init_db(engine)
    ctx["engine"] = engine
    ctx["sessionmaker"] = make_sessionmaker(engine)
    ctx["bot"] = Bot(settings.bot_token)


async def shutdown(ctx) -> None:
    await ctx["bot"].session.close()
    await ctx["engine"].dispose()


class WorkerSettings:
    functions = [run_check]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_jobs = 1          # one channel at a time: be gentle with t.me at the start
    job_timeout = 180
    max_tries = 1         # a failed check is reported to the user, not retried silently
