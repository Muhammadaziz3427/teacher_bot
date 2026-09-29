"""Bot bootstrap: logging, dispatcher, middleware, routers and scheduler."""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from . import __version__
from .ai_worker import setup_worker
from .config import settings
from .db import dispose, init_db
from . import db_sync
from .handlers import register_handlers
from .logging_setup import setup_logging
from .middlewares import AppContextMiddleware
from .scheduler import setup_scheduler

log = logging.getLogger("teacher_bot")


def build_bot() -> Bot:
    return Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def build_dispatcher() -> Dispatcher:
    """Dispatcher with one DB session + language/role context per update."""
    dp = Dispatcher(storage=MemoryStorage())
    context = AppContextMiddleware()
    dp.message.outer_middleware(context)
    dp.callback_query.outer_middleware(context)
    dp.chat_member.outer_middleware(context)
    dp.my_chat_member.outer_middleware(context)
    register_handlers(dp)
    return dp


async def run() -> None:
    if not settings.bot_token:
        raise SystemExit(
            "BOT_TOKEN is missing.\n"
            "Copy .env.example to .env and put your @BotFather token in it."
        )
    # Ephemeral disk (Render free): restore the database from GitHub first.
    # If it cannot be fetched we must NOT continue with an empty database —
    # the first push would overwrite every student's record on the remote.
    try:
        if await db_sync.pull_async():
            log.info("Database restored from %s", settings.db_sync_repo)
    except Exception:
        if not settings.db_path.exists():
            raise SystemExit(
                "DB sync pull failed and there is no local database — "
                "refusing to start with an empty one."
            )
        log.exception("DB sync pull failed; using the local database")

    await init_db()
    bot = build_bot()
    dp = build_dispatcher()
    scheduler = setup_scheduler(bot)
    worker = setup_worker(bot)
    worker.start()
    miniapp = None
    try:
        from .miniapp import start as start_miniapp
        miniapp = start_miniapp()
    except Exception:
        log.exception("Mini app failed to start (the bot keeps running)")
    me = await bot.get_me()
    log.info(
        "Started @%s (id=%s) · v%s · AI %s · tz %s",
        me.username, me.id, __version__,
        "ON" if settings.ai_ready else "OFF (manual grading)",
        settings.tz_name,
    )
    if not settings.ai_ready:
        log.warning("OPENAI_API_KEY is empty — homework will be saved as 'pending'.")
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await worker.stop()
        scheduler.shutdown(wait=False)
        if miniapp is not None:
            try:
                miniapp.stop()
            except Exception:
                log.exception("Mini app failed to stop")
        try:
            if await db_sync.push_async(force=True):
                log.info("Database saved to GitHub on shutdown")
        except Exception:
            log.exception("Database save on shutdown failed")
        await bot.session.close()
        await dispose()


async def main() -> None:
    setup_logging()
    await run()


if __name__ == "__main__":
    asyncio.run(main())
