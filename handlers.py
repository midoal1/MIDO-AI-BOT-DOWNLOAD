import re
import os
import uuid
import html
import logging
from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    FSInputFile, InputMediaPhoto
)
from downloader import extract_info, download_video_quality, download_audio, cleanup_file
from database import register_user, increment_downloads, get_stats

logger = logging.getLogger(__name__)
router = Router()

URL_PATTERN = re.compile(r'https?://[^\s]+')

# Memory cache for active video URLs
URL_CACHE = {}


async def update_bot_description(bot, user_count: int):
    """Update bot short description dynamically with user count."""
    try:
        short_desc = f"👥 عدد المستخدمين: {user_count} | 🎬 تنزيل الفيديوهات والصوتيات بدون علامة مائية"
        await bot.set_my_short_description(short_description=short_desc)
    except Exception as e:
        logger.warning(f"Could not update bot short description: {e}")


async def safe_edit_status(message: Message, text: str, reply_markup=None):
    """Safely edit message text or caption whether message has photo or text."""
    try:
        if message.photo:
            return await message.edit_caption(caption=text, reply_markup=reply_markup, parse_mode="HTML")
        else:
            return await message.edit_text(text=text, reply_markup=reply_markup, parse_mode="HTML")
    except Exception as e:
        logger.warning(f"Error editing status message: {e}")
        return message


@router.message(CommandStart())
async def start_handler(message: Message):
    is_new, user_count = register_user(message.from_user.id)
    if is_new:
        await update_bot_description(message.bot, user_count)

    welcome_text = (
        "👋 <b>أهلاً بك في بوت تنزيل الفيديوهات والصوتيات الشامل!</b>\n\n"
        f"👥 <b>إجمالي مستخدمي البوت حتى الآن:</b> <code>{user_count}</code> مستخدم\n\n"
        "🎬 <b>المنصات المدعومة:</b>\n"
        "• 🎵 <b>TikTok</b> (فيديوهات بدون علامة مائية + بوستات الصور 📸)\n"
        "• 🔴 <b>YouTube & Shorts</b>\n"
        "• 📸 <b>Instagram Reels & Posts</b>\n"
        "• 🐦 <b>Twitter / X</b> & 📘 <b>Facebook</b>\n"
        "• 📌 <b>Pinterest</b> & جميع مواقع الفيديوهات الأخرى!\n\n"
        "💡 <b>كيفية الاستخدام:</b>\n"
        "فقط قم بإرسال رابط أي فيديو، وسأعرض لك الصورة المصغرة مع خيارات الجودة أو MP3!"
    )
    await message.answer(welcome_text, parse_mode="HTML")


@router.message(Command("stats"))
async def stats_handler(message: Message):
    stats = get_stats()
    user_count = stats["user_count"]
    downloads = stats["total_downloads"]

    await update_bot_description(message.bot, user_count)

    stats_text = (
        "📊 <b>إحصائيات البوت الحالية:</b>\n\n"
        f"👥 <b>عدد المستخدمين المسجلين:</b> <code>{user_count}</code>\n"
        f"📥 <b>إجمالي الفيديوهات والصوتيات المنزلة:</b> <code>{downloads}</code>\n\n"
        "✨ تم تحديث الوصف التعريفي للبوت في تليجرام بنجاح!"
    )
    await message.answer(stats_text, parse_mode="HTML")


@router.message(Command("help"))
async def help_handler(message: Message):
    help_text = (
        "❓ <b>مساعدة الاستخدام:</b>\n\n"
        "1. انسخ رابط أي فيديو من أي منصة.\n"
        "2. أرسل الرابط في المحادثة.\n"
        "3. اختار الجودة المطلوبة (720p / 480p) أو صوت فقط (MP3).\n\n"
        "⚠️ <b>ملاحظة:</b> الأقصى المسموح لحجم الملفات في تليجرام هو 50 ميجابايت."
    )
    await message.answer(help_text, parse_mode="HTML")


@router.message(F.text)
async def handle_video_link(message: Message):
    is_new, user_count = register_user(message.from_user.id)
    if is_new:
        await update_bot_description(message.bot, user_count)

    urls = URL_PATTERN.findall(message.text)
    if not urls:
        await message.answer("⚠️ يرجى إرسال رابط فيديو صحيح لتتم معالجته.")
        return

    url = urls[0]
    status_msg = await message.answer("🔍 <b>جاري فحص الرابط وجلب الخيارات...</b>", parse_mode="HTML")

    info = await extract_info(url)
    if not info:
        await status_msg.edit_text("❌ <b>تعذر جلب معلومات الفيديو.</b>\nيرجى التأكد من أن الرابط يعمل وليس خاصاً.")
        return

    url_id = str(uuid.uuid4())[:8]
    URL_CACHE[url_id] = url

    title = html.escape(info.get("title", "فيديو"))
    platform = html.escape(info.get("platform", "منصة فيديو"))
    author = html.escape(info.get("author", ""))
    thumb = info.get("thumbnail")

    msg_text = (
        f"🎬 <b>{title}</b>\n\n"
        f"🌐 المنصة: <code>{platform}</code>\n"
    )
    if author:
        msg_text += f"👤 الكاتب/القناة: <code>{author}</code>\n"

    msg_text += "\n👇 <b>اختر نوع التحميل أو الجودة المطلوبة:</b>"

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🎬 فيديو 720p HD", callback_data=f"dl:720:{url_id}"),
                InlineKeyboardButton(text="📺 فيديو 480p SD", callback_data=f"dl:480:{url_id}"),
            ],
            [
                InlineKeyboardButton(text="🎵 صوت فقط (MP3)", callback_data=f"dl:mp3:{url_id}"),
            ]
        ]
    )

    if thumb and (thumb.startswith("http://") or thumb.startswith("https://")):
        try:
            await status_msg.delete()
            await message.answer_photo(
                photo=thumb,
                caption=msg_text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
            return
        except Exception as e:
            logger.warning(f"Could not send thumbnail photo: {e}")

    await status_msg.edit_text(msg_text, reply_markup=keyboard, parse_mode="HTML")


@router.callback_query(F.data.startswith("dl:"))
async def handle_download_option(callback: CallbackQuery):
    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer("⚠️ طلب غير صالحة.", show_alert=True)
        return

    mode = parts[1]
    url_id = parts[2]

    url = URL_CACHE.get(url_id)
    if not url:
        await callback.answer("⚠️ انتهت صلاحية هذا الرابط. يرجى إرسال الرابط مجدداً.", show_alert=True)
        return

    await callback.answer()

    if mode == "mp3":
        loading_text = "⏳ <b>جاري تحويل وتنزيل الصوت بصيغة MP3...</b>"
    else:
        loading_text = f"⏳ <b>جاري تنزيل الملف بجودة {mode}p...</b>"

    status_msg = await safe_edit_status(callback.message, loading_text)

    download_data = None
    try:
        if mode == "mp3":
            download_data = await download_audio(url)
        else:
            download_data = await download_video_quality(url, mode)

        if not download_data:
            await safe_edit_status(callback.message, "❌ <b>عذراً، تعذر تنزيل الملف.</b>\nقد يتجاوز حجم الملف الحد المسموح (50 ميجابايت) أو أن الرابط غير مدعوم.")
            return

        increment_downloads()

        title = html.escape(download_data.get("title", ""))
        author = html.escape(download_data.get("author", ""))
        platform = html.escape(download_data.get("platform", ""))

        caption = f"🎬 <b>{title[:80]}</b>\n"
        if author:
            caption += f"👤 المصدر: {author}\n"
        caption += f"🌐 النوع: {platform}\n\n"
        caption += "🤖 تم التحميل بواسطة @MIDOALIAIBOT"

        if download_data.get("type") == "photos":
            await safe_edit_status(callback.message, "📤 <b>جاري رفع ألبوم الصور إلى تليجرام...</b>")
            image_paths = download_data.get("image_paths", [])
            media_group = []
            for idx, img_p in enumerate(image_paths):
                if idx == 0:
                    media_group.append(InputMediaPhoto(media=FSInputFile(img_p), caption=caption, parse_mode="HTML"))
                else:
                    media_group.append(InputMediaPhoto(media=FSInputFile(img_p)))

            if media_group:
                await callback.message.answer_media_group(media=media_group)

            if download_data.get("music_path"):
                await callback.message.answer_audio(
                    audio=FSInputFile(download_data["music_path"]),
                    caption="🎵 <b>الخلفية الصوتية للبوست - @MIDOALIAIBOT</b>",
                    parse_mode="HTML"
                )

        else:
            file_path = download_data.get("file_path")
            if not file_path or not os.path.exists(file_path):
                await safe_edit_status(callback.message, "❌ <b>عذراً، تعذر إيجاد ملف التنزيل.</b>")
                return

            file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
            if file_size_mb > 50:
                await safe_edit_status(callback.message, f"⚠️ <b>حجم الملف كبير جداً ({file_size_mb:.1f} ميجابايت).</b>\nتسمح سياسة تليجرام للبوتات بإرسال ملفات حتى 50 ميجابايت فقط.")
                return

            await safe_edit_status(callback.message, "📤 <b>جاري رفع الملف إلى تليجرام...</b>")
            input_file = FSInputFile(file_path)

            if mode == "mp3" or download_data.get("type") == "audio":
                await callback.message.answer_audio(
                    audio=input_file,
                    caption=caption,
                    title=download_data.get("title", "")[:60],
                    performer=download_data.get("author", "")[:30] if download_data.get("author") else "MIDO AI",
                    parse_mode="HTML"
                )
            else:
                await callback.message.answer_video(
                    video=input_file,
                    caption=caption,
                    parse_mode="HTML"
                )

        await callback.message.delete()

    except Exception as e:
        logger.error(f"Error handling download callback: {e}", exc_info=True)
        await safe_edit_status(callback.message, "❌ <b>حدث خطأ أثناء معالجة التنزيل.</b>")
    finally:
        if download_data:
            if download_data.get("file_path"):
                cleanup_file(download_data["file_path"])
            if download_data.get("image_paths"):
                for p in download_data["image_paths"]:
                    cleanup_file(p)
            if download_data.get("music_path"):
                cleanup_file(download_data["music_path"])
