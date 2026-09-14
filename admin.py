import asyncio
import logging
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from database import is_admin, add_admin, get_stats, get_all_user_ids, set_force_channel, get_force_channel

logger = logging.getLogger(__name__)
admin_router = Router()

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


@admin_router.message(Command("myid"))
@admin_router.message(F.text.startswith("/myid"))
async def my_id_handler(message: Message):
    await message.answer(f"🆔 <b>معرفك في تليجرام (Your ID):</b> <code>{message.from_user.id}</code>", parse_mode="HTML")


@admin_router.message(Command("admin"))
@admin_router.message(F.text.startswith("/admin"))
async def admin_panel_handler(message: Message):
    user_id = message.from_user.id
    
    stats = get_stats()
    if stats["admin_count"] == 0 or not is_admin(user_id):
        # Auto register first user as Master Admin if no admin set yet
        if stats["admin_count"] == 0:
            add_admin(user_id)
            await message.answer("🎉 <b>تم تسجيلك وتعيينك مالكاً رسمياً وأدمن للبوت بنجاح!</b>", parse_mode="HTML")
            stats = get_stats()
        else:
            await message.answer("⚠️ <b>عذراً، هذا الأمر مخصص لمالك البوت (الأدمن) فقط.</b>", parse_mode="HTML")
            return

    force_chan = stats["force_channel"] or "غير محددة (معطلة)"

    panel_text = (
        "👑 <b>لوحة تحكم أدمن البوت (محمية 🔐):</b>\n\n"
        f"👤 <b>معرف الأدمن:</b> <code>{user_id}</code>\n"
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
            "👑 <b>لوحة تحكم أدمن البوت (تحديث 🔐):</b>\n\n"
            f"👤 <b>معرف الأدمن:</b> <code>{callback.from_user.id}</code>\n"
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
