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
    get_force_channel,
)

logger = logging.getLogger(__name__)

admin_router = Router()

# Telegram ID الخاص بمالك البوت
ADMIN_ID = 8784484645

# حفظ حالة الأدمن مؤقتًا
ADMIN_STATE = {}


def get_admin_keyboard():
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
    return user_id == ADMIN_ID


@admin_router.message(Command("myid"))
async def my_id_handler(message: Message):
    if message.from_user is None:
        return

    await message.answer(
        f"🆔 <b>معرفك في تيليجرام:</b> "
        f"<code>{message.from_user.id}</code>",
        parse_mode="HTML",
    )


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

    if action == "close":
        ADMIN_STATE.pop(callback.from_user.id, None)

        if callback.message:
            await callback.message.delete()

        await callback.answer()
        return

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

    if action == "broadcast":
        ADMIN_STATE[callback.from_user.id] = "broadcast"

        await callback.answer()

        if callback.message:
            await callback.message.answer(
                "📢 <b>قسم الإذاعة العامة:</b>\n\n"
                "قم الآن بإرسال أو إعادة توجيه أي رسالة، "
                "صورة، فيديو أو منشور ترغب بنشره لجميع المستخدمين.\n\n"
                "لإلغاء الإذاعة أرسل:\n"
                "<code>إلغاء</code>",
                parse_mode="HTML",
            )

        return

    if action == "set_channel":
        ADMIN_STATE[callback.from_user.id] = "set_channel"

        await callback.answer()

        if callback.message:
            await callback.message.answer(
                "🔒 <b>إعداد القناة الإجبارية:</b>\n\n"
                "أرسل الآن معرف القناة، مثال:\n"
                "<code>@MyChannel</code>\n\n"
                "ولإلغاء الاشتراك الإجباري أرسل:\n"
                "<code>off</code>",
                parse_mode="HTML",
            )

        return


@admin_router.message(
    F.text,
    lambda message: (
        message.from_user is not None
        and message.from_user.id in ADMIN_STATE
    ),
)
async def handle_admin_state(message: Message):
    if message.from_user is None:
        return

    user_id = message.from_user.id

    if not is_owner(user_id):
        ADMIN_STATE.pop(user_id, None)
        return

    state = ADMIN_STATE.get(user_id)

    if not state:
        return

    text = (message.text or "").strip()

    if text.lower() in {"إلغاء", "الغاء", "cancel"}:
        ADMIN_STATE.pop(user_id, None)

        await message.answer(
            "❌ تم إلغاء العملية.",
            reply_markup=get_admin_keyboard(),
        )
        return

    if state == "set_channel":
        if text.lower() == "off":
            set_force_channel(None)
            ADMIN_STATE.pop(user_id, None)

            await message.answer(
                "✅ تم تعطيل الاشتراك الإجباري.",
                reply_markup=get_admin_keyboard(),
            )
            return

        if not text.startswith("@"):
            await message.answer(
                "⚠️ أرسل معرف القناة بالشكل الصحيح.\n"
                "مثال:\n"
                "<code>@MyChannel</code>",
                parse_mode="HTML",
            )
            return

        set_force_channel(text)
        ADMIN_STATE.pop(user_id, None)

        await message.answer(
            f"✅ تم تعيين القناة الإجبارية إلى:\n"
            f"<code>{text}</code>",
            parse_mode="HTML",
            reply_markup=get_admin_keyboard(),
        )
        return


@admin_router.message(
    lambda message: (
        message.from_user is not None
        and ADMIN_STATE.get(message.from_user.id) == "broadcast"
    )
)
async def handle_broadcast(message: Message):
    if message.from_user is None:
        return

    user_id = message.from_user.id

    if not is_owner(user_id):
        ADMIN_STATE.pop(user_id, None)
        return

    user_ids = get_all_user_ids()

    if not user_ids:
        ADMIN_STATE.pop(user_id, None)
        await message.answer("⚠️ لا يوجد مستخدمون لإرسال الإذاعة إليهم.")
        return

    success_count = 0
    failed_count = 0

    status_message = await message.answer(
        f"📢 جاري إرسال الإذاعة إلى {len(user_ids)} مستخدم..."
    )

    for target_user_id in user_ids:
        try:
            if target_user_id == user_id:
                continue

            await message.send_copy(chat_id=target_user_id)

            success_count += 1

        except Exception as exc:
            failed_count += 1
            logger.warning(
                "Broadcast failed for user %s: %s",
                target_user_id,
                exc,
            )

        await asyncio.sleep(0.05)

    ADMIN_STATE.pop(user_id, None)

    await status_message.edit_text(
        "✅ <b>انتهت الإذاعة.</b>\n\n"
        f"📨 تم الإرسال بنجاح: <code>{success_count}</code>\n"
        f"❌ فشل الإرسال: <code>{failed_count}</code>",
        parse_mode="HTML",
    )