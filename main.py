import asyncio
import logging
import sys

# Ensure UTF-8 output encoding on Windows console
if sys.stdout and hasattr(sys.stdout, 'reconfigure') and sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from aiogram import Bot, Dispatcher
from config import BOT_TOKEN, validate_config
from handlers import router
from admin import admin_router
from subscriptions import sub_router

import os
from aiohttp import web
from aiogram.types import BotCommand
from database import get_stats

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

async def handle_health_check(request):
    return web.Response(text="Bot is live 🚀")

async def start_dummy_web_server():
    port_str = os.getenv("PORT")
    if port_str:
        try:
            port = int(port_str)
            app = web.Application()
            app.router.add_get("/", handle_health_check)
            app.router.add_get("/health", handle_health_check)
            runner = web.AppRunner(app)
            await runner.setup()
            site = web.TCPSite(runner, "0.0.0.0", port)
            await site.start()
            logging.info(f"Health check web server running on port {port}")
        except Exception as e:
            logging.warning(f"Could not start dummy web server: {e}")

async def keep_alive_ping():
    """Self pings the server every 4 minutes to keep Render Web Service active and prevent sleep mode."""
    port_str = os.getenv("PORT")
    render_url = os.getenv("RENDER_EXTERNAL_URL")
    if not port_str and not render_url:
        return
        
    await asyncio.sleep(10)
    while True:
        try:
            target_url = render_url if render_url else f"http://127.0.0.1:{port_str}/health"
            async with aiohttp.ClientSession() as session:
                async with session.get(target_url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    logging.info(f"Keep-alive self ping to {target_url}: status {resp.status}")
        except Exception as e:
            logging.debug(f"Keep-alive ping error: {e}")
        await asyncio.sleep(240)  # Ping every 4 minutes

async def setup_bot_profile(bot: Bot):
    try:
        commands = [
            BotCommand(command="start", description="🚀 بدء استخدام البوت / Main Menu"),
            BotCommand(command="help", description="❓ دليل التعليمات / Help & Guide"),
            BotCommand(command="vip", description="⭐ باقة الـ VIP / VIP Membership"),
            BotCommand(command="stats", description="📊 إحصائيات البوت / Statistics"),
        ]
        await bot.set_my_commands(commands)

        desc_ar = (
            "🤖 أهلاً بك في بوت تنزيل الفيديوهات والصوتيات الشامل!\n\n"
            "🎬 المنصات المدعومة:\n"
            "• 🎵 TikTok (فيديوهات بدون علامة مائية + ألبومات الصور)\n"
            "• 🔴 YouTube & Shorts\n"
            "• 📸 Instagram Reels & Posts\n"
            "• 🐦 Twitter / X & Facebook\n"
            "• 📌 Pinterest وجميع مواقع الفيديوهات الأخرى!\n\n"
            "أرسل رابط أي فيديو لبدء التنزيل الفوري 🚀"
        )
        await bot.set_my_description(description=desc_ar, language_code="ar")

        desc_en = (
            "🤖 Welcome to Video & Audio Downloader Bot!\n\n"
            "🎬 Supported Platforms:\n"
            "• 🎵 TikTok (No Watermark + Photo Albums)\n"
            "• 🔴 YouTube & Shorts\n"
            "• 📸 Instagram Reels & Posts\n"
            "• 🐦 Twitter / X & Facebook\n"
            "• 📌 Pinterest & all video sites!\n\n"
            "Send any video link to download 🚀"
        )
        await bot.set_my_description(description=desc_en, language_code="en")

        stats = get_stats()
        u_count = stats.get("user_count", 0)
        short_desc = f"👥 عدد المستخدمين: {u_count} | 🎬 تنزيل الفيديوهات والصوتيات بدون علامة مائية"
        await bot.set_my_short_description(short_description=short_desc)
        logging.info("Bot profile commands and descriptions setup successfully.")
    except Exception as e:
        logging.warning(f"Could not setup bot profile metadata: {e}")

async def main():
    if not validate_config():
        sys.exit(1)
        
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(admin_router)
    dp.include_router(sub_router)
    dp.include_router(router)
    
    await start_dummy_web_server()
    asyncio.create_task(keep_alive_ping())
    await setup_bot_profile(bot)

    print("🚀 جاري تشغيل بوت تنزيل الفيديوهات والصوتيات مع نظام الاشتراكات والـ VIP...")
    print("اضغط Ctrl+C لإيقاف البوت في أي وقت.\n")
    
    while True:
        try:
            await bot.delete_webhook(drop_pending_updates=True)
            logging.info("Starting Telegram Bot long-polling...")
            await dp.start_polling(bot)
        except Exception as e:
            logging.error(f"Polling connection lost ({e}). Reconnecting in 5 seconds...")
            await asyncio.sleep(5)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("\n🛑 تم إيقاف البوت.")