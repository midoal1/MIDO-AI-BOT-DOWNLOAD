import asyncio
import logging
import sys

# Ensure UTF-8 output encoding on Windows console
if sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from aiogram import Bot, Dispatcher
from config import BOT_TOKEN, validate_config
from handlers import router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

async def main():
    if not validate_config():
        sys.exit(1)
        
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)
    
    print("🚀 جاري تشغيل بوت تنزيل الفيديوهات...")
    print("اضغط Ctrl+C لإيقاف البوت في أي وقت.\n")
    
    # Delete webhook and drop old updates
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("\n🛑 تم إيقاف البوت.")
