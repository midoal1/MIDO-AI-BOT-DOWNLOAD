import asyncio
import logging
import os
import sys

from aiohttp import web
from aiogram import Bot, Dispatcher

from config import BOT_TOKEN, validate_config
from handlers import router


# Ensure UTF-8 output encoding on Windows console
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        reconfigure = getattr(sys.stdout, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")
    except Exception:
        pass


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)


async def health_check(request: web.Request) -> web.Response:
    """Health-check endpoint required by Render Web Service."""
    return web.Response(text="MIDO AI BOT is running")


async def start_web_server() -> web.AppRunner:
    """Start a minimal HTTP server so Render can detect an open port."""
    app = web.Application()

    app.router.add_get("/", health_check)
    app.router.add_get("/health", health_check)

    runner = web.AppRunner(app)
    await runner.setup()

    port = int(os.environ.get("PORT", "10000"))

    site = web.TCPSite(
        runner,
        host="0.0.0.0",
        port=port,
    )

    await site.start()

    logging.info("Web server started on port %s", port)

    return runner


async def main() -> None:
    if not validate_config():
        sys.exit(1)

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    dp.include_router(router)

    web_runner = None

    try:
        # Start HTTP server required by Render Web Service
        web_runner = await start_web_server()

        # Delete webhook and drop old Telegram updates
        await bot.delete_webhook(drop_pending_updates=True)

        logging.info("MIDO AI BOT started")
        logging.info("Starting Telegram polling...")

        # Start Telegram bot using long polling
        await dp.start_polling(bot)

    finally:
        logging.info("Shutting down MIDO AI BOT...")

        await bot.session.close()

        if web_runner is not None:
            await web_runner.cleanup()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("MIDO AI BOT stopped")