"""Sets the bot's name, descriptions and command menu per language.
Run once after creating the bot, and again after changing texts:
    python -m app.bot.setup
English is the default for every language we don't list."""

from __future__ import annotations

import asyncio

from aiogram import Bot
from aiogram.types import BotCommand

from ..config import get_settings

PROFILE = {
    None: {  # default (English)
        "name": "Channel Checker: fake subscribers & real reach",
        "short": "Check any public Telegram channel before buying ads: real reach, fake signs, fair price.",
        "description": ("Before you pay for an ad in a Telegram channel, send it to me. In a minute you get:\n"
                        "• how many people will really see your post\n"
                        "• signs of fake subscribers or bought views\n"
                        "• your price per 1,000 real views\n"
                        "• a clear verdict: 🟢 real audience, 🟡 mixed signals, 🔴 likely fake\n\n"
                        "First check is free. Public channels only."),
        "commands": [("check", "Check a channel"), ("balance", "Checks left"), ("buy", "Buy checks"),
                     ("language", "Change language"), ("help", "How to read the report"),
                     ("terms", "Terms of use"), ("paysupport", "Payment support")],
    },
    "ru": {
        "name": "Проверка канала на накрутку и охват",
        "short": "Проверьте канал перед покупкой рекламы: реальный охват, накрутка, честная цена.",
        "description": ("Прежде чем платить за рекламу в Telegram-канале, пришлите его мне. За минуту вы узнаете:\n"
                        "• сколько человек реально увидят ваш пост\n"
                        "• есть ли признаки накрутки подписчиков или просмотров\n"
                        "• сколько вы платите за 1000 реальных просмотров\n"
                        "• понятный вердикт: 🟢 живая аудитория, 🟡 есть сомнения, 🔴 похоже на накрутку\n\n"
                        "Первая проверка бесплатно. Только публичные каналы."),
        "commands": [("check", "Проверить канал"), ("balance", "Сколько осталось проверок"), ("buy", "Купить проверки"),
                     ("language", "Сменить язык"), ("help", "Как читать отчёт"),
                     ("terms", "Условия использования"), ("paysupport", "Поддержка по оплатам")],
    },
}


async def main() -> None:
    bot = Bot(get_settings().bot_token)
    try:
        for lang, p in PROFILE.items():
            await bot.set_my_name(name=p["name"], language_code=lang)
            await bot.set_my_short_description(short_description=p["short"], language_code=lang)
            await bot.set_my_description(description=p["description"], language_code=lang)
            await bot.set_my_commands([BotCommand(command=c, description=d) for c, d in p["commands"]], language_code=lang)
            print(f"profile set for {lang or 'default (en)'}")
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
