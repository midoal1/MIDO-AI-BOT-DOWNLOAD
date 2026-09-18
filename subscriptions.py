import html
import logging
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import (
    Message, CallbackQuery, PreCheckoutQuery, LabeledPrice,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from database import (
    is_vip, activate_vip, get_user_lang, get_log_channel,
    is_admin, record_download, check_daily_limit
)

logger = logging.getLogger(__name__)
sub_router = Router()


def get_vip_upgrade_keyboard(lang: str = "ar"):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⭐ " + ("شراء بنجوم تليجرام (تفعيل فوري)" if lang == "ar" else "Buy with Telegram Stars (Instant)"),
                    callback_data="buy_stars:30"
                )
            ],
            [
                InlineKeyboardButton(
                    text="💳 " + ("الدفع بالتحويل (إرسال إيصال الدفع)" if lang == "ar" else "Pay via Transfer (Send Receipt)"),
                    callback_data="buy_receipt"
                )
            ]
        ]
    )


@sub_router.message(Command("vip"))
async def vip_info_command(message: Message):
    lang = get_user_lang(message.from_user.id, message.from_user.language_code)
    vip_active, exp_date = is_vip(message.from_user.id)
    
    if vip_active:
        msg = (
            f"⭐ <b>أنت مشترك في باقة VIP حالياً!</b>\n\n"
            f"📅 <b>اشتراكك ساري حتى:</b> <code>{exp_date}</code>\n"
            "✨ تتمتع بتنزيلات غير محدودة وبأعلى جودة بدون أي إعلانات أو حدود يومية."
        ) if lang == "ar" else (
            f"⭐ <b>You are an active VIP member!</b>\n\n"
            f"📅 <b>Expires on:</b> <code>{exp_date}</code>\n"
            "✨ Enjoy unlimited downloads with max quality and zero ads."
        )
        await message.answer(msg, parse_mode="HTML")
    else:
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
        await message.answer(msg, reply_markup=get_vip_upgrade_keyboard(lang), parse_mode="HTML")


@sub_router.callback_query(F.data.startswith("buy_stars:"))
async def handle_buy_stars(callback: CallbackQuery):
    days = int(callback.data.split(":")[1])
    prices = [LabeledPrice(label="VIP Subscription (30 Days)", amount=150)]  # 150 Stars
    
    try:
        await callback.bot.send_invoice(
            chat_id=callback.from_user.id,
            title="⭐ اشتراك VIP - بوت MIDO AI",
            description=f"تنزيل غير محدود بدون إعلانات وبأعلى جودة لمدة {days} يوماً.",
            payload=f"vip_sub_{days}_{callback.from_user.id}",
            provider_token="",  # Empty provider_token for Telegram Stars XTR currency
            currency="XTR",
            prices=prices,
            start_parameter="vip_subscription"
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Error sending Stars invoice: {e}")
        await callback.answer("⚠️ تعذر فتح الفاتورة حالياً.", show_alert=True)


@sub_router.pre_checkout_query()
async def pre_checkout_handler(pre_checkout_query: PreCheckoutQuery):
    await pre_checkout_query.answer(ok=True)


@sub_router.message(F.successful_payment)
async def successful_payment_handler(message: Message):
    payload = message.successful_payment.invoice_payload
    days = 30
    if "vip_sub_" in payload:
        try:
            days = int(payload.split("_")[2])
        except Exception:
            days = 30
            
    expiry_date = activate_vip(message.from_user.id, days)
    
    await message.answer(
        f"🎉 <b>مبروك! تم دفع {message.successful_payment.total_amount} نجمة وتفعيل اشتراك VIP بنجاح!</b>\n\n"
        f"📅 <b>الاشتراك ساري حتى:</b> <code>{expiry_date}</code>\n"
        "✨ تستمتع الآن بتنزيلات غير محدودة وبأعلى جودة!",
        parse_mode="HTML"
    )


@sub_router.callback_query(F.data == "buy_receipt")
async def handle_buy_receipt(callback: CallbackQuery):
    lang = get_user_lang(callback.from_user.id, callback.from_user.language_code)
    text = (
        "💳 <b>طريقة الدفع بالتحويل المباشر:</b>\n\n"
        "1. قم بتحويل قيمة الاشتراك (عبر <b>فودافون كاش / InstaPay</b>).\n"
        "2. قم بإلتقاط **صورة إيصال التحويل**.\n"
        "3. أرسل الصورة هنا مباشرة في هذه المحادثة للبوت.\n\n"
        "⚡ سيتم استلام الإيصال وتحويله أونلاين للقناة الرسمية للتأكيد والتفعيل فوراً!"
    ) if lang == "ar" else (
        "💳 <b>Manual Transfer Payment:</b>\n\n"
        "1. Transfer subscription fee via <b>Vodafone Cash / InstaPay</b>.\n"
        "2. Take a screenshot of the payment receipt.\n"
        "3. Send the photo here directly in chat to the bot.\n\n"
        "⚡ Your receipt will be forwarded to our team channel for instant verification!"
    )
    await callback.answer()
    await callback.message.answer(text, parse_mode="HTML")


# Handle receipt photo uploaded by user
@sub_router.message(F.photo, F.chat.type == "private")
async def handle_receipt_photo(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or "بدون معرف"
    full_name = html.escape(message.from_user.full_name or "مستخدم")
    log_channel = get_log_channel()
    photo_id = message.photo[-1].file_id

    channel_caption = (
        "🧾 <b>طلب تفعيل اشتراك VIP جديد!</b>\n\n"
        f"👤 <b>الاسم الكامل:</b> {full_name}\n"
        f"🌐 <b>اسم المستخدم:</b> @{username}\n"
        f"🆔 <b>الـ ID الخاص به:</b> <code>{user_id}</code>\n"
        f"📅 <b>الباقة المطلوبة:</b> VIP لمدة 30 يوماً\n\n"
        "اضغط على الأزرار أدناه للتحقق والتفعيل أونلاين:"
    )

    channel_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ تفعيل الاشتراك (30 يوم)", callback_data=f"sub_act:{user_id}:30"),
                InlineKeyboardButton(text="❌ رفض الطلب", callback_data=f"sub_rej:{user_id}")
            ]
        ]
    )

    try:
        # Forward receipt photo + details + buttons to channel @midoaidownload
        await message.bot.send_photo(
            chat_id=log_channel,
            photo=photo_id,
            caption=channel_caption,
            reply_markup=channel_keyboard,
            parse_mode="HTML"
        )
        
        await message.answer(
            "✅ <b>تم استلام صورة الإيصال وتحويلها بنجاح للقناة الرسمية للتأكيد والتفعيل!</b>\n"
            "سيتم تفعيل حسابك كـ VIP وإشعارك فور مراجعة التحويل أونلاين.",
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Failed to send receipt photo to channel {log_channel}: {e}")
        await message.answer(
            "⚠️ <b>تعذر إرسال الإيصال للقناة حالياً.</b>\nيرجى التأكد من رفع البوت كـ Admin في القناة.",
            parse_mode="HTML"
        )


# Handle activation/rejection buttons clicked inside the Channel @midoaidownload
@sub_router.callback_query(F.data.startswith("sub_act:") | F.data.startswith("sub_rej:"))
async def handle_channel_activation_callback(callback: CallbackQuery):
    parts = callback.data.split(":")
    action = parts[0]  # "sub_act" or "sub_rej"
    target_user_id = int(parts[1])
    admin_user = callback.from_user
    admin_name = html.escape(admin_user.full_name or admin_user.username or "Admin")

    if action == "sub_act":
        days = int(parts[2]) if len(parts) > 2 else 30
        expiry_date = activate_vip(target_user_id, days)

        # Notify the user in private chat
        try:
            await callback.bot.send_message(
                chat_id=target_user_id,
                text=(
                    f"🎉 <b>مبروك! تم التحقق من إيصال التحويل وتفعيل اشتراك VIP الخاص بك بنجاح!</b>\n\n"
                    f"📅 <b>الاشتراك ساري حتى:</b> <code>{expiry_date}</code>\n"
                    "✨ استمتع الآن بتنزيلات غير محدودة وبأعلى جودة!"
                ),
                parse_mode="HTML"
            )
        except Exception as e:
            logger.warning(f"Could not notify user {target_user_id} of VIP activation: {e}")

        # Update caption in channel
        orig_caption = callback.message.caption or ""
        new_caption = (
            f"{orig_caption}\n\n"
            f"✅ <b>تم تفعيل الاشتراك بنجاح!</b>\n"
            f"👤 بواسطة: <b>{admin_name}</b> (ساري حتى {expiry_date})"
        )
        await callback.message.edit_caption(caption=new_caption, reply_markup=None, parse_mode="HTML")
        await callback.answer("✅ تم تفعيل الاشتراك للمستخدم بنجاح!")

    elif action == "sub_rej":
        # Notify user of rejection
        try:
            await callback.bot.send_message(
                chat_id=target_user_id,
                text=(
                    "❌ <b>عذراً، تعذر التثبت من إيصال التحويل المرفق.</b>\n"
                    "يرجى التأكد من الصورة وإرسال إيصال جديد أو التواصل مع الدعم."
                ),
                parse_mode="HTML"
            )
        except Exception as e:
            logger.warning(f"Could not notify user {target_user_id} of rejection: {e}")

        orig_caption = callback.message.caption or ""
        new_caption = (
            f"{orig_caption}\n\n"
            f"❌ <b>تم رفض الطلب بواسطة:</b> <b>{admin_name}</b>"
        )
        await callback.message.edit_caption(caption=new_caption, reply_markup=None, parse_mode="HTML")
        await callback.answer("❌ تم رفض الطلب.")
