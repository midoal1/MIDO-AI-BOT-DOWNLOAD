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
from downloader import (
    extract_info, download_video_quality, download_audio,
    convert_video_to_gif, cleanup_file
)
from database import (
    register_user, get_user_lang, set_user_lang, increment_downloads,
    get_stats, is_fast_mode, toggle_fast_mode, get_force_channel
)

logger = logging.getLogger(__name__)
router = Router()

URL_PATTERN = re.compile(r'https?://[^\s]+')

# Memory cache for active video URLs
URL_CACHE = {}

TEXTS = {
    "ar": {
        "welcome": (
            "👋 <b>أهلاً بك في بوت تنزيل الفيديوهات والصوتيات الشامل!</b>\n\n"
            "👥 <b>إجمالي مستخدمي البوت:</b> <code>{user_count}</code> مستخدم\n"
            "🌐 <b>اللغة الحالية:</b> 🇸🇦 العربية\n"
            "⚡ <b>الوضع السريع:</b> {fast_status}\n\n"
            "🎬 <b>المنصات المدعومة:</b>\n"
            "• 🎵 <b>TikTok</b> (فيديوهات بدون علامة مائية + صور 📸)\n"
            "• 🔴 <b>YouTube & Shorts</b>\n"
            "• 📸 <b>Instagram Reels & Posts</b>\n"
            "• 🐦 <b>Twitter / X</b> & 📘 <b>Facebook</b>\n"
            "• 📌 <b>Pinterest</b> & جميع مواقع الفيديوهات الأخرى!\n\n"
            "💡 <b>كيفية الاستخدام:</b>\n"
            "فقط قم بإرسال رابط أي فيديو للتنزيل أو اختر الخيارات أدناه:"
        ),
        "help": (
            "❓ <b>مساعدة الاستخدام:</b>\n\n"
            "1. انسخ رابط أي فيديو من أي منصة.\n"
            "2. أرسل الرابط في المحادثة.\n"
            "3. اختر الجودة المطلوبة (720p / 480p) أو صوت فقط (MP3).\n\n"
            "⚠️ <b>ملاحظة:</b> الحد الأقصى لحجم الملفات في تليجرام هو 50 ميجابايت."
        ),
        "inspecting": "🔍 <b>جاري فحص الرابط وجلب الخيارات...</b>",
        "select_option": "\n👇 <b>اختر نوع التحميل أو الجودة المطلوبة:</b>",
        "btn_video_720": "🎬 فيديو 720p HD",
        "btn_video_480": "📺 فيديو 480p SD",
        "btn_audio_mp3": "🎵 صوت فقط (MP3)",
        "btn_gif": "🖼️ تحويل إلى GIF",
        "btn_lang_ar": "🇸🇦 العربية (محددة)",
        "btn_lang_en": "🇬🇧 English",
        "downloading_video": "⏳ <b>جاري تنزيل الملف بجودة {quality}p...</b>",
        "downloading_audio": "⏳ <b>جاري تحويل وتنزيل الصوت بصيغة MP3...</b>",
        "downloading_gif": "⏳ <b>جاري إنشاء المقطع المتحرك GIF...</b>",
        "uploading": "📤 <b>جاري رفع الملف إلى تليجرام...</b>",
        "uploading_photos": "📤 <b>جاري رفع ألبوم الصور إلى تليجرام...</b>",
        "error_download": "❌ <b>عذراً، تعذر تنزيل الملف.</b>\nقد يتجاوز حجم الملف الحد المسموح (50MB) أو أن الرابط غير مدعوم.",
        "error_size": "⚠️ <b>حجم الملف كبير جداً ({size:.1f} ميجابايت).</b>\nتسمح سياسة تليجرام للبوتات بإرسال ملفات حتى 50 ميجابايت فقط.",
        "lang_saved": "✅ تم تحديد اللغة العربية بنجاح!",
        "lang_prompt": "🌐 <b>اختر لغتك المفضلة / Select your language:</b>",
        "force_sub": (
            "⚠️ <b>عذراً، يجب عليك الاشتراك في القناة أولاً لاستخدام البوت:</b>\n\n"
            "📢 <b>القناة:</b> <code>{channel}</code>\n\n"
            "بعد الاشتراك، اضغط زر <b>تأكيد الاشتراك ✅</b> بالأسفل لمتابعة التحميل."
        )
    },
    "en": {
        "welcome": (
            "👋 <b>Welcome to Video & Audio Downloader Bot!</b>\n\n"
            "👥 <b>Total Bot Users:</b> <code>{user_count}</code>\n"
            "🌐 <b>Current Language:</b> 🇬🇧 English\n"
            "⚡ <b>Fast Mode:</b> {fast_status}\n\n"
            "🎬 <b>Supported Platforms:</b>\n"
            "• 🎵 <b>TikTok</b> (No Watermark + Photo Posts 📸)\n"
            "• 🔴 <b>YouTube & Shorts</b>\n"
            "• 📸 <b>Instagram Reels & Posts</b>\n"
            "• 🐦 <b>Twitter / X</b> & 📘 <b>Facebook</b>\n"
            "• 📌 <b>Pinterest</b> & all video sites!\n\n"
            "💡 <b>How to use:</b>\n"
            "Just send any video link to download or select options below:"
        ),
        "help": (
            "❓ <b>Help & Instructions:</b>\n\n"
            "1. Copy any video link from any platform.\n"
            "2. Send the link here in chat.\n"
            "3. Select target quality (720p / 480p) or Audio only (MP3).\n\n"
            "⚠️ <b>Note:</b> Telegram max file upload limit is 50 MB."
        ),
        "inspecting": "🔍 <b>Inspecting link and fetching options...</b>",
        "select_option": "\n👇 <b>Select download quality or format:</b>",
        "btn_video_720": "🎬 Video 720p HD",
        "btn_video_480": "📺 Video 480p SD",
        "btn_audio_mp3": "🎵 Audio Only (MP3)",
        "btn_gif": "🖼️ Convert to GIF",
        "btn_lang_ar": "🇸🇦 العربية",
        "btn_lang_en": "🇬🇧 English (Selected)",
        "downloading_video": "⏳ <b>Downloading video in {quality}p...</b>",
        "downloading_audio": "⏳ <b>Converting & downloading MP3 audio...</b>",
        "downloading_gif": "⏳ <b>Generating GIF animation...</b>",
        "uploading": "📤 <b>Uploading file to Telegram...</b>",
        "uploading_photos": "📤 <b>Uploading photo album to Telegram...</b>",
        "error_download": "❌ <b>Sorry, failed to download file.</b>\nFile might exceed 50MB limit or URL is unsupported.",
        "error_size": "⚠️ <b>File size is too large ({size:.1f} MB).</b>\nTelegram bots allow uploads up to 50MB max.",
        "lang_saved": "✅ English language saved successfully!",
        "lang_prompt": "🌐 <b>Select your language / اختر لغتك المفضلة:</b>",
        "force_sub": (
            "⚠️ <b>Sorry, you must subscribe to our channel first to use the bot:</b>\n\n"
            "📢 <b>Channel:</b> <code>{channel}</code>\n\n"
            "After subscribing, click <b>Check Subscription ✅</b> below."
        )
    }
}


async def check_force_sub(bot, user_id: int, lang: str) -> tuple[bool, InlineKeyboardMarkup | None, str | None]:
    """Check if force channel subscription is enabled and user is subscribed."""
    channel = get_force_channel()
    if not channel:
        return True, None, None

    try:
        member = await bot.get_chat_member(chat_id=channel, user_id=user_id)
        if member.status in ["creator", "administrator", "member"]:
            return True, None, None
    except Exception as e:
        logger.warning(f"Failed to check chat member status for {channel}: {e}")

    t = TEXTS[lang]
    clean_chan = channel.replace("@", "")
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📢 " + ("انضم للقناة الآن" if lang == "ar" else "Join Channel Now"), url=f"https://t.me/{clean_chan}")],
            [InlineKeyboardButton(text="✅ " + ("تحقق من الاشتراك" if lang == "ar" else "Check Subscription"), callback_data="check_sub")]
        ]
    )
    return False, kb, t["force_sub"].format(channel=channel)


async def update_bot_description(bot, user_count: int):
    try:
        short_desc = f"👥 عدد المستخدمين: {user_count} | 🎬 تنزيل الفيديوهات والصوتيات بدون علامة مائية"
        await bot.set_my_short_description(short_description=short_desc)
    except Exception as e:
        logger.warning(f"Could not update bot short description: {e}")


async def safe_edit_status(message: Message, text: str, reply_markup=None):
    try:
        if message.photo:
            return await message.edit_caption(caption=text, reply_markup=reply_markup, parse_mode="HTML")
        else:
            return await message.edit_text(text=text, reply_markup=reply_markup, parse_mode="HTML")
    except Exception as e:
        logger.warning(f"Error editing status message: {e}")
        return message


def get_main_keyboard(current_lang: str, is_fast: bool):
    ar_mark = " ✅" if current_lang == "ar" else ""
    en_mark = " ✅" if current_lang == "en" else ""
    fast_text = "⚡ الوضع السريع: مفعل 🟢" if is_fast else "⚡ الوضع السريع: معطل 🔴"
    if current_lang == "en":
        fast_text = "⚡ Fast Mode: ON 🟢" if is_fast else "⚡ Fast Mode: OFF 🔴"

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=f"🇸🇦 العربية{ar_mark}", callback_data="set_lang:ar"),
                InlineKeyboardButton(text=f"🇬🇧 English{en_mark}", callback_data="set_lang:en"),
            ],
            [
                InlineKeyboardButton(text=fast_text, callback_data="toggle_fast"),
            ]
        ]
    )


@router.message(CommandStart())
async def start_handler(message: Message):
    tg_lang = message.from_user.language_code
    is_new, user_count, ulang = register_user(message.from_user.id, tg_lang)
    
    if is_new:
        await update_bot_description(message.bot, user_count)

    # Force Sub Check
    is_subbed, sub_kb, sub_msg = await check_force_sub(message.bot, message.from_user.id, ulang)
    if not is_subbed:
        await message.answer(sub_msg, reply_markup=sub_kb, parse_mode="HTML")
        return

    is_fast = is_fast_mode(message.from_user.id)
    fast_status = "مُفعل 🟢" if is_fast else "مُعطل 🔴"
    if ulang == "en":
        fast_status = "ON 🟢" if is_fast else "OFF 🔴"

    t = TEXTS[ulang]
    welcome_text = t["welcome"].format(user_count=user_count, fast_status=fast_status)
    keyboard = get_main_keyboard(ulang, is_fast)
    await message.answer(welcome_text, reply_markup=keyboard, parse_mode="HTML")


@router.callback_query(F.data == "check_sub")
async def handle_check_sub(callback: CallbackQuery):
    ulang = get_user_lang(callback.from_user.id, callback.from_user.language_code)
    is_subbed, sub_kb, sub_msg = await check_force_sub(callback.bot, callback.from_user.id, ulang)
    
    if is_subbed:
        await callback.answer("🎉 " + ("شكراً لاشتراكك! يمكنك استخدام البوت الآن." if ulang == "ar" else "Thank you for subscribing! You can now use the bot."), show_alert=True)
        await callback.message.delete()
    else:
        await callback.answer("⚠️ " + ("لم يتم التعرف على اشتراكك بالقناة بعد." if ulang == "ar" else "You are not subscribed to the channel yet."), show_alert=True)


@router.callback_query(F.data == "toggle_fast")
async def handle_toggle_fast(callback: CallbackQuery):
    is_fast = toggle_fast_mode(callback.from_user.id)
    ulang = get_user_lang(callback.from_user.id, callback.from_user.language_code)
    t = TEXTS[ulang]
    
    msg = "⚡ تم تفعيل الوضع السريع للتنزيل المباشر!" if is_fast else "⚡ تم إيقاف الوضع السريع ورجوع الأزرار."
    if ulang == "en":
        msg = "⚡ Fast mode enabled!" if is_fast else "⚡ Fast mode disabled."
        
    await callback.answer(msg, show_alert=True)
    
    stats = get_stats()
    fast_status = "مُفعل 🟢" if is_fast else "مُعطل 🔴"
    if ulang == "en":
        fast_status = "ON 🟢" if is_fast else "OFF 🔴"

    welcome_text = t["welcome"].format(user_count=stats["user_count"], fast_status=fast_status)
    keyboard = get_main_keyboard(ulang, is_fast)
    await safe_edit_status(callback.message, welcome_text, reply_markup=keyboard)


@router.callback_query(F.data.startswith("set_lang:"))
async def handle_set_language(callback: CallbackQuery):
    new_lang = callback.data.split(":")[1]
    set_user_lang(callback.from_user.id, new_lang)
    t = TEXTS[new_lang]
    await callback.answer(t["lang_saved"], show_alert=True)
    
    stats = get_stats()
    is_fast = is_fast_mode(callback.from_user.id)
    fast_status = "مُفعل 🟢" if is_fast else "مُعطل 🔴"
    if new_lang == "en":
        fast_status = "ON 🟢" if is_fast else "OFF 🔴"

    welcome_text = t["welcome"].format(user_count=stats["user_count"], fast_status=fast_status)
    keyboard = get_main_keyboard(new_lang, is_fast)
    await safe_edit_status(callback.message, welcome_text, reply_markup=keyboard)


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
    ulang = get_user_lang(message.from_user.id, message.from_user.language_code)
    t = TEXTS[ulang]
    await message.answer(t["help"], parse_mode="HTML")


@router.message(F.text)
async def handle_video_link(message: Message):
    tg_lang = message.from_user.language_code
    is_new, user_count, ulang = register_user(message.from_user.id, tg_lang)
    if is_new:
        await update_bot_description(message.bot, user_count)

    t = TEXTS[ulang]

    # Force Sub Check
    is_subbed, sub_kb, sub_msg = await check_force_sub(message.bot, message.from_user.id, ulang)
    if not is_subbed:
        await message.answer(sub_msg, reply_markup=sub_kb, parse_mode="HTML")
        return

    urls = URL_PATTERN.findall(message.text)
    if not urls:
        await message.answer("⚠️ " + ("يرجى إرسال رابط فيديو صحيح." if ulang == "ar" else "Please send a valid video link."))
        return

    url = urls[0]
    status_msg = await message.answer(t["inspecting"], parse_mode="HTML")

    # Fast Mode: Auto Download HD video directly!
    if is_fast_mode(message.from_user.id):
        await status_msg.edit_text(t["downloading_video"].format(quality="720"), parse_mode="HTML")
        download_data = await download_video_quality(url, "720")
        if download_data and download_data.get("file_path"):
            increment_downloads()
            file_path = download_data["file_path"]
            title = html.escape(download_data.get("title", ""))
            author = html.escape(download_data.get("author", ""))
            caption = f"🎬 <b>{title[:80]}</b>\n🤖 @MIDOALIAIBOT"
            await message.answer_video(video=FSInputFile(file_path), caption=caption, parse_mode="HTML")
            cleanup_file(file_path)
            await status_msg.delete()
            return

    info = await extract_info(url)
    if not info:
        await status_msg.edit_text(t["error_download"], parse_mode="HTML")
        return

    url_id = str(uuid.uuid4())[:8]
    URL_CACHE[url_id] = url

    title = html.escape(info.get("title", "Video"))
    platform = html.escape(info.get("platform", "Platform"))
    author = html.escape(info.get("author", ""))
    thumb = info.get("thumbnail")

    msg_text = (
        f"🎬 <b>{title}</b>\n\n"
        f"🌐 " + ("المنصة" if ulang == "ar" else "Platform") + f": <code>{platform}</code>\n"
    )
    if author:
        msg_text += f"👤 " + ("المصدر" if ulang == "ar" else "Author") + f": <code>{author}</code>\n"

    msg_text += t["select_option"]

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=t["btn_video_720"], callback_data=f"dl:720:{url_id}"),
                InlineKeyboardButton(text=t["btn_video_480"], callback_data=f"dl:480:{url_id}"),
            ],
            [
                InlineKeyboardButton(text=t["btn_audio_mp3"], callback_data=f"dl:mp3:{url_id}"),
                InlineKeyboardButton(text=t["btn_gif"], callback_data=f"dl:gif:{url_id}"),
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
        await callback.answer("⚠️ Request invalid.", show_alert=True)
        return

    mode = parts[1]  # "720", "480", "mp3", or "gif"
    url_id = parts[2]

    ulang = get_user_lang(callback.from_user.id, callback.from_user.language_code)
    t = TEXTS[ulang]

    url = URL_CACHE.get(url_id)
    if not url:
        await callback.answer("⚠️ " + ("انتهت صلاحية الرابط." if ulang == "ar" else "Link expired."), show_alert=True)
        return

    await callback.answer()

    if mode == "mp3":
        loading_text = t["downloading_audio"]
    elif mode == "gif":
        loading_text = t["downloading_gif"]
    else:
        loading_text = t["downloading_video"].format(quality=mode)

    status_msg = await safe_edit_status(callback.message, loading_text)

    download_data = None
    try:
        if mode == "mp3":
            download_data = await download_audio(url)
        elif mode == "gif":
            # Download video first then convert to GIF
            download_data = await download_video_quality(url, "480")
            if download_data and download_data.get("file_path"):
                gif_path = await convert_video_to_gif(download_data["file_path"])
                cleanup_file(download_data["file_path"])
                if gif_path:
                    download_data["file_path"] = gif_path
                    download_data["type"] = "gif"
                else:
                    download_data = None
        else:
            download_data = await download_video_quality(url, mode)

        if not download_data:
            await safe_edit_status(callback.message, t["error_download"])
            return

        increment_downloads()

        title = html.escape(download_data.get("title", ""))
        author = html.escape(download_data.get("author", ""))
        platform = html.escape(download_data.get("platform", ""))

        caption = f"🎬 <b>{title[:80]}</b>\n"
        if author:
            caption += f"👤 " + ("المصدر" if ulang == "ar" else "Source") + f": {author}\n"
        caption += f"🌐 " + ("النوع" if ulang == "ar" else "Type") + f": {platform}\n\n"
        caption += "🤖 @MIDOALIAIBOT"

        if download_data.get("type") == "photos":
            await safe_edit_status(callback.message, t["uploading_photos"])
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
                    caption="🎵 <b>@MIDOALIAIBOT</b>",
                    parse_mode="HTML"
                )

        else:
            file_path = download_data.get("file_path")
            if not file_path or not os.path.exists(file_path):
                await safe_edit_status(callback.message, t["error_download"])
                return

            file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
            if file_size_mb > 50:
                await safe_edit_status(callback.message, t["error_size"].format(size=file_size_mb))
                return

            await safe_edit_status(callback.message, t["uploading"])
            input_file = FSInputFile(file_path)

            if download_data.get("type") == "gif":
                await callback.message.answer_animation(
                    animation=input_file,
                    caption=caption,
                    parse_mode="HTML"
                )
            elif mode == "mp3" or download_data.get("type") == "audio":
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
        await safe_edit_status(callback.message, t["error_download"])
    finally:
        if download_data:
            if download_data.get("file_path"):
                cleanup_file(download_data["file_path"])
            if download_data.get("image_paths"):
                for p in download_data["image_paths"]:
                    cleanup_file(p)
            if download_data.get("music_path"):
                cleanup_file(download_data["music_path"])
