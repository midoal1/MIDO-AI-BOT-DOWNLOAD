import asyncio
import logging

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from database import (
    get_stats,
    get_all_user_ids,
    set_force_channel,
    is_admin,
)

logger = logging.getLogger(__name__)

admin_router = Router()

# Telegram ID الخاص بمالك البوت
ADMIN_ID = 8784484645

# حالة الأدمن المؤقتة
ADMIN_STATE: dict = {}


def get_admin_state(user_id: int):
    val = ADMIN_STATE.get(user_id)
    if isinstance(val, dict):
        return val.get("state")
    return val


def get_admin_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📊 تحديث الإحصائيات",
                    callback_data="admin:stats",
                ),
                InlineKeyboardButton(
                    text="📢 إذاعة عامة (Broadcast)",
                    callback_data="admin:broadcast",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🔒 ضبط القناة الإجبارية",
                    callback_data="admin:set_channel",
                ),
                InlineKeyboardButton(
                    text="❌ إغلاق اللوحة",
                    callback_data="admin:close",
                ),
            ],
        ]
    )


def is_owner(user_id: int) -> bool:
    return is_admin(user_id) or user_id == ADMIN_ID


# =========================================================
# MY ID
# =========================================================

@admin_router.message(Command("myid"))
async def my_id_handler(message: Message):
    if message.from_user is None:
        return

    await message.answer(
        f"🆔 <b>معرفك في تيليجرام:</b> "
        f"<code>{message.from_user.id}</code>",
        parse_mode="HTML",
    )


# =========================================================
# ADMIN PANEL
# =========================================================

@admin_router.message(Command("admin"))
async def admin_panel_handler(message: Message):
    if message.from_user is None:
        return

    user_id = message.from_user.id

    if not is_owner(user_id):
        await message.answer(
            "⚠️ <b>عذراً، هذا الأمر مخصص لمالك البوت فقط.</b>",
            parse_mode="HTML",
        )
        return

    # إلغاء أي عملية قديمة عند فتح لوحة الأدمن من جديد
    ADMIN_STATE.pop(user_id, None)

    stats = get_stats()

    force_chan = stats.get("force_channel") or "غير محددة (معطلة)"
    user_count = stats.get("user_count", 0)
    total_downloads = stats.get("total_downloads", 0)

    panel_text = (
        "👑 <b>لوحة تحكم أدمن البوت (محمية 🔐):</b>\n\n"
        f"👤 <b>معرف الأدمن:</b> <code>{user_id}</code>\n"
        f"👥 <b>إجمالي المستخدمين:</b> <code>{user_count}</code>\n"
        f"📥 <b>إجمالي التحميلات:</b> <code>{total_downloads}</code>\n"
        f"🔒 <b>القناة الإجبارية الحالية:</b> "
        f"<code>{force_chan}</code>\n\n"
        "اختر أحد الخيارات التالية للإدارة:"
    )

    await message.answer(
        panel_text,
        reply_markup=get_admin_keyboard(),
        parse_mode="HTML",
    )


# =========================================================
# ADMIN BUTTONS
# =========================================================

@admin_router.callback_query(F.data.startswith("admin:"))
async def handle_admin_callbacks(callback: CallbackQuery):
    if not is_owner(callback.from_user.id):
        await callback.answer(
            "⚠️ هذه اللوحة مخصصة لمالك البوت فقط.",
            show_alert=True,
        )
        return

    if not callback.data:
        return

    action = callback.data.split(":", 1)[1]

    # -------------------------
    # CLOSE
    # -------------------------

    if action == "close":
        ADMIN_STATE.pop(callback.from_user.id, None)

        if callback.message:
            await callback.message.delete()

        await callback.answer()
        return

    # -------------------------
    # STATS
    # -------------------------

    if action == "stats":
        stats = get_stats()

        force_chan = stats.get("force_channel") or "غير محددة (معطلة)"
        user_count = stats.get("user_count", 0)
        total_downloads = stats.get("total_downloads", 0)

        panel_text = (
            "👑 <b>لوحة تحكم أدمن البوت (تحديث 🔐):</b>\n\n"
            f"👤 <b>معرف الأدمن:</b> "
            f"<code>{callback.from_user.id}</code>\n"
            f"👥 <b>إجمالي المستخدمين:</b> "
            f"<code>{user_count}</code>\n"
            f"📥 <b>إجمالي التحميلات:</b> "
            f"<code>{total_downloads}</code>\n"
            f"🔒 <b>القناة الإجبارية الحالية:</b> "
            f"<code>{force_chan}</code>\n\n"
            "اختر أحد الخيارات التالية للإدارة:"
        )

        if callback.message:
            await callback.message.edit_text(
                panel_text,
                reply_markup=get_admin_keyboard(),
                parse_mode="HTML",
            )

        await callback.answer("✅ تم تحديث الإحصائيات.")
        return

    # -------------------------
    # BROADCAST
    # -------------------------

    if action == "broadcast":
        ADMIN_STATE[callback.from_user.id] = "broadcast"

        await callback.answer()

        if callback.message:
            await callback.message.answer(
                "📢 <b>قسم الإذاعة العامة:</b>\n\n"
                "أرسل الآن الرسالة التي تريد إرسالها لجميع مستخدمي البوت.\n\n"
                "يمكنك إرسال:\n"
                "• 📝 نص\n"
                "• 🖼 صورة\n"
                "• 🎬 فيديو\n"
                "• 🎵 صوت\n"
                "• 📎 ملف\n"
                "• ↪️ رسالة معاد توجيهها\n\n"
                "لإلغاء العملية أرسل:\n"
                "<code>إلغاء</code>",
                parse_mode="HTML",
            )

        return

    if action == "confirm_bc":
        st = ADMIN_STATE.get(callback.from_user.id)
        if not isinstance(st, dict) or st.get("state") != "confirm_broadcast" or "message" not in st:
            await callback.answer("⚠️ انتهت صلاحية الطلب أو تم إلغاء الإذاعة.", show_alert=True)
            return

        bc_msg: Message = st["message"]
        ADMIN_STATE.pop(callback.from_user.id, None)

        user_ids = get_all_user_ids()
        if not user_ids:
            await callback.answer()
            if callback.message:
                await callback.message.answer(
                    "⚠️ لا يوجد مستخدمون مسجلون في البوت لإرسال الإذاعة إليهم.",
                    reply_markup=get_admin_keyboard(),
                )
            return

        await callback.answer("🚀 جاري بدء الإذاعة...")
        if callback.message:
            await callback.message.edit_reply_markup(reply_markup=None)

        success_count = 0
        failed_count = 0
        skipped_count = 0

        status_message = await callback.message.answer(
            f"📢 جاري إرسال الإذاعة إلى {len(user_ids)} مستخدم..."
        )

        for target_user_id in user_ids:
            try:
                target_user_id = int(target_user_id)

                if target_user_id == callback.from_user.id:
                    skipped_count += 1
                    continue

                await bc_msg.send_copy(chat_id=target_user_id)
                success_count += 1

            except Exception as exc:
                failed_count += 1
                logger.warning(
                    "Broadcast failed for user %s: %s",
                    target_user_id,
                    exc,
                )

            await asyncio.sleep(0.05)

        await status_message.edit_text(
            "✅ <b>انتهت الإذاعة العامة بنجاح!</b>\n\n"
            f"📨 تم الإرسال بنجاح: <code>{success_count}</code>\n"
            f"❌ فشل الإرسال: <code>{failed_count}</code>\n"
            f"⏭ تم التخطي: <code>{skipped_count}</code>",
            parse_mode="HTML",
            reply_markup=get_admin_keyboard(),
        )
        return

    if action == "cancel_bc":
        ADMIN_STATE.pop(callback.from_user.id, None)
        await callback.answer("❌ تم إلغاء الإذاعة.")
        if callback.message:
            await callback.message.edit_reply_markup(reply_markup=None)
            await callback.message.answer(
                "❌ تم إلغاء عملية الإذاعة.",
                reply_markup=get_admin_keyboard(),
            )
        return

    # -------------------------
    # FORCE CHANNEL
    # -------------------------

    if action == "set_channel":
        ADMIN_STATE[callback.from_user.id] = "set_channel"

        await callback.answer()

        if callback.message:
            await callback.message.answer(
                "🔒 <b>إعداد القناة الإجبارية:</b>\n\n"
                "أرسل معرف القناة بالشكل التالي:\n"
                "<code>@MyChannel</code>\n\n"
                "ولتعطيل الاشتراك الإجباري أرسل:\n"
                "<code>off</code>\n\n"
                "ولإلغاء العملية أرسل:\n"
                "<code>إلغاء</code>",
                parse_mode="HTML",
            )

        return


# =========================================================
# BROADCAST HANDLER
# يجب أن يكون قبل أي Handler عام للرسائل
# =========================================================

@admin_router.message(
    lambda message: (
        message.from_user is not None
        and is_owner(message.from_user.id)
        and get_admin_state(message.from_user.id) in ["broadcast", "confirm_broadcast"]
    )
)
async def handle_broadcast(message: Message):
    if message.from_user is None:
        return

    user_id = message.from_user.id

    # إلغاء العملية
    if message.text:
        text = message.text.strip().lower()

        if text in {"إلغاء", "الغاء", "cancel"}:
            ADMIN_STATE.pop(user_id, None)

            await message.answer(
                "❌ تم إلغاء الإذاعة.",
                reply_markup=get_admin_keyboard(),
            )
            return

    # حفظ الرسالة للمعاينة والتأكيد
    ADMIN_STATE[user_id] = {
        "state": "confirm_broadcast",
        "message": message,
    }

    user_ids = get_all_user_ids()
    total_users = len(user_ids)

    await message.answer(
        f"👁️ <b>معاينة رسالة الإذاعة العامة (Preview):</b>\n\n"
        f"👥 سيتم إرسالها إلى: <code>{total_users}</code> مستخدم\n"
        f"👇 الرسالة المعروضة أدناه هي الشكل الدقيق الذي سيصله المستلمون:",
        parse_mode="HTML",
    )

    confirm_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ تأكيد وإرسال الإذاعة",
                    callback_data="admin:confirm_bc",
                ),
                InlineKeyboardButton(
                    text="❌ إلغاء الإذاعة",
                    callback_data="admin:cancel_bc",
                ),
            ]
        ]
    )

    await message.send_copy(
        chat_id=user_id,
        reply_markup=confirm_keyboard,
    )


# =========================================================
# FORCE CHANNEL HANDLER
# =========================================================

@admin_router.message(
    lambda message: (
        message.from_user is not None
        and is_owner(message.from_user.id)
        and get_admin_state(message.from_user.id) == "set_channel"
    )
)
async def handle_set_channel(message: Message):
    if message.from_user is None:
        return

    user_id = message.from_user.id

    text = (message.text or "").strip()

    # إلغاء
    if text.lower() in {"إلغاء", "الغاء", "cancel"}:
        ADMIN_STATE.pop(user_id, None)

        await message.answer(
            "❌ تم إلغاء العملية.",
            reply_markup=get_admin_keyboard(),
        )
        return

    # تعطيل القناة الإجبارية
    if text.lower() == "off":
        set_force_channel(None)

        ADMIN_STATE.pop(user_id, None)

        await message.answer(
            "✅ تم تعطيل الاشتراك الإجباري.",
            reply_markup=get_admin_keyboard(),
        )
        return

    # التحقق من صيغة Username
    if not text.startswith("@"):
        await message.answer(
            "⚠️ أرسل معرف القناة بالشكل الصحيح.\n\n"
            "مثال:\n"
            "<code>@MyChannel</code>",
            parse_mode="HTML",
        )
        return

    set_force_channel(text)

    ADMIN_STATE.pop(user_id, None)

    await message.answer(
        "✅ <b>تم تعيين القناة الإجبارية بنجاح.</b>\n\n"
        f"📢 القناة:\n<code>{text}</code>",
        parse_mode="HTML",
        reply_markup=get_admin_keyboard(),
    )