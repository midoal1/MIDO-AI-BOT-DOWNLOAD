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
    return {"users": [], "total_downloads": 0}


def save_db(data: dict):
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Error saving database.json: {e}")


def register_user(user_id: int) -> tuple[bool, int]:
    """Register user if new. Returns (is_new, total_user_count)."""
    db = load_db()
    users_list = db.get("users", [])
    is_new = False
    if user_id not in users_list:
        users_list.append(user_id)
        db["users"] = users_list
        save_db(db)
        is_new = True
    return is_new, len(users_list)


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
