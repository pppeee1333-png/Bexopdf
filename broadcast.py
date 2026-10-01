import asyncio

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from user_stats import UserStats
from utils import logger

BROADCAST = 20


def get_all_user_ids():
    try:
        stats = UserStats._load_stats()
        users = stats.get("users", {})
        return [int(uid) for uid in users.keys()]
    except Exception as e:
        logger.error(f"فشل الحصول على المستخدمين للإذاعة: {e}")
        return []


async def broadcast_entry(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    await query.answer()

    context.user_data["broadcast_active"] = True

    await query.edit_message_text(
        "📢 **إذاعة للمستخدمين**\n\n"
        "أرسل الآن الرسالة التي تريد إرسالها إلى جميع المستخدمين.\n\n"
        "يمكنك إرسال نص فقط حاليًا.\n\n"
        "للإلغاء أرسل `/cancel`.",
        parse_mode="Markdown"
    )

    return BROADCAST


async def broadcast_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    if not update.effective_message:
        return ConversationHandler.END

    text = update.effective_message.text

    if not text:
        await update.effective_message.reply_text(
            "❌ الإذاعة تدعم الرسائل النصية فقط حاليًا."
        )
        return BROADCAST

    if text == "/cancel":
        context.user_data.pop("broadcast_active", None)

        await update.effective_message.reply_text(
            "✅ تم إلغاء الإذاعة."
        )

        return ConversationHandler.END

    users = get_all_user_ids()

    if not users:
        await update.effective_message.reply_text(
            "📭 لا يوجد مستخدمون مسجلون."
        )
        return ConversationHandler.END

    await update.effective_message.reply_text(
        f"📢 بدأت الإذاعة...\n\n"
        f"👥 المستهدفون: {len(users)}\n"
        f"⏳ يرجى الانتظار..."
    )

    success = 0
    failed = 0

    for user_id in users:
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=text
            )

            success += 1

            # تقليل الضغط على Telegram والـVPS
            await asyncio.sleep(0.05)

        except Exception as e:
            failed += 1
            logger.warning(
                f"فشل إرسال الإذاعة إلى {user_id}: {e}"
            )

    context.user_data.pop("broadcast_active", None)

    await update.effective_message.reply_text(
        "📢 **اكتملت الإذاعة**\n\n"
        f"👥 المستهدفون: {len(users)}\n"
        f"✅ تم الإرسال: {success}\n"
        f"❌ فشل الإرسال: {failed}",
        parse_mode="Markdown"
    )

    return ConversationHandler.END
