"""Inline keyboards shared by the bot and the worker."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from .i18n import t


def report_keyboard(lang: str, check_id: int, bot_username: str | None) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=t(lang, "btn_full"), callback_data=f"full:{check_id}")],
            [InlineKeyboardButton(text=t(lang, "btn_another"), callback_data="another")]]
    if bot_username:
        rows.append([InlineKeyboardButton(text=t(lang, "btn_share"),
                                          url=f"https://t.me/share/url?url=https://t.me/{bot_username}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
