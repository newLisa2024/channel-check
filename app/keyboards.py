"""Inline keyboards shared by the bot and the worker."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from .i18n import t


def _tail_rows(lang: str, bot_username: str | None) -> list[list[InlineKeyboardButton]]:
    rows = [[InlineKeyboardButton(text=t(lang, "btn_another"), callback_data="another")]]
    if bot_username:
        rows.append([InlineKeyboardButton(text=t(lang, "btn_share"),
                                          url=f"https://t.me/share/url?url=https://t.me/{bot_username}")])
    return rows


def report_keyboard(lang: str, check_id: int, bot_username: str | None) -> InlineKeyboardMarkup:
    """Under the short report: full report, check another, share."""
    rows = [[InlineKeyboardButton(text=t(lang, "btn_full"), callback_data=f"full:{check_id}")]]
    return InlineKeyboardMarkup(inline_keyboard=rows + _tail_rows(lang, bot_username))


def full_keyboard(lang: str, bot_username: str | None) -> InlineKeyboardMarkup:
    """Under the full report: check another, share."""
    return InlineKeyboardMarkup(inline_keyboard=_tail_rows(lang, bot_username))


def check_channel_keyboard(lang: str) -> InlineKeyboardMarkup:
    """After a successful payment: go straight to checking a channel."""
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=t(lang, "btn_check_channel"),
                                                                       callback_data="another")]])
