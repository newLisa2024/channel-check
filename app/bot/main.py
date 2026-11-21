"""Bot entry point: python -m app.bot.main"""

from __future__ import annotations

import asyncio
import logging

from aiogram import Dispatcher
from aiogram.fsm.storage.redis import RedisStorage
from arq import create_pool
from arq.connections import RedisSettings

from ..botfactory import make_bot
from ..config import get_settings
from ..db import init_db, make_engine, make_sessionmaker
from .handlers import router


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = get_settings()
    if not settings.bot_token:
        raise SystemExit("BOT_TOKEN is not set")

    engine = make_engine(settings.database_url)
    await init_db(engine)
    sessionmaker = make_sessionmaker(engine)
    arq = await create_pool(RedisSettings.from_dsn(settings.redis_url))

    bot = make_bot(settings.bot_token)
    dp = Dispatcher(storage=RedisStorage.from_url(settings.redis_url),
                    sessionmaker=sessionmaker, settings=settings, arq=arq)
    dp.include_router(router)
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await arq.aclose()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
