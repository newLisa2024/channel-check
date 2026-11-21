"""Telegram handlers. Heavy work (loading a channel) is queued to the worker; the bot only talks."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice, Message, PreCheckoutQuery

from .. import repo
from ..channel_input import ChannelRequest, from_forward, parse_price, parse_text
from ..config import Settings
from ..db import Check, User
from ..i18n import available, pick_language, t
from ..keyboards import report_keyboard
from ..products import PACKS, invoice_payload, parse_payload
from ..ratelimit import allow
from ..render import full, summary

log = logging.getLogger(__name__)
router = Router()
EXAMPLE_CHANNEL = "durov"


class PriceInput(StatesGroup):
    waiting = State()


# --- helpers -----------------------------------------------------------------

async def ensure_user(sessionmaker, settings: Settings, tg_user, referred_by: int | None = None) -> tuple[User, bool]:
    async with sessionmaker() as s:
        return await repo.get_or_create_user(s, tg_user.id, pick_language(tg_user.language_code),
                                             settings.free_checks_on_start, referred_by)


def buy_keyboard(lang: str) -> InlineKeyboardMarkup:
    rows = []
    for pack in PACKS.values():
        label = t(lang, "pack_label_one", stars=pack.stars) if pack.checks == 1 else t(lang, "pack_label", checks=pack.checks, stars=pack.stars)
        rows.append([InlineKeyboardButton(text=label, callback_data=f"buy:{pack.key}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)




def price_keyboard(lang: str, channel: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(lang, "btn_check_now"), callback_data=f"check:{channel}")],
        [InlineKeyboardButton(text=t(lang, "btn_add_price"), callback_data=f"price:{channel}")],
    ])


async def bot_username(message_or_bot) -> str | None:
    bot = getattr(message_or_bot, "bot", message_or_bot)
    me = await bot.me()
    return me.username


# --- start / info ------------------------------------------------------------

@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject, sessionmaker, settings: Settings):
    referred_by = None
    if command.args and command.args.startswith("ref") and command.args[3:].isdigit():
        referred_by = int(command.args[3:])
    user, created = await ensure_user(sessionmaker, settings, message.from_user, referred_by)
    async with sessionmaker() as s:
        await repo.log_event(s, user.id, "start", created=created, ref=referred_by)
    lang = user.language
    second = (t(lang, "start_free", n=user.free_checks_left) if user.free_checks_left and not user.paid_checks_left
              else t(lang, "start_balance", free=user.free_checks_left, paid=user.paid_checks_left))
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=t(lang, "btn_example"), callback_data="example")]])
    await message.answer(f"{t(lang, 'start_greeting')}\n\n{second}", reply_markup=kb)


@router.message(Command("help"))
async def cmd_help(message: Message, sessionmaker, settings: Settings):
    user, _ = await ensure_user(sessionmaker, settings, message.from_user)
    await message.answer(t(user.language, "help"))


@router.message(Command("terms"))
async def cmd_terms(message: Message, sessionmaker, settings: Settings):
    user, _ = await ensure_user(sessionmaker, settings, message.from_user)
    await message.answer(t(user.language, "terms"))


@router.message(Command("paysupport"))
async def cmd_paysupport(message: Message, sessionmaker, settings: Settings):
    user, _ = await ensure_user(sessionmaker, settings, message.from_user)
    if settings.support_contact:
        await message.answer(t(user.language, "paysupport", contact=settings.support_contact))
    else:
        await message.answer(t(user.language, "paysupport_nocontact"))


@router.message(Command("balance"))
async def cmd_balance(message: Message, sessionmaker, settings: Settings):
    user, _ = await ensure_user(sessionmaker, settings, message.from_user)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=t(user.language, "btn_buy"), callback_data="buymenu")]])
    await message.answer(t(user.language, "balance", free=user.free_checks_left, paid=user.paid_checks_left), reply_markup=kb)


@router.message(Command("language"))
async def cmd_language(message: Message, sessionmaker, settings: Settings):
    user, _ = await ensure_user(sessionmaker, settings, message.from_user)
    names = {"en": "English", "ru": "Русский"}
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=names.get(code, code), callback_data=f"lang:{code}")]
                                               for code in available()])
    await message.answer(t(user.language, "language_prompt"), reply_markup=kb)


@router.callback_query(F.data.startswith("lang:"))
async def cb_language(call: CallbackQuery, sessionmaker):
    code = call.data.split(":", 1)[1]
    if code not in available():
        await call.answer()
        return
    async with sessionmaker() as s:
        await repo.set_language(s, call.from_user.id, code)
    await call.message.edit_text(t(code, "language_set"))
    await call.answer()


@router.message(Command("check"))
async def cmd_check(message: Message, sessionmaker, settings: Settings):
    user, _ = await ensure_user(sessionmaker, settings, message.from_user)
    await message.answer(t(user.language, "not_a_channel"))


@router.callback_query(F.data == "another")
async def cb_another(call: CallbackQuery, sessionmaker, settings: Settings):
    user, _ = await ensure_user(sessionmaker, settings, call.from_user)
    await call.message.answer(t(user.language, "not_a_channel"))
    await call.answer()


# --- channel input -----------------------------------------------------------

@router.callback_query(F.data == "example")
async def cb_example(call: CallbackQuery, sessionmaker, settings: Settings):
    user, _ = await ensure_user(sessionmaker, settings, call.from_user)
    await call.message.answer(t(user.language, "ask_price", channel=EXAMPLE_CHANNEL),
                              reply_markup=price_keyboard(user.language, EXAMPLE_CHANNEL))
    await call.answer()


@router.message(StateFilter(PriceInput.waiting), F.text)
async def on_price(message: Message, state: FSMContext, sessionmaker, settings: Settings, arq):
    user, _ = await ensure_user(sessionmaker, settings, message.from_user)
    price = parse_price(message.text)
    if price is None:
        await message.answer(t(user.language, "price_invalid"))
        return
    data = await state.get_data()
    await state.clear()
    await start_check(message, user, ChannelRequest(data["channel"], price), sessionmaker, settings, arq)


@router.message(F.forward_origin)
async def on_forward(message: Message, sessionmaker, settings: Settings):
    user, _ = await ensure_user(sessionmaker, settings, message.from_user)
    request = from_forward(message)
    if not request:
        await message.answer(t(user.language, "not_a_channel"))
        return
    await message.answer(t(user.language, "ask_price", channel=request.username),
                         reply_markup=price_keyboard(user.language, request.username))


@router.message(F.text & ~F.text.startswith("/"))
async def on_text(message: Message, sessionmaker, settings: Settings, arq):
    user, _ = await ensure_user(sessionmaker, settings, message.from_user)
    request = parse_text(message.text)
    if not request:
        key = "private_link" if ("t.me/+" in message.text or "joinchat" in message.text) else "not_a_channel"
        await message.answer(t(user.language, key))
        return
    if request.price is not None:
        await start_check(message, user, request, sessionmaker, settings, arq)
        return
    await message.answer(t(user.language, "ask_price", channel=request.username),
                         reply_markup=price_keyboard(user.language, request.username))


@router.callback_query(F.data.startswith("check:"))
async def cb_check(call: CallbackQuery, sessionmaker, settings: Settings, arq):
    user, _ = await ensure_user(sessionmaker, settings, call.from_user)
    await call.answer()
    await start_check(call.message, user, ChannelRequest(call.data.split(":", 1)[1]), sessionmaker, settings, arq)


@router.callback_query(F.data.startswith("price:"))
async def cb_price(call: CallbackQuery, state: FSMContext, sessionmaker, settings: Settings):
    user, _ = await ensure_user(sessionmaker, settings, call.from_user)
    await state.set_state(PriceInput.waiting)
    await state.update_data(channel=call.data.split(":", 1)[1])
    await call.message.answer(t(user.language, "price_prompt"))
    await call.answer()


# --- the check itself --------------------------------------------------------

async def start_check(message: Message, user: User, request: ChannelRequest, sessionmaker, settings: Settings, arq):
    """message = where to answer (the user's chat). Spends a check only when a report is delivered."""
    lang = user.language
    channel = request.username
    async with sessionmaker() as s:
        await repo.log_event(s, user.id, "check_requested", channel=channel, price=request.price)

        # 1. The same user checked this channel recently: show it again for free.
        own = await repo.own_recent_check(s, user.id, channel, settings.own_repeat_hours)
        if own and own.report:
            await message.answer(f"{t(lang, 'repeat_free_note')}\n\n{summary(own.report, lang, request.price)}",
                                 reply_markup=report_keyboard(lang, own.id, await bot_username(message)))
            return

        if not await allow(arq, user.id, settings.checks_per_hour_limit):
            await message.answer(t(lang, "rate_limited"))
            return

        kind = await repo.reserve_credit(s, user.id)
        if not kind:
            await repo.log_event(s, user.id, "invoice_shown", where="no_credits")
            await message.answer(t(lang, "no_credits"), reply_markup=buy_keyboard(lang))
            return

        # 2. Someone checked this channel within cache_hours: reuse the result, no new load of t.me.
        cached = await repo.cached_check(s, channel, settings.cache_hours)
        if cached and cached.report:
            check = await repo.create_check(s, user_id=user.id, channel_username=channel, price=request.price,
                                            status="ok", verdict=cached.verdict, report=cached.report,
                                            from_cache=True, credit_kind=kind)
            await message.answer(f"{t(lang, 'cached_note', hours=settings.cache_hours)}\n\n{summary(check.report, lang, request.price)}",
                                 reply_markup=report_keyboard(lang, check.id, await bot_username(message)))
            return

        # 3. A fresh check: queue it; the worker edits the progress message with the result.
        check = await repo.create_check(s, user_id=user.id, channel_username=channel, price=request.price,
                                        status="queued", credit_kind=kind)
        progress = await message.answer(t(lang, "checking", channel=channel))
        check.chat_id = progress.chat.id
        check.message_id = progress.message_id
        await s.commit()
    await arq.enqueue_job("run_check", check.id)


@router.callback_query(F.data.startswith("full:"))
async def cb_full(call: CallbackQuery, sessionmaker, settings: Settings):
    user, _ = await ensure_user(sessionmaker, settings, call.from_user)
    try:
        check_id = int(call.data.split(":", 1)[1])
    except ValueError:
        await call.answer()
        return
    async with sessionmaker() as s:
        check = await s.get(Check, check_id)
        if not check or check.user_id != user.id or not check.report:
            await call.answer()
            return
        await repo.log_event(s, user.id, "report_opened", check_id=check_id)
    await call.message.answer(full(check.report, user.language, check.price))
    await call.answer()


# --- payments (Telegram Stars, currency XTR) ---------------------------------

@router.message(Command("buy"))
async def cmd_buy(message: Message, sessionmaker, settings: Settings):
    user, _ = await ensure_user(sessionmaker, settings, message.from_user)
    await message.answer(t(user.language, "no_credits"), reply_markup=buy_keyboard(user.language))


@router.callback_query(F.data == "buymenu")
async def cb_buymenu(call: CallbackQuery, sessionmaker, settings: Settings):
    user, _ = await ensure_user(sessionmaker, settings, call.from_user)
    await call.message.answer(t(user.language, "no_credits"), reply_markup=buy_keyboard(user.language))
    await call.answer()


@router.callback_query(F.data.startswith("buy:"))
async def cb_buy(call: CallbackQuery, sessionmaker, settings: Settings):
    user, _ = await ensure_user(sessionmaker, settings, call.from_user)
    pack = PACKS.get(call.data.split(":", 1)[1])
    if not pack:
        await call.answer()
        return
    lang = user.language
    title = t(lang, "invoice_title_one") if pack.checks == 1 else t(lang, "invoice_title", checks=pack.checks)
    await call.message.answer_invoice(
        title=title, description=t(lang, "invoice_desc"), payload=invoice_payload(pack, user.id),
        currency="XTR", prices=[LabeledPrice(label=title, amount=pack.stars)],
    )
    async with sessionmaker() as s:
        await repo.log_event(s, user.id, "invoice_shown", pack=pack.key)
    await call.answer()


@router.pre_checkout_query()
async def on_pre_checkout(query: PreCheckoutQuery):
    parsed = parse_payload(query.invoice_payload)
    ok = bool(parsed) and parsed[1] == query.from_user.id and query.currency == "XTR" and query.total_amount == parsed[0].stars
    if ok:
        await query.answer(ok=True)
    else:
        await query.answer(ok=False, error_message="Invoice is outdated, please open /buy again.")


@router.message(F.successful_payment)
async def on_paid(message: Message, sessionmaker, settings: Settings):
    payment = message.successful_payment
    parsed = parse_payload(payment.invoice_payload)
    user, _ = await ensure_user(sessionmaker, settings, message.from_user)
    if not parsed:
        log.error("Unknown payload in successful payment: %s", payment.invoice_payload)
        return
    pack, _ = parsed
    async with sessionmaker() as s:
        fresh = await repo.record_payment(s, user.id, pack.key, pack.checks, payment.total_amount,
                                          payment.telegram_payment_charge_id)
        if fresh:
            await repo.log_event(s, user.id, "paid", pack=pack.key, stars=payment.total_amount)
        user = await s.get(User, user.id)
    await message.answer(t(user.language, "paid_ok", checks=pack.checks, paid=user.paid_checks_left))


@router.message(Command("refund"))
async def cmd_refund(message: Message, command: CommandObject, sessionmaker, settings: Settings):
    """Admin only: /refund <telegram_payment_charge_id>"""
    if message.from_user.id not in settings.admin_id_set:
        return
    lang = pick_language(message.from_user.language_code)
    charge_id = (command.args or "").strip()
    if not charge_id:
        await message.answer(t(lang, "refund_usage"))
        return
    async with sessionmaker() as s:
        from sqlalchemy import select
        from ..db import Payment
        payment = (await s.execute(select(Payment).where(Payment.charge_id == charge_id))).scalars().first()
        if not payment:
            await message.answer(t(lang, "refund_fail", error="payment not found"))
            return
        try:
            await message.bot.refund_star_payment(user_id=payment.user_id, telegram_payment_charge_id=charge_id)
        except Exception as exc:  # Telegram returns a readable error, e.g. already refunded
            await message.answer(t(lang, "refund_fail", error=str(exc)))
            return
        await repo.mark_refunded(s, charge_id)
    await message.answer(t(lang, "refund_ok", stars=payment.stars, user=payment.user_id))
