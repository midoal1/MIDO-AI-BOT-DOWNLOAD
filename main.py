import asyncio
import logging
import os
import sys

from aiohttp import web, ClientSession, ClientTimeout
from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramNetworkError

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

logger = logging.getLogger(__name__)


async def health_check(request: web.Request) -> web.Response:
    """Health-check endpoint required by Render Web Service."""
    return web.Response(text="MIDO AI BOT is running")


async def keep_alive() -> None:
    """Ping our own health endpoint every 13 minutes to prevent Render sleeping."""
    port = int(os.environ.get("PORT", "10000"))
    url = f"http://127.0.0.1:{port}/health"
    timeout = ClientTimeout(total=15)
    # Wait for the HTTP server to fully start
    await asyncio.sleep(20)
    while True:
        try:
            async with ClientSession(timeout=timeout) as session:
                async with session.get(url) as resp:
                    logger.info("Keep-alive ping OK — status: %s", resp.status)
        except Exception as e:
            logger.warning("Keep-alive ping failed: %s", e)
        await asyncio.sleep(13 * 60)  # every 13 minutes


async def start_web_server() -> web.AppRunner:
    """Start a minimal HTTP server so Render can detect an open port."""
    app = web.Application()
    app.router.add_get("/", health_check)
    app.router.add_get("/health", health_check)

    runner = web.AppRunner(app)
    await runner.setup()

    port = int(os.environ.get("PORT", "10000"))
    site = web.TCPSite(runner, host="0.0.0.0", port=port)
    await site.start()

    logger.info("Web server started on port %s", port)
    return runner


async def run_bot_with_retry(bot: Bot, dp: Dispatcher) -> None:
    """Run Telegram polling with automatic restart on network errors."""
    retry_delay = 5
    while True:
        try:
            logger.info("Starting Telegram polling...")
            await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
        except TelegramNetworkError as e:
            logger.error("Network error: %s — retrying in %ds...", e, retry_delay)
            await asyncio.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, 60)
        except Exception as e:
            logger.error("Unexpected error: %s — retrying in %ds...", e, retry_delay)
            await asyncio.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, 60)
        else:
            # polling ended cleanly
            break


async def main() -> None:
    if not validate_config():
        sys.exit(1)

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)

    web_runner = None

    try:
        # 1. Start HTTP server (required by Render to detect the open port)
        web_runner = await start_web_server()

        # 2. Start keep-alive background task
        asyncio.create_task(keep_alive())

        # 3. Clear any pending Telegram updates
        await bot.delete_webhook(drop_pending_updates=True)

        logger.info("MIDO AI BOT started successfully!")

        # 4. Run polling with auto-restart on crash
        await run_bot_with_retry(bot, dp)

    finally:
        logger.info("Shutting down MIDO AI BOT...")
        try:
            await bot.session.close()
        except Exception:
            pass
        if web_runner is not None:
            await web_runner.cleanup()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("MIDO AI BOT stopped.")