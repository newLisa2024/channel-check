"""One place to create the Bot, so the bot and the worker share the same defaults."""

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties


def make_bot(token: str) -> Bot:
    # Reports contain t.me links to top posts; without this Telegram attaches a big preview of a stranger's post.
    return Bot(token, default=DefaultBotProperties(link_preview_is_disabled=True))
