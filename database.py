import json
import os
import time
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

DB_FILE = os.path.join(os.path.dirname(__file__), "database.json")


def load_db() -> dict:
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading database.json: {e}")
    return {
        "users": [],
        "user_langs": {},
        "fast_mode_users": [],
        "admin_ids": [],
        "force_channel": "",
        "total_downloads": 0,
        "vip_until": {},
        "daily_downloads": {},
        "log_channel": "@midoaidownload"
    }


def save_db(data: dict):
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Error saving database.json: {e}")


def register_user(user_id: int, telegram_lang_code: str = None) -> tuple[bool, int, str]:
    db = load_db()
    users_list = db.get("users", [])
    user_langs = db.get("user_langs", {})
    admin_ids = db.get("admin_ids", [])
    
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


def is_vip(user_id: int) -> tuple[bool, str]:
    """Check if user has an active VIP subscription. Returns (is_vip, expire_date_str)."""
    db = load_db()
    vip_until = db.get("vip_until", {})
    str_uid = str(user_id)
    
    if str_uid in vip_until:
        expire_timestamp = vip_until[str_uid]
        if time.time() < expire_timestamp:
            date_str = datetime.fromtimestamp(expire_timestamp).strftime("%Y-%m-%d")
            return True, date_str
    return False, ""


def activate_vip(user_id: int, days: int = 30) -> str:
    """Activate or extend VIP subscription for N days."""
    db = load_db()
    vip_until = db.get("vip_until", {})
    str_uid = str(user_id)
    
    current_time = time.time()
    existing_expiry = vip_until.get(str_uid, 0)
    
    if existing_expiry > current_time:
        new_expiry = existing_expiry + (days * 86400)
    else:
        new_expiry = current_time + (days * 86400)
        
    vip_until[str_uid] = new_expiry
    db["vip_until"] = vip_until
    save_db(db)
    
    return datetime.fromtimestamp(new_expiry).strftime("%Y-%m-%d")


def check_daily_limit(user_id: int, max_free: int = 5) -> tuple[bool, int]:
    """
    Check daily download limit for free users.
    Returns (can_download, remaining_downloads).
    """
    is_vip_active, _ = is_vip(user_id)
    if is_vip_active:
        return True, 999  # Unlimited for VIP

    db = load_db()
    daily = db.get("daily_downloads", {})
    str_uid = str(user_id)
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    user_record = daily.get(str_uid, {})
    if user_record.get("date") != today_str:
        user_record = {"date": today_str, "count": 0}
        
    current_count = user_record.get("count", 0)
    if current_count >= max_free:
        return False, 0
        
    return True, (max_free - current_count)


def record_download(user_id: int):
    """Record a download for daily tracking and global stats."""
    db = load_db()
    db["total_downloads"] = db.get("total_downloads", 0) + 1
    
    is_vip_active, _ = is_vip(user_id)
    if not is_vip_active:
        daily = db.get("daily_downloads", {})
        str_uid = str(user_id)
        today_str = datetime.now().strftime("%Y-%m-%d")
        
        user_record = daily.get(str_uid, {})
        if user_record.get("date") != today_str:
            user_record = {"date": today_str, "count": 1}
        else:
            user_record["count"] = user_record.get("count", 0) + 1
            
        daily[str_uid] = user_record
        db["daily_downloads"] = daily
        
    save_db(db)


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


def set_force_channel(channel: str):
    db = load_db()
    db["force_channel"] = channel.strip()
    save_db(db)


def get_log_channel() -> str:
    db = load_db()
    return db.get("log_channel", "@midoaidownload").strip()


def get_all_user_ids() -> list:
    db = load_db()
    return db.get("users", [])


def get_vip_users_list() -> list[dict]:
    """Returns list of dicts with user_id, expire_date, and days_left for active VIP subscribers."""
    db = load_db()
    vip_until = db.get("vip_until", {})
    current_time = time.time()
    active_vips = []

    for uid_str, exp_timestamp in vip_until.items():
        if exp_timestamp > current_time:
            dt_str = datetime.fromtimestamp(exp_timestamp).strftime("%Y-%m-%d %H:%M")
            days_left = max(0, int((exp_timestamp - current_time) / 86400))
            active_vips.append({
                "user_id": int(uid_str),
                "expire_date": dt_str,
                "days_left": days_left
            })

    active_vips.sort(key=lambda x: x["days_left"])
    return active_vips


def get_stats() -> dict:
    db = load_db()
    vip_count = 0
    current_time = time.time()
    for uid, exp in db.get("vip_until", {}).items():
        if exp > current_time:
            vip_count += 1
            
    return {
        "user_count": len(db.get("users", [])),
        "vip_count": vip_count,
        "total_downloads": db.get("total_downloads", 0),
        "users": db.get("users", []),
        "admin_count": len(db.get("admin_ids", [])),
        "force_channel": db.get("force_channel", ""),
        "log_channel": db.get("log_channel", "@midoaidownload")
    }
