import json
import os
import logging

logger = logging.getLogger(__name__)

DB_FILE = os.path.join(os.path.dirname(__file__), "database.json")


def load_db() -> dict:
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading database.json: {e}")
    return {"users": [], "user_langs": {}, "total_downloads": 0}


def save_db(data: dict):
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Error saving database.json: {e}")


def register_user(user_id: int, telegram_lang_code: str = None) -> tuple[bool, int, str]:
    """Register user if new and detect default language. Returns (is_new, total_count, user_lang)."""
    db = load_db()
    users_list = db.get("users", [])
    user_langs = db.get("user_langs", {})
    
    is_new = False
    str_uid = str(user_id)
    
    if user_id not in users_list:
        users_list.append(user_id)
        db["users"] = users_list
        is_new = True

    # Detect language if not explicitly set
    if str_uid not in user_langs:
        detected_lang = "ar"
        if telegram_lang_code and not telegram_lang_code.lower().startswith("ar"):
            detected_lang = "en"
        user_langs[str_uid] = detected_lang
        db["user_langs"] = user_langs
        save_db(db)
    else:
        if is_new:
            save_db(db)
            
    return is_new, len(users_list), user_langs.get(str_uid, "ar")


def get_user_lang(user_id: int, telegram_lang_code: str = None) -> str:
    """Get stored user language or detect from telegram_lang_code."""
    db = load_db()
    user_langs = db.get("user_langs", {})
    str_uid = str(user_id)
    
    if str_uid in user_langs:
        return user_langs[str_uid]
        
    detected_lang = "ar"
    if telegram_lang_code and not telegram_lang_code.lower().startswith("ar"):
        detected_lang = "en"
    return detected_lang


def set_user_lang(user_id: int, lang: str) -> str:
    """Set preferred user language."""
    db = load_db()
    user_langs = db.get("user_langs", {})
    user_langs[str(user_id)] = lang
    db["user_langs"] = user_langs
    save_db(db)
    return lang


def increment_downloads() -> int:
    """Increment download count."""
    db = load_db()
    db["total_downloads"] = db.get("total_downloads", 0) + 1
    save_db(db)
    return db["total_downloads"]


def get_stats() -> dict:
    db = load_db()
    return {
        "user_count": len(db.get("users", [])),
        "total_downloads": db.get("total_downloads", 0),
        "users": db.get("users", [])
    }
