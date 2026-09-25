import re
import os
import uuid
import html
import logging
from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    FSInputFile, InputMediaPhoto, InlineQuery, InlineQueryResultArticle,
    InputTextMessageContent
)
from downloader import (
    extract_info, download_video_quality, download_audio,
    convert_video_to_gif, cleanup_file, search_video_by_query,
    search_videos_inline, extract_playlist_info
)
from database import (
    register_user, get_user_lang, set_user_lang,
    get_stats, is_fast_mode, toggle_fast_mode, get_force_channel,
    is_vip, check_daily_limit, record_download, is_admin
)
from subscriptions import get_vip_upgrade_keyboard

logger = logging.getLogger(__name__)
router = Router()

URL_PATTERN = re.compile(r'https?://[^\s]+')

# Memory caches
URL_CACHE = {}
SEARCH_STATE = {}
PLAYLIST_CACHE = {}

TEXTS = {
    "ar": {
        "welcome": (
            "👋 <b>أهلاً بك في بوت تنزيل الفيديوهات والصوتيات الشامل!</b>\n\n"
            "👥 <b>إجمالي مستخدمي البوت:</b> <code>{user_count}</code> مستخدم\n"
            "🌐 <b>اللغة الحالية:</b> 🇸🇦 العربية\n"
            "⭐ <b>الحالة:</b> {vip_status}\n"
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
            "⚠️ <b>ملاحظة:</b> يحصل الحساب المجاني على 5 تنزيلات يومياً، أو اشترك بـ VIP لتنزيل غير محدود."
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
            "⭐ <b>Status:</b> {vip_status}\n"
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
            "⚠️ <b>Note:</b> Free users get 5 daily downloads. Upgrade to VIP for unlimited access."
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


def get_main_keyboard(current_lang: str, is_fast: bool, user_id: int = None):
    ar_mark = " ✅" if current_lang == "ar" else ""
    en_mark = " ✅" if current_lang == "en" else ""
    fast_text = "⚡ الوضع السريع: مفعل 🟢" if is_fast else "⚡ الوضع السريع: معطل 🔴"
    if current_lang == "en":
        fast_text = "⚡ Fast Mode: ON 🟢" if is_fast else "⚡ Fast Mode: OFF 🔴"

    search_btn_text = "🔍 بحث عن فيديو / أغنية" if current_lang == "ar" else "🔍 Search Video / Song"

    rows = [
        [
            InlineKeyboardButton(text=search_btn_text, callback_data="btn_search_prompt")
        ],
        [
            InlineKeyboardButton(text=f"🇸🇦 العربية{ar_mark}", callback_data="set_lang:ar"),
            InlineKeyboardButton(text=f"🇬🇧 English{en_mark}", callback_data="set_lang:en"),
        ],
        [
            InlineKeyboardButton(text=fast_text, callback_data="toggle_fast"),
        ],
        [
            InlineKeyboardButton(
                text="⭐ " + ("ترقية إلى باقة VIP" if current_lang == "ar" else "Upgrade to VIP"),
                callback_data="vip_upgrade"
            )
        ]
    ]

    if user_id and is_admin(user_id):
        admin_btn = "👑 لوحة التحكم (الأدمن)" if current_lang == "ar" else "👑 Admin Panel"
        rows.append([InlineKeyboardButton(text=admin_btn, callback_data="open_admin_panel")])

    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(CommandStart())
async def start_handler(message: Message):
    tg_lang = message.from_user.language_code
    is_new, user_count, ulang = register_user(message.from_user.id, tg_lang)
    
    if is_new:
        await update_bot_description(message.bot, user_count)

    is_subbed, sub_kb, sub_msg = await check_force_sub(message.bot, message.from_user.id, ulang)
    if not is_subbed:
        await message.answer(sub_msg, reply_markup=sub_kb, parse_mode="HTML")
        return

    is_fast = is_fast_mode(message.from_user.id)
    fast_status = "مُفعل 🟢" if is_fast else "مُعطل 🔴"
    if ulang == "en":
        fast_status = "ON 🟢" if is_fast else "OFF 🔴"

    vip_active, exp_date = is_vip(message.from_user.id)
    vip_status = f"مشترك VIP ⭐ (حتى {exp_date})" if vip_active else "حساب مجاني 🆓 (5 تنزيلات/يوم)"
    if ulang == "en":
        vip_status = f"VIP Active ⭐ (until {exp_date})" if vip_active else "Free Tier 🆓 (5 daily downloads)"

    t = TEXTS[ulang]
    welcome_text = t["welcome"].format(user_count=user_count, fast_status=fast_status, vip_status=vip_status)
    keyboard = get_main_keyboard(ulang, is_fast, message.from_user.id)
    await message.answer(welcome_text, reply_markup=keyboard, parse_mode="HTML")


@router.callback_query(F.data == "vip_upgrade")
async def handle_vip_upgrade_button(callback: CallbackQuery):
    lang = get_user_lang(callback.from_user.id, callback.from_user.language_code)
    msg = (
        "⭐ <b>باقة الاشتراكات الفائقة VIP:</b>\n\n"
        "• تنزيلات غير محدودة بدون حدود يومية.\n"
        "• أسرع جودة وأعلى دقة (1080p HD).\n"
        "• تنزيل ألبومات تيك توك وتفعيل النمط السريع.\n\n"
        "اختر طريقة الشراء المفضل لك أدناه:"
    ) if lang == "ar" else (
        "⭐ <b>VIP Premium Subscription:</b>\n\n"
        "• Unlimited daily downloads.\n"
        "• Max video quality (1080p HD).\n"
        "• Instant Fast Mode & TikTok Photo Albums.\n\n"
        "Choose your preferred payment method below:"
    )
    await callback.answer()
    await callback.message.answer(msg, reply_markup=get_vip_upgrade_keyboard(lang), parse_mode="HTML")


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
    user_id = callback.from_user.id
    ulang = get_user_lang(user_id, callback.from_user.language_code)

    vip_active, exp_date = is_vip(user_id)
    if not vip_active and not is_admin(user_id):
        alert_msg = (
            "⚠️ <b>عذراً، ميزة الوضع السريع مخصصة حصرياً لمشتركي باقة VIP فقط!</b>\n\n"
            "قم بالترقية إلى باقة VIP للتمتع بالتنزيل المباشر الفوري والتنزيلات غير المحدودة."
        ) if ulang == "ar" else (
            "⚠️ <b>Sorry, Fast Mode is an exclusive VIP feature!</b>\n\n"
            "Upgrade to VIP for instant direct downloads and unlimited access."
        )
        await callback.answer("⚠️ ميزة الوضع السريع حصرية لمشتركي VIP فقط!", show_alert=True)
        await callback.message.answer(alert_msg, reply_markup=get_vip_upgrade_keyboard(ulang), parse_mode="HTML")
        return

    is_fast = toggle_fast_mode(user_id)
    t = TEXTS[ulang]
    
    msg = "⚡ تم تفعيل الوضع السريع للتنزيل المباشر!" if is_fast else "⚡ تم إيقاف الوضع السريع ورجوع الأزرار."
    if ulang == "en":
        msg = "⚡ Fast mode enabled!" if is_fast else "⚡ Fast mode disabled."
        
    await callback.answer(msg, show_alert=True)
    
    stats = get_stats()
    fast_status = "مُفعل 🟢" if is_fast else "مُعطل 🔴"
    if ulang == "en":
        fast_status = "ON 🟢" if is_fast else "OFF 🔴"

    vip_status = f"مشترك VIP ⭐ (حتى {exp_date})" if vip_active else "حساب مجاني 🆓 (5 تنزيلات/يوم)"
    if ulang == "en":
        vip_status = f"VIP Active ⭐ (until {exp_date})" if vip_active else "Free Tier 🆓 (5 daily downloads)"

    welcome_text = t["welcome"].format(user_count=stats["user_count"], fast_status=fast_status, vip_status=vip_status)
    keyboard = get_main_keyboard(ulang, is_fast, user_id)
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

    vip_active, exp_date = is_vip(callback.from_user.id)
    vip_status = f"مشترك VIP ⭐ (حتى {exp_date})" if vip_active else "حساب مجاني 🆓 (5 تنزيلات/يوم)"
    if new_lang == "en":
        vip_status = f"VIP Active ⭐ (until {exp_date})" if vip_active else "Free Tier 🆓 (5 daily downloads)"

    welcome_text = t["welcome"].format(user_count=stats["user_count"], fast_status=fast_status, vip_status=vip_status)
    keyboard = get_main_keyboard(new_lang, is_fast, callback.from_user.id)
    await safe_edit_status(callback.message, welcome_text, reply_markup=keyboard)


@router.callback_query(F.data == "open_admin_panel")
async def handle_open_admin_panel(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⚠️ عذراً، هذا الخيار للأدمن فقط.", show_alert=True)
        return

    await callback.answer()
    stats = get_stats()

    force_chan = stats.get("force_channel") or "غير محددة (معطلة)"
    user_count = stats.get("user_count", 0)
    total_downloads = stats.get("total_downloads", 0)

    panel_text = (
        "👑 <b>لوحة تحكم أدمن البوت (محمية 🔐):</b>\n\n"
        f"👤 <b>معرف الأدمن:</b> <code>{callback.from_user.id}</code>\n"
        f"👥 <b>إجمالي المستخدمين:</b> <code>{user_count}</code>\n"
        f"📥 <b>إجمالي التحميلات:</b> <code>{total_downloads}</code>\n"
        f"🔒 <b>القناة الإجبارية الحالية:</b> <code>{force_chan}</code>\n\n"
        "اختر أحد الخيارات التالية للإدارة:"
    )

    from admin import get_admin_keyboard
    await callback.message.answer(panel_text, reply_markup=get_admin_keyboard(), parse_mode="HTML")


@router.callback_query(F.data == "btn_search_prompt")
async def handle_search_prompt(callback: CallbackQuery):
    user_id = callback.from_user.id
    ulang = get_user_lang(user_id, callback.from_user.language_code)
    SEARCH_STATE[user_id] = "awaiting_search_query"
    await callback.answer()

    prompt_text = (
        "🔎 <b>قسم البحث المباشر عن الفيديوهات والصوتيات:</b>\n\n"
        "أرسل الآن اسم الفيديو أو الأغنية باللغة العربية أو الإنجليزية.\n\n"
        "<i>مثال:</i> <code>البخت ويجز</code> أو <code>El Bakht Wegz</code>"
    ) if ulang == "ar" else (
        "🔎 <b>Direct Video & Song Search:</b>\n\n"
        "Send the video or song name in Arabic or English.\n\n"
        "<i>Example:</i> <code>El Bakht Wegz</code>"
    )
    await callback.message.answer(prompt_text, parse_mode="HTML")


@router.inline_query()
async def inline_search_handler(inline_query: InlineQuery):
    query = (inline_query.query or "").strip()
    if not query:
        item = InlineQueryResultArticle(
            id="help",
            title="🔍 اكتب اسم أغنية أو فيديو للبحث...",
            description="مثال: @MIDOALIAIBOT البخت ويجز",
            input_message_content=InputTextMessageContent(
                message_text="🤖 أرسل رابط الفيديو أو اكتب اسم الأغنية لبدء التنزيل!",
                parse_mode="HTML"
            )
        )
        await inline_query.answer([item], cache_time=60)
        return

    results_data = await search_videos_inline(query, max_results=5)
    articles = []
    for res in results_data:
        title = html.escape(res.get("title", ""))
        author = html.escape(res.get("author", ""))
        url = res.get("url", "")
        thumb = res.get("thumbnail")

        msg_content = InputTextMessageContent(
            message_text=f"🎬 <b>{title}</b>\n👤 المصدر: {author}\n🔗 {url}\n\n🤖 @MIDOALIAIBOT",
            parse_mode="HTML"
        )

        articles.append(
            InlineQueryResultArticle(
                id=res["id"],
                title=res["title"],
                description=f"👤 {author}",
                thumbnail_url=thumb if (thumb and thumb.startswith("http")) else None,
                input_message_content=msg_content
            )
        )

    await inline_query.answer(articles, cache_time=300)


@router.message(Command("stats"))
async def stats_handler(message: Message):
    stats = get_stats()
    user_count = stats["user_count"]
    vip_count = stats.get("vip_count", 0)
    downloads = stats["total_downloads"]

    await update_bot_description(message.bot, user_count)

    stats_text = (
        "📊 <b>إحصائيات البوت الحالية:</b>\n\n"
        f"👥 <b>إجمالي المستخدمين:</b> <code>{user_count}</code>\n"
        f"⭐ <b>المشتركين الـ VIP:</b> <code>{vip_count}</code>\n"
        f"📥 <b>إجمالي الفيديوهات والصوتيات المنزلة:</b> <code>{downloads}</code>\n\n"
        "✨ تم تحديث الوصف التعريفي للبوت في تليجرام بنجاح!"
    )
    await message.answer(stats_text, parse_mode="HTML")


@router.message(Command("help"))
async def help_handler(message: Message):
    ulang = get_user_lang(message.from_user.id, message.from_user.language_code)
    t = TEXTS[ulang]
    await message.answer(t["help"], parse_mode="HTML")


@router.callback_query(F.data.startswith("dl_pl:"))
async def handle_playlist_download(callback: CallbackQuery):
    parts = callback.data.split(":")
    mode = parts[1]
    pl_id = parts[2]

    user_id = callback.from_user.id
    ulang = get_user_lang(user_id, callback.from_user.language_code)

    pl_info = PLAYLIST_CACHE.get(pl_id)
    if not pl_info or not pl_info.get("items"):
        await callback.answer("⚠️ " + ("انتهت صلاحية قائمة التشغيل." if ulang == "ar" else "Playlist session expired."), show_alert=True)
        return

    await callback.answer()
    items = pl_info["items"]
    status_msg = await safe_edit_status(
        callback.message,
        f"⏳ <b>جاري بدء تنزيل قائمة التشغيل ({len(items)} فيديو)...</b>" if ulang == "ar" else f"⏳ <b>Starting playlist download ({len(items)} videos)...</b>"
    )

    completed = 0
    for idx, item in enumerate(items, 1):
        v_url = item["url"]
        try:
            if mode == "mp3":
                dl_res = await download_audio(v_url)
            else:
                dl_res = await download_video_quality(v_url, "480")

            if dl_res and dl_res.get("file_path") and os.path.exists(dl_res["file_path"]):
                fp = dl_res["file_path"]
                title = html.escape(dl_res.get("title", item.get("title", "")))
                caption = f"📁 [{idx}/{len(items)}] <b>{title[:70]}</b>\n🤖 @MIDOALIAIBOT"

                input_file = FSInputFile(fp)
                if mode == "mp3":
                    await callback.message.answer_audio(audio=input_file, caption=caption, parse_mode="HTML")
                else:
                    await callback.message.answer_video(video=input_file, caption=caption, parse_mode="HTML")

                cleanup_file(fp)
                record_download(user_id)
                completed += 1
        except Exception as e:
            logger.warning(f"Playlist item {idx} download failed: {e}")

        await asyncio.sleep(0.5)

    await callback.message.answer(
        f"✅ <b>تم انتهاء تنزيل قائمة التشغيل!</b>\nتم إرسال <code>{completed}</code> من <code>{len(items)}</code> ملف بنجاح." if ulang == "ar" else f"✅ <b>Playlist download completed!</b>\nSent <code>{completed}</code> of <code>{len(items)}</code> files successfully.",
        parse_mode="HTML"
    )


@router.message(F.text, ~F.text.startswith("/"))
async def handle_video_link(message: Message):
    user_id = message.from_user.id
    tg_lang = message.from_user.language_code
    is_new, user_count, ulang = register_user(user_id, tg_lang)
    if is_new:
        await update_bot_description(message.bot, user_count)

    t = TEXTS[ulang]

    is_subbed, sub_kb, sub_msg = await check_force_sub(message.bot, user_id, ulang)
    if not is_subbed:
        await message.answer(sub_msg, reply_markup=sub_kb, parse_mode="HTML")
        return

    # Daily download limit check for free users
    can_dl, rem = check_daily_limit(user_id, max_free=5)
    if not can_dl:
        limit_text = (
            "⚠️ <b>عذراً، لقد استهلكت رصيدك المجاني اليومي (5 تنزيلات).</b>\n\n"
            "للحصول على تنزيلات غير محدودة وبأعلى جودة بدون قيود يومية، يرجى الترقية إلى <b>باقة الـ VIP</b>."
        ) if ulang == "ar" else (
            "⚠️ <b>Sorry, you have reached your daily free limit (5 downloads).</b>\n\n"
            "To enjoy unlimited daily downloads with max quality, upgrade to <b>VIP Subscription</b>."
        )
        await message.answer(limit_text, reply_markup=get_vip_upgrade_keyboard(ulang), parse_mode="HTML")
        return

    urls = URL_PATTERN.findall(message.text or "")
    if not urls:
        # Search query by name
        if SEARCH_STATE.get(user_id) == "awaiting_search_query" or len((message.text or "").strip()) >= 2:
            SEARCH_STATE.pop(user_id, None)
            search_query = message.text.strip()
            status_msg = await message.answer(
                "🔍 <b>جاري البحث عن الفيديو/الأغنية...</b>" if ulang == "ar" else "🔍 <b>Searching for video/song...</b>",
                parse_mode="HTML"
            )

            search_res = await search_video_by_query(search_query)
            if not search_res or not search_res.get("url"):
                await status_msg.edit_text(
                    "❌ " + ("لم يتم العثور على نتائج للبحث." if ulang == "ar" else "No results found for search."),
                    parse_mode="HTML"
                )
                return

            url = search_res["url"]
            url_id = str(uuid.uuid4())[:8]
            URL_CACHE[url_id] = url

            title = html.escape(search_res.get("title", search_query))
            author = html.escape(search_res.get("author", ""))
            thumb = search_res.get("thumbnail")

            msg_text = (
                f"🎬 <b>{title}</b>\n\n"
                f"🌐 " + ("المنصة" if ulang == "ar" else "Platform") + f": <code>YouTube Search</code>\n"
            )
            if author:
                msg_text += f"👤 " + ("المصدر" if ulang == "ar" else "Author") + f": <code>{author}</code>\n"

            play_btn_text = "▶️ تشغيل الأغنية/الصوت فوراً (MP3)" if ulang == "ar" else "▶️ Play MP3 Audio Now"

            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(text=play_btn_text, callback_data=f"dl:mp3:{url_id}")
                    ],
                    [
                        InlineKeyboardButton(text=t["btn_video_720"], callback_data=f"dl:720:{url_id}"),
                        InlineKeyboardButton(text=t["btn_video_480"], callback_data=f"dl:480:{url_id}"),
                    ],
                    [
                        InlineKeyboardButton(text=t["btn_gif"], callback_data=f"dl:gif:{url_id}"),
                    ]
                ]
            )

            if thumb and (thumb.startswith("http://") or thumb.startswith("https://")):
                try:
                    await message.answer_photo(photo=thumb, caption=msg_text, reply_markup=keyboard, parse_mode="HTML")
                    try:
                        await status_msg.delete()
                    except Exception:
                        pass
                    return
                except Exception as e:
                    logger.warning(f"Could not send search photo thumbnail: {e}")

            await status_msg.edit_text(msg_text, reply_markup=keyboard, parse_mode="HTML")
            return

        await message.answer("⚠️ " + ("يرجى إرسال رابط فيديو صحيح أو اسم أغنية للبحث." if ulang == "ar" else "Please send a valid video link or song name to search."))
        return

    url = urls[0]
    # Check if URL is Playlist
    if "list=" in url.lower() or "playlist?list=" in url.lower():
        status_msg = await message.answer(
            "📁 <b>جاري فحص قائمة التشغيل...</b>" if ulang == "ar" else "📁 <b>Inspecting playlist...</b>",
            parse_mode="HTML"
        )
        pl_info = await extract_playlist_info(url, max_items=10)
        if pl_info and pl_info.get("items"):
            pl_id = str(uuid.uuid4())[:8]
            PLAYLIST_CACHE[pl_id] = pl_info

            pl_title = html.escape(pl_info.get("title", "Playlist"))
            item_count = pl_info.get("item_count", len(pl_info["items"]))

            pl_text = (
                f"📁 <b>قائمة تشغيل: {pl_title}</b>\n\n"
                f"🎬 <b>عدد الفيديوهات المعالجة:</b> <code>{item_count}</code> فيديو\n\n"
                f"👇 اختر طريقة التنزيل التجميعية للقائمة بالكامل:"
            ) if ulang == "ar" else (
                f"📁 <b>Playlist: {pl_title}</b>\n\n"
                f"🎬 <b>Videos count:</b> <code>{item_count}</code>\n\n"
                f"👇 Choose batch download mode for playlist:"
            )

            pl_kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="📥 تنزيل كافة الفيديوهات (MP4)" if ulang == "ar" else "📥 Download All Videos (MP4)",
                            callback_data=f"dl_pl:mp4:{pl_id}"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="🎵 تنزيل كل الصوتيات (MP3)" if ulang == "ar" else "🎵 Download All Audios (MP3)",
                            callback_data=f"dl_pl:mp3:{pl_id}"
                        )
                    ]
                ]
            )

            await status_msg.edit_text(pl_text, reply_markup=pl_kb, parse_mode="HTML")
            return

    url = urls[0]
    status_msg = await message.answer(t["inspecting"], parse_mode="HTML")

    if is_fast_mode(message.from_user.id):
        await status_msg.edit_text(t["downloading_video"].format(quality="720"), parse_mode="HTML")
        download_data = await download_video_quality(url, "720")
        if download_data and download_data.get("file_path"):
            file_path = download_data["file_path"]
            file_size_mb = download_data.get("file_size_mb") or (os.path.getsize(file_path) / (1024 * 1024))
            if file_size_mb > 49.5:
                cleanup_file(file_path)
                url_id = str(uuid.uuid4())[:8]
                URL_CACHE[url_id] = url
                opt_buttons = [
                    [InlineKeyboardButton(text="📺 تنزيل بجودة 480p SD" if ulang == "ar" else "📺 Try 480p Quality", callback_data=f"dl:480:{url_id}")],
                    [InlineKeyboardButton(text="🎵 استخراج الصوت MP3" if ulang == "ar" else "🎵 Extract MP3 Audio", callback_data=f"dl:mp3:{url_id}")]
                ]
                large_msg = (
                    f"⚠️ <b>حجم الفيديو كبير جداً ({file_size_mb:.1f} ميجابايت).</b>\n\n"
                    f"تسمح سياسة تليجرام للبوتات بإرسال ملفات حتى 50 ميجابايت فقط.\n"
                    f"اختر الجودة البديلة أو الصوت فقط بالأسفل:"
                ) if ulang == "ar" else (
                    f"⚠️ <b>Video is too large ({file_size_mb:.1f} MB).</b>\n\n"
                    f"Telegram bot API limit is 50MB.\n"
                    f"Choose lower quality or audio only below:"
                )
                await status_msg.edit_text(large_msg, reply_markup=InlineKeyboardMarkup(inline_keyboard=opt_buttons), parse_mode="HTML")
                return

            record_download(message.from_user.id)
            title = html.escape(download_data.get("title", ""))
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
            await message.answer_photo(
                photo=thumb,
                caption=msg_text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
            try:
                await status_msg.delete()
            except Exception:
                pass
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

    mode = parts[1]
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

        record_download(callback.from_user.id)

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

            file_size_mb = download_data.get("file_size_mb") or (os.path.getsize(file_path) / (1024 * 1024))
            if file_size_mb > 49.5:
                cleanup_file(file_path)
                download_data["file_path"] = None

                opt_buttons = []
                if mode == "720":
                    opt_buttons.append([
                        InlineKeyboardButton(
                            text="📺 تنزيل بجودة 480p SD" if ulang == "ar" else "📺 Try 480p Quality",
                            callback_data=f"dl:480:{url_id}"
                        )
                    ])
                elif mode == "480":
                    opt_buttons.append([
                        InlineKeyboardButton(
                            text="📺 تنزيل بجودة 360p" if ulang == "ar" else "📺 Try 360p Quality",
                            callback_data=f"dl:360:{url_id}"
                        )
                    ])

                opt_buttons.append([
                    InlineKeyboardButton(
                        text="🎵 استخراج الصوت MP3 فقط" if ulang == "ar" else "🎵 Extract MP3 Audio Only",
                        callback_data=f"dl:mp3:{url_id}"
                    )
                ])

                large_msg = (
                    f"⚠️ <b>حجم الفيديو كبير جداً ({file_size_mb:.1f} ميجابايت).</b>\n\n"
                    f"تسمح سياسة خوادم تليجرام للبوتات بإرسال ملفات حتى 50 ميجابايت فقط.\n"
                    f"الجودة المطلوبة ({mode}p) تجاوزت هذا الحد.\n\n"
                    f"💡 <b>اختر إما تنزيل بجودة أقل أو استخراج الصوت فقط:</b>"
                ) if ulang == "ar" else (
                    f"⚠️ <b>Video file is too large ({file_size_mb:.1f} MB).</b>\n\n"
                    f"Telegram bot API limits uploads to 50MB max.\n"
                    f"The requested quality ({mode}p) exceeded this limit.\n\n"
                    f"💡 <b>Choose a lower quality or extract audio:</b>"
                )

                await safe_edit_status(
                    callback.message,
                    large_msg,
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=opt_buttons)
                )
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
