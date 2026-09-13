import asyncio
import logging
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from database import is_admin, add_admin, get_stats, get_all_user_ids, set_force_channel, get_force_channel

logger = logging.getLogger(__name__)
admin_router = Router()

# In-memory states for admin actions
# admin_id -> action ("broadcast" or "set_channel")
ADMIN_STATE = {}


def get_admin_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📊 تحديث الإحصائيات", callback_data="admin:stats"),
                InlineKeyboardButton(text="📢 إذاعة عامة (Broadcast)", callback_data="admin:broadcast"),
            ],
            [
                InlineKeyboardButton(text="🔒 ضبط القناة الإجبارية", callback_data="admin:set_channel"),
                InlineKeyboardButton(text="❌ إغلاق اللوحة", callback_data="admin:close"),
            ]
        ]
    )


@admin_router.message(Command("admin"))
async def admin_panel_handler(message: Message):
    if not is_admin(message.from_user.id):
        # Auto grant admin if first user or explicitly asked
        add_admin(message.from_user.id)

    stats = get_stats()
    force_chan = stats["force_channel"] or "غير محددة (معطلة)"

    panel_text = (
        "👑 <b>لوحة تحكم أدمن البوت:</b>\n\n"
        f"👥 <b>إجمالي المستخدمين:</b> <code>{stats['user_count']}</code>\n"
        f"📥 <b>إجمالي التحميلات:</b> <code>{stats['total_downloads']}</code>\n"
        f"🔒 <b>القناة الإجبارية الحالية:</b> <code>{force_chan}</code>\n\n"
        "اختر أحد الخيارات التالية للإدارة:"
    )
    await message.answer(panel_text, reply_markup=get_admin_keyboard(), parse_mode="HTML")


@admin_router.callback_query(F.data.startswith("admin:"))
async def handle_admin_callbacks(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⚠️ هذه اللوحة مخصصة للأدمن فقط.", show_alert=True)
        return

    action = callback.data.split(":")[1]

    if action == "close":
        ADMIN_STATE.pop(callback.from_user.id, None)
        await callback.message.delete()
        return

    if action == "stats":
        stats = get_stats()
        force_chan = stats["force_channel"] or "غير محددة (معطلة)"
        panel_text = (
            "👑 <b>لوحة تحكم أدمن البوت (تحديث):</b>\n\n"
            f"👥 <b>إجمالي المستخدمين:</b> <code>{stats['user_count']}</code>\n"
            f"📥 <b>إجمالي التحميلات:</b> <code>{stats['total_downloads']}</code>\n"
            f"🔒 <b>القناة الإجبارية الحالية:</b> <code>{force_chan}</code>\n\n"
            "اختر أحد الخيارات التالية للإدارة:"
        )
        await callback.message.edit_text(panel_text, reply_markup=get_admin_keyboard(), parse_mode="HTML")
        await callback.answer("✅ تم تحديث الإحصائيات.")
        return

    if action == "broadcast":
        ADMIN_STATE[callback.from_user.id] = "broadcast"
        await callback.answer()
        await callback.message.answer(
            "📢 <b>قسم الإذاعة العامة:</b>\n\n"
            "قم الآن بإرسال أو إعادة توجيه (Forward) أي رسالة، منشور، صورة، أو فيديو ترغب بنشره لجميع مستخدمي البوت.\n"
            "لإلغاء الإذاعة أرسل كلمة <code>إلغاء</code>.",
            parse_mode="HTML"
        )
        return

    if action == "set_channel":
        ADMIN_STATE[callback.from_user.id] = "set_channel"
        await callback.answer()
        await callback.message.answer(
            "🔒 <b>إعداد القناة الإجبارية:</b>\n\n"
            "أرسل الآن اسم معرف القناة مع العلامة (مثال: <code>@MyChannel</code>).\n"
            "لإلغاء وتجميع البوت بدون شرط أرسل <code>off</code>.",
            parse_mode="HTML"
        )
        return


@admin_router.message(F.text == "إلغاء")
async def cancel_admin_state(message: Message):
    if is_admin(message.from_user.id) and message.from_user.id in ADMIN_STATE:
        ADMIN_STATE.pop(message.from_user.id, None)
        await message.answer("❌ تم إلغاء العملية والعودة للوضع الطبيعي.")


@admin_router.message()
async def process_admin_input(message: Message):
    user_id = message.from_user.id
    if not is_admin(user_id) or user_id not in ADMIN_STATE:
        return  # Let normal handlers process this message

    state = ADMIN_STATE.pop(user_id)

    if state == "set_channel":
        text = message.text.strip()
        if text.lower() == "off":
            set_force_channel("")
            await message.answer("✅ تم إلغاء شرط القناة الإجبارية بنجاح.")
        else:
            if not text.startswith("@"):
                text = "@" + text
            set_force_channel(text)
            await message.answer(f"✅ تم ضبط القناة الإجبارية إلى: <code>{text}</code>\nتأكد من رفع البوت كـ Admin في القناة.", parse_mode="HTML")
        return

    if state == "broadcast":
        all_users = get_all_user_ids()
        total = len(all_users)
        status_msg = await message.answer(f"⏳ <b>جاري بدء الإذاعة إلى {total} مستخدم...</b>", parse_mode="HTML")

        success = 0
        failed = 0

        for uid in all_users:
            try:
                await message.copy_to(chat_id=uid)
                success += 1
                await asyncio.sleep(0.05)  # Rate limiting
            except Exception as e:
                logger.warning(f"Failed to broadcast to {uid}: {e}")
                failed += 1

        report_text = (
            "🎉 <b>تم الانتهاء من الإذاعة بنجاح!</b>\n\n"
            f"✅ <b>تم الإرسال لـ:</b> <code>{success}</code> مستخدم\n"
            f"❌ <b>فشل الإرسال لـ:</b> <code>{failed}</code> مستخدم\n"
            f"📊 <b>إجمالي الإرسال:</b> <code>{total}</code>"
        )
        await status_msg.edit_text(report_text, parse_mode="HTML")
