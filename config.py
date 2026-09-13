import os
import sys
from dotenv import load_dotenv

# Ensure UTF-8 output encoding on Windows console
if sys.stdout and hasattr(sys.stdout, 'reconfigure') and sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

def validate_config():
    if not BOT_TOKEN or BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN_HERE":
        print("\n" + "=" * 65)
        print("⚠️ خطأ: لم يتم ضبط توكن البوت (BOT_TOKEN) في ملف .env")
        print("يرجى فتح ملف .env ووضع التوكن الخاص بك من @BotFather")
        print("=" * 65 + "\n")
        return False
    return True
