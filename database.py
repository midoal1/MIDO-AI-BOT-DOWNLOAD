import json
import os
import logging

logger = logging.getLogger(__name__)

# على Render، /opt/render/project/src هو المسار الثابت الوحيد اللي ميتمسحش
# لو مش على Render، نستخدم مسار الملف الحالي
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(_BASE_DIR, "database.json")

_DEFAULT_DB = {
    "users": [],
    "user_langs": {},
    "fast_mode_users": [],
    "admin_ids": [],
    "force_channel": "",
    "total_downloads": 0
}


def load_db() -> dict:
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                # تأكد إن كل الـ keys موجودة
                for key, default_val in _DEFAULT_DB.items():
                    if key not in data:
                        data[key] = default_val
                return data
        except Exception as e:
            logger.error(f"Error loading database.json: {e}")
    return dict(_DEFAULT_DB)


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
    admin_ids = db.get("admin_ids", [])

    # Auto register first user as Admin if no admins defined
    if not admin_ids:
        admin_ids.append(user_id)
        db["admin_ids"] = admin_ids

    is_new = False
    str_uid = str(user_id)

    if user_id not in users_list:
        users_list.append(user_id)
        db["users"] = users_list
        is_new = True

    if str_uid not in user_langs:
        detected_lang = "ar"
        if telegram_lang_code and not telegram_lang_code.lower().startswith("ar"):
            detected_lang = "en"
        user_langs[str_uid] = detected_lang
        db["user_langs"] = user_langs

    save_db(db)
    return is_new, len(users_list), user_langs.get(str_uid, "ar")


def get_user_lang(user_id: int, telegram_lang_code: str = None) -> str:
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
    db = load_db()
    user_langs = db.get("user_langs", {})
    user_langs[str(user_id)] = lang
    db["user_langs"] = user_langs
    save_db(db)
    return lang


def is_fast_mode(user_id: int) -> bool:
    db = load_db()
    return user_id in db.get("fast_mode_users", [])


def toggle_fast_mode(user_id: int) -> bool:
    db = load_db()
    fast_users = db.get("fast_mode_users", [])
    if user_id in fast_users:
        fast_users.remove(user_id)
        res = False
    else:
        fast_users.append(user_id)
        res = True
    db["fast_mode_users"] = fast_users
    save_db(db)
    return res


def is_admin(user_id: int) -> bool:
    db = load_db()
    return user_id in db.get("admin_ids", [])


def add_admin(user_id: int):
    db = load_db()
    admins = db.get("admin_ids", [])
    if user_id not in admins:
        admins.append(user_id)
        db["admin_ids"] = admins
        save_db(db)


def get_force_channel() -> str:
    db = load_db()
    return db.get("force_channel", "").strip()


def set_force_channel(channel):
    db = load_db()
    db["force_channel"] = (channel or "").strip()
    save_db(db)


def increment_downloads() -> int:
    db = load_db()
    db["total_downloads"] = db.get("total_downloads", 0) + 1
    save_db(db)
    return db["total_downloads"]


def get_all_user_ids() -> list:
    db = load_db()
    return [int(uid) for uid in db.get("users", [])]


def get_stats() -> dict:
    db = load_db()
    return {
        "user_count": len(db.get("users", [])),
        "total_downloads": db.get("total_downloads", 0),
        "users": db.get("users", []),
        "admin_count": len(db.get("admin_ids", [])),
        "force_channel": db.get("force_channel", "")
    }
