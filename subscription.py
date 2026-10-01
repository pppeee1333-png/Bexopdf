import json
from pathlib import Path
from typing import List
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from config import Config
from utils import logger

CHANNELS_FILE = Path(Config.TEMP_DIR).parent / "channels.json"

class SubscriptionSystem:
    @staticmethod
    def load_channels() -> List[str]:
        try:
            if CHANNELS_FILE.exists():
                with open(CHANNELS_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            return []
        except Exception as e:
            logger.error(f"خطأ في تحميل القنوات: {e}")
            return []
    
    @staticmethod
    def save_channels(channels: List[str]) -> bool:
        try:
            with open(CHANNELS_FILE, "w", encoding="utf-8") as f:
                json.dump(channels, f, ensure_ascii=False, indent=2)
            Config.FORCED_CHANNELS = channels
            return True
        except Exception as e:
            logger.error(f"خطأ في حفظ القنوات: {e}")
            return False
    
    @staticmethod
    def get_all_channels() -> List[str]:
        channels = [Config.FORCED_CHANNEL] if Config.FORCED_CHANNEL else []
        channels += Config.FORCED_CHANNELS
        return list(dict.fromkeys(channels))
    
    @staticmethod
    def is_admin(user_id: int) -> bool:
        return user_id in Config.ADMINS

async def check_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user_id = update.effective_user.id
    
    if SubscriptionSystem.is_admin(user_id):
        return True
    
    channels = SubscriptionSystem.get_all_channels()
    
    if not channels:
        return True
    
    unsubscribed = []
    
    for channel in channels:
        channel_name = channel.strip()
        if channel_name.startswith("@"):
            channel_name = channel_name[1:]
        
        try:
            chat_member = await context.bot.get_chat_member(
                chat_id=f"@{channel_name}",
                user_id=user_id
            )
            
            status = chat_member.status
            if status not in ["member", "administrator", "creator"]:
                unsubscribed.append(channel_name)
                
        except Exception as e:
            logger.error(f"خطأ في التحقق من قناة {channel_name}: {e}")
            unsubscribed.append(channel_name)
    
    if unsubscribed:
        await send_subscription_required(update, context, unsubscribed)
        return False
    
    return True

async def send_subscription_required(update: Update, context: ContextTypes.DEFAULT_TYPE, channels: List[str]):
    keyboard = []
    
    for channel in channels:
        channel_name = channel.strip()
        if channel_name.startswith("@"):
            channel_name = channel_name[1:]
        keyboard.append([InlineKeyboardButton(
            f"📢 اشترك في @{channel_name}",
            url=f"https://t.me/{channel_name}"
        )])
    
    keyboard.append([InlineKeyboardButton(
        "✅ تحقق من الاشتراك",
        callback_data="check_subscription"
    )])
    
    inline_keyboard = InlineKeyboardMarkup(keyboard)
    
    channels_text = "\n".join([f"• @{ch}" for ch in channels])
    
    message_text = (
        "🔒 **يجب الاشتراك في القنوات التالية لاستخدام البوت:**\n\n"
        f"{channels_text}\n\n"
        "📌 **الخطوات:**\n"
        "1️⃣ اضغط على أزرار الاشتراك\n"
        "2️⃣ اشترك في جميع القنوات\n"
        "3️⃣ اضغط على 'تحقق من الاشتراك'\n\n"
        "✅ بعد الاشتراك، ستتمكن من استخدام جميع ميزات البوت!"
    )
    
    await update.message.reply_text(
        message_text,
        reply_markup=inline_keyboard,
        parse_mode="Markdown"
    )

async def check_subscription_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    
    if SubscriptionSystem.is_admin(user_id):
        await query.edit_message_text("✅ أنت مشرف، تم تجاوز التحقق!")
        return
    
    channels = SubscriptionSystem.get_all_channels()
    unsubscribed = []
    
    for channel in channels:
        channel_name = channel.strip()
        if channel_name.startswith("@"):
            channel_name = channel_name[1:]
        
        try:
            chat_member = await context.bot.get_chat_member(
                chat_id=f"@{channel_name}",
                user_id=user_id
            )
            
            status = chat_member.status
            if status not in ["member", "administrator", "creator"]:
                unsubscribed.append(channel_name)
                
        except Exception:
            unsubscribed.append(channel_name)
    
    if unsubscribed:
        keyboard = []
        for channel in unsubscribed:
            keyboard.append([InlineKeyboardButton(
                f"📢 اشترك في @{channel}",
                url=f"https://t.me/{channel}"
            )])
        keyboard.append([InlineKeyboardButton(
            "🔄 تحقق مرة أخرى",
            callback_data="check_subscription"
        )])
        
        await query.edit_message_text(
            "❌ **لم يتم العثور على اشتراك!**\n\n"
            "📌 يرجى الاشتراك في جميع القنوات أعلاه ثم اضغط 'تحقق مرة أخرى'",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
    else:
        await query.edit_message_text(
            "✅ **تم التحقق بنجاح!**\n"
            "أنت مشترك في جميع القنوات، يمكنك الآن استخدام البوت.\n\n"
            "👋 اضغط /start للبدء",
            parse_mode="Markdown"
        )
