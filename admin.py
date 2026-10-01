import json
import os
import shutil
from pathlib import Path
from typing import List
from datetime import datetime

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, ConversationHandler

from config import Config
from utils import logger, format_size
from maintenance import MaintenanceSystem
from broadcast import broadcast_entry, BROADCAST

CHANNELS_FILE = Path(Config.BASE_DIR) / "channels.json"
ADD_CHANNEL = 10


class AdminSystem:

    @staticmethod
    def normalize_channel(channel: str) -> str:
        return channel.strip().lstrip("@").strip()

    @staticmethod
    def load_channels() -> List[str]:
        try:
            channels = []

            if CHANNELS_FILE.exists():
                with open(CHANNELS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)

                if isinstance(data, list):
                    channels = [
                        AdminSystem.normalize_channel(str(x))
                        for x in data
                        if str(x).strip()
                    ]

            # إذا كان الملف فارغًا، نستخدم إعدادات .env القديمة
            if not channels:
                if Config.FORCED_CHANNEL:
                    channels.append(
                        AdminSystem.normalize_channel(Config.FORCED_CHANNEL)
                    )

                for channel in getattr(Config, "FORCED_CHANNELS", []):
                    channel = AdminSystem.normalize_channel(channel)
                    if channel and channel not in channels:
                        channels.append(channel)

                if channels:
                    AdminSystem.save_channels(channels)

            return list(dict.fromkeys(channels))

        except Exception as e:
            logger.error(f"خطأ في تحميل القنوات: {e}")
            return []

    @staticmethod
    def save_channels(channels: List[str]) -> bool:
        try:
            cleaned = []

            for channel in channels:
                channel = AdminSystem.normalize_channel(str(channel))

                if channel and channel not in cleaned:
                    cleaned.append(channel)

            with open(CHANNELS_FILE, "w", encoding="utf-8") as f:
                json.dump(
                    cleaned,
                    f,
                    ensure_ascii=False,
                    indent=2
                )

            # تحديث الذاكرة مباشرة
            Config.FORCED_CHANNELS = cleaned

            return True

        except Exception as e:
            logger.error(f"خطأ في حفظ القنوات: {e}")
            return False

    @staticmethod
    def get_all_channels() -> List[str]:
        return AdminSystem.load_channels()

    @staticmethod
    def is_admin(user_id: int) -> bool:
        return user_id in Config.ADMINS


def get_system_stats() -> dict:
    try:
        disk_usage = shutil.disk_usage("/")

        temp_files = [
            p for p in Path(Config.TEMP_DIR).rglob("*")
            if p.is_file()
        ]

        temp_size = sum(
            f.stat().st_size
            for f in temp_files
            if f.exists()
        )

        try:
            from main import user_sessions
            from utils import active_users

            active_sessions = len(user_sessions)
            busy_users = len(active_users)

        except Exception:
            active_sessions = 0
            busy_users = 0

        try:
            from user_stats import UserStats
            user_stats = UserStats.get_stats()
        except Exception:
            user_stats = {}

        return {
            "disk_total": disk_usage.total,
            "disk_used": disk_usage.used,
            "disk_free": disk_usage.free,
            "disk_percent": (
                disk_usage.used / disk_usage.total
            ) * 100,

            "temp_files": len(temp_files),
            "temp_size": temp_size,

            "active_sessions": active_sessions,
            "busy_users": busy_users,

            "total_users": user_stats.get("total_users", 0),
            "today_users": user_stats.get("today_users", 0),
            "weekly_active": user_stats.get("weekly_active", 0),
            "monthly_active": user_stats.get("monthly_active", 0),
            "total_interactions": user_stats.get(
                "total_interactions", 0
            ),

            "timestamp": datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        }

    except Exception as e:
        logger.error(f"❌ فشل الحصول على الإحصائيات: {e}")
        return {"error": str(e)}


def clean_temp_files() -> dict:
    try:
        temp_path = Path(Config.TEMP_DIR)

        if not temp_path.exists():
            return {"deleted": 0, "size": 0}

        deleted = 0
        size = 0

        for file_path in temp_path.rglob("*"):
            if file_path.is_file():
                try:
                    size += file_path.stat().st_size
                    file_path.unlink(missing_ok=True)
                    deleted += 1
                except OSError:
                    pass

        for directory in sorted(
            [p for p in temp_path.rglob("*") if p.is_dir()],
            reverse=True
        ):
            try:
                if not any(directory.iterdir()):
                    directory.rmdir()
            except OSError:
                pass

        return {
            "deleted": deleted,
            "size": size
        }

    except Exception as e:
        return {"error": str(e)}


async def admin_panel(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    user = update.effective_user

    if not user or not AdminSystem.is_admin(user.id):
        message = update.effective_message

        if message:
            await message.reply_text(
                "❌ هذا الأمر مخصص للمشرفين فقط!"
            )
        return

    channels = AdminSystem.get_all_channels()

    if channels:
        channels_list = "\n".join(
            f"{i}️⃣ @{channel}"
            for i, channel in enumerate(channels, 1)
        )
    else:
        channels_list = "📭 لا توجد قنوات"

    stats = get_system_stats()

    if "error" not in stats:
        session_info = (
            f"👥 المستخدمون: {stats['total_users']}\n"
            f"📅 اليوم: {stats['today_users']}\n"
            f"🔥 7 أيام: {stats['weekly_active']}\n"
            f"📆 الشهر: {stats['monthly_active']}\n"
            f"⚙️ جلسات الآن: {stats['active_sessions']}\n"
            f"🛠️ قيد المعالجة: {stats['busy_users']}\n"
        )

        temp_info = (
            f"📁 المؤقت: {stats['temp_files']} "
            f"({format_size(stats['temp_size'])})\n"
        )

        disk_info = (
            f"💾 التخزين: "
            f"{format_size(stats['disk_used'])} / "
            f"{format_size(stats['disk_total'])} "
            f"({stats['disk_percent']:.1f}%)"
        )

    else:
        session_info = "⚠️ تعذر جلب الإحصائيات\n"
        temp_info = ""
        disk_info = ""

    text = (
        "👑 **لوحة تحكم المشرف**\n\n"

        "📢 **الاشتراك الإجباري**\n"
        f"{channels_list}\n\n"

        "📊 **إحصائيات سريعة**\n"
        f"{session_info}"
        f"{temp_info}"
        f"{disk_info}\n\n"

        "اختر العملية:"
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "📢 الاشتراك الإجباري",
                callback_data="admin_subscription"
            )
        ],
        [
            InlineKeyboardButton(
                "🛠️ الصيانة",
                callback_data="admin_maintenance"
            ),
            InlineKeyboardButton(
                "📢 الإذاعة",
                callback_data="admin_broadcast"
            )
        ],
        [
            InlineKeyboardButton(
                "📊 إحصائيات",
                callback_data="admin_stats"
            ),
            InlineKeyboardButton(
                "🗑️ تنظيف",
                callback_data="admin_clean"
            )
        ],
        [
            InlineKeyboardButton(
                "❌ إغلاق",
                callback_data="admin_close"
            )
        ]
    ])

    message = update.effective_message

    if message:
        await message.reply_text(
            text,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )


async def admin_callback_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query

    if not query:
        return

    await query.answer()

    user = update.effective_user

    if not user or not AdminSystem.is_admin(user.id):
        await query.edit_message_text("❌ غير مصرح!")
        return

    action = query.data

    # =========================
    # إغلاق
    # =========================

    if action == "admin_close":
        await query.edit_message_text("✅ تم إغلاق لوحة التحكم")
        return ConversationHandler.END

    # =========================
    # الاشتراك الإجباري
    # =========================

    if action == "admin_subscription":
        channels = AdminSystem.get_all_channels()

        if channels:
            text = (
                "📢 **إدارة الاشتراك الإجباري**\n\n"
                "القنوات الحالية:\n\n"
            )

            for i, channel in enumerate(channels, 1):
                text += f"{i}️⃣ @{channel}\n"

        else:
            text = (
                "📢 **إدارة الاشتراك الإجباري**\n\n"
                "📭 لا توجد قنوات إجبارية حاليًا."
            )

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "➕ إضافة قناة",
                    callback_data="admin_add_channel"
                )
            ],
            [
                InlineKeyboardButton(
                    "➖ حذف قناة",
                    callback_data="admin_remove_channel"
                )
            ],
            [
                InlineKeyboardButton(
                    "📋 تحديث القائمة",
                    callback_data="admin_subscription"
                )
            ],
            [
                InlineKeyboardButton(
                    "⬅️ رجوع",
                    callback_data="admin_back"
                )
            ]
        ])

        await query.edit_message_text(
            text,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
        return

    # =========================
    # إضافة قناة
    # =========================

    if action == "admin_add_channel":
        context.user_data["admin_action"] = "add_channel"

        await query.edit_message_text(
            "➕ **إضافة قناة للاشتراك الإجباري**\n\n"
            "أرسل معرف القناة:\n\n"
            "مثال:\n"
            "`@bexo50`\n\n"
            "أو:\n"
            "`bexo50`\n\n"
            "⚠️ يجب أن يكون البوت مشرفًا في القناة.\n\n"
            "للإلغاء أرسل `/cancel`.",
            parse_mode="Markdown"
        )

        return ADD_CHANNEL

    # =========================
    # حذف قناة
    # =========================

    if action == "admin_remove_channel":
        channels = AdminSystem.get_all_channels()

        if not channels:
            await query.edit_message_text(
                "📭 لا توجد قنوات لحذفها.",
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            "⬅️ رجوع",
                            callback_data="admin_subscription"
                        )
                    ]
                ])
            )
            return

        keyboard = []

        for channel in channels:
            keyboard.append([
                InlineKeyboardButton(
                    f"❌ حذف @{channel}",
                    callback_data=f"remove_channel:{channel}"
                )
            ])

        keyboard.append([
            InlineKeyboardButton(
                "⬅️ رجوع",
                callback_data="admin_subscription"
            )
        ])

        await query.edit_message_text(
            "🗑️ **حذف قناة**\n\n"
            "اختر القناة التي تريد حذفها:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        return

    # =========================
    # تنفيذ حذف القناة
    # =========================

    if action.startswith("remove_channel:"):
        channel = action.split(":", 1)[1]
        channel = AdminSystem.normalize_channel(channel)

        channels = AdminSystem.get_all_channels()

        if channel not in channels:
            await query.edit_message_text(
                "❌ القناة غير موجودة."
            )
            return

        channels.remove(channel)

        if AdminSystem.save_channels(channels):
            await query.edit_message_text(
                f"✅ تم حذف القناة `@{channel}` من الاشتراك الإجباري.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            "📢 إدارة القنوات",
                            callback_data="admin_subscription"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "⬅️ لوحة التحكم",
                            callback_data="admin_back"
                        )
                    ]
                ])
            )
        else:
            await query.edit_message_text(
                "❌ فشل حفظ التغييرات."
            )

        return

    # =========================
    # رجوع
    # =========================

    if action == "admin_back":
        await query.edit_message_text(
            "👑 **لوحة تحكم المشرف**\n\n"
            "استخدم الأزرار أدناه:",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "📢 الاشتراك الإجباري",
                        callback_data="admin_subscription"
                    )
                ],
                [
                    InlineKeyboardButton(
                        "📊 إحصائيات",
                        callback_data="admin_stats"
                    ),
                    InlineKeyboardButton(
                        "🗑️ تنظيف",
                        callback_data="admin_clean"
                    )
                ],
                [
                    InlineKeyboardButton(
                        "❌ إغلاق",
                        callback_data="admin_close"
                    )
                ]
            ]),
            parse_mode="Markdown"
        )
        return

    # =========================
    # الصيانة
    # =========================

    if action == "admin_maintenance":
        enabled = MaintenanceSystem.is_enabled()

        status = "🟢 مفعلة" if enabled else "🔴 متوقفة"
        button_text = "🟢 إيقاف الصيانة" if enabled else "🔴 تشغيل الصيانة"

        text = (
            "🛠️ **وضع الصيانة**\n\n"
            f"الحالة الحالية: {status}\n\n"
            "عند تفعيل الصيانة، سيتم منع المستخدمين "
            "العاديين من استخدام البوت.\n"
            "👑 الأدمن يستطيع استخدام البوت بشكل طبيعي."
        )

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    button_text,
                    callback_data="admin_toggle_maintenance"
                )
            ],
            [
                InlineKeyboardButton(
                    "⬅️ رجوع",
                    callback_data="admin_back"
                )
            ]
        ])

        await query.edit_message_text(
            text,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
        return

    if action == "admin_toggle_maintenance":
        current = MaintenanceSystem.is_enabled()
        new_state = not current

        if MaintenanceSystem.set_enabled(new_state):
            status = "🟢 مفعلة" if new_state else "🔴 متوقفة"

            await query.edit_message_text(
                "🛠️ **تم تحديث وضع الصيانة**\n\n"
                f"الحالة: {status}",
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            "🛠️ إدارة الصيانة",
                            callback_data="admin_maintenance"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "⬅️ لوحة التحكم",
                            callback_data="admin_back"
                        )
                    ]
                ]),
                parse_mode="Markdown"
            )
        else:
            await query.edit_message_text(
                "❌ فشل حفظ حالة الصيانة."
            )

        return

    # =========================
    # الإذاعة
    # =========================

    if action == "admin_broadcast":
        await query.answer()

        context.user_data["broadcast_active"] = True

        await query.edit_message_text(
            "📢 **إذاعة للمستخدمين**\n\n"
            "أرسل الآن الرسالة التي تريد إرسالها إلى جميع المستخدمين.\n\n"
            "📝 حاليًا الإذاعة تدعم النصوص.\n\n"
            "للإلغاء أرسل `/cancel`.",
            parse_mode="Markdown"
        )

        return BROADCAST

    # =========================
    # الإحصائيات
    # =========================

    if action == "admin_stats":
        stats = get_system_stats()

        if "error" in stats:
            await query.edit_message_text(
                f"❌ خطأ: {stats['error']}"
            )
            return

        text = (
            "📊 **إحصائيات البوت والنظام**\n\n"

            f"🕐 الوقت: {stats['timestamp']}\n\n"

            "👥 **المستخدمون:**\n"
            f"• إجمالي المستخدمين: {stats['total_users']} شخص\n"
            f"• مستخدمو اليوم: {stats['today_users']}\n"
            f"• النشطون خلال 7 أيام: {stats['weekly_active']}\n"
            f"• النشطون هذا الشهر: {stats['monthly_active']}\n"
            f"• إجمالي التفاعلات: {stats['total_interactions']}\n"
            f"• الجلسات الحالية: {stats['active_sessions']}\n"
            f"• المستخدمون قيد المعالجة: {stats['busy_users']}\n\n"

            "💾 **التخزين:**\n"
            f"• الإجمالي: {format_size(stats['disk_total'])}\n"
            f"• المستخدم: {format_size(stats['disk_used'])}\n"
            f"• المتاح: {format_size(stats['disk_free'])}\n"
            f"• النسبة: {stats['disk_percent']:.1f}%\n\n"

            "📁 **الملفات المؤقتة:**\n"
            f"• العدد: {stats['temp_files']}\n"
            f"• الحجم: {format_size(stats['temp_size'])}"
        )

        await query.edit_message_text(
            text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "⬅️ رجوع",
                        callback_data="admin_back"
                    )
                ]
            ])
        )
        return

    # =========================
    # تنظيف
    # =========================

    if action == "admin_clean":
        result = clean_temp_files()

        if "error" in result:
            await query.edit_message_text(
                f"❌ خطأ: {result['error']}"
            )
            return

        await query.edit_message_text(
            "🗑️ **تم تنظيف الملفات المؤقتة**\n\n"
            f"📁 الملفات المحذوفة: {result['deleted']}\n"
            f"💾 الحجم المحذوف: {format_size(result['size'])}",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "⬅️ رجوع",
                        callback_data="admin_back"
                    )
                ]
            ])
        )
        return


async def admin_add_channel_entry(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query

    if not query:
        return ConversationHandler.END

    await query.answer()

    user = update.effective_user

    if not user or not AdminSystem.is_admin(user.id):
        await query.edit_message_text("❌ غير مصرح!")
        return ConversationHandler.END

    context.user_data["admin_action"] = "add_channel"

    await query.edit_message_text(
        "➕ **إضافة قناة للاشتراك الإجباري**\n\n"
        "أرسل معرف القناة:\n\n"
        "مثال:\n"
        "`@bexo50`\n\n"
        "⚠️ يجب أن يكون البوت مشرفًا في القناة.\n\n"
        "للإلغاء أرسل `/cancel`.",
        parse_mode="Markdown"
    )

    return ADD_CHANNEL


async def add_channel_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    user = update.effective_user

    if not user or not AdminSystem.is_admin(user.id):
        await update.effective_message.reply_text(
            "❌ غير مصرح!"
        )
        return ConversationHandler.END

    channel_input = update.effective_message.text.strip()

    if channel_input.lower() == "/cancel":
        await update.effective_message.reply_text(
            "✅ تم إلغاء العملية."
        )
        return ConversationHandler.END

    channel = AdminSystem.normalize_channel(channel_input)

    if not channel:
        await update.effective_message.reply_text(
            "❌ معرف القناة غير صالح.\n\n"
            "مثال: `@bexo50`",
            parse_mode="Markdown"
        )
        return ADD_CHANNEL

    # منع الروابط بدل username
    if "t.me/" in channel.lower() or "http://" in channel.lower() or "https://" in channel.lower():
        await update.effective_message.reply_text(
            "❌ أرسل معرف القناة فقط.\n\n"
            "مثال:\n"
            "`@bexo50`",
            parse_mode="Markdown"
        )
        return ADD_CHANNEL

    try:
        # التأكد أن القناة موجودة
        chat = await context.bot.get_chat(f"@{channel}")

        if chat.type not in ["channel", "supergroup"]:
            await update.effective_message.reply_text(
                "❌ هذا المعرف ليس قناة أو مجموعة عامة."
            )
            return ADD_CHANNEL

        # التأكد من صلاحية البوت
        bot_member = await context.bot.get_chat_member(
            chat_id=f"@{channel}",
            user_id=context.bot.id
        )

        if bot_member.status not in [
            "administrator",
            "creator"
        ]:
            await update.effective_message.reply_text(
                f"⚠️ البوت ليس مشرفًا في @{channel}.\n\n"
                "اجعل البوت مشرفًا ثم حاول مرة أخرى."
            )
            return ADD_CHANNEL

        channels = AdminSystem.get_all_channels()

        if channel in channels:
            await update.effective_message.reply_text(
                f"⚠️ القناة @{channel} موجودة بالفعل."
            )
            return ADD_CHANNEL

        channels.append(channel)

        if not AdminSystem.save_channels(channels):
            await update.effective_message.reply_text(
                "❌ فشل حفظ القناة."
            )
            return ADD_CHANNEL

        await update.effective_message.reply_text(
            f"✅ **تمت إضافة القناة بنجاح!**\n\n"
            f"📢 القناة: @{channel}\n"
            f"🔒 أصبحت الآن ضمن الاشتراك الإجباري.",
            parse_mode="Markdown"
        )

        return ConversationHandler.END

    except Exception as e:
        logger.error(
            f"خطأ في إضافة القناة @{channel}: {e}"
        )

        await update.effective_message.reply_text(
            f"❌ لم أستطع الوصول إلى القناة @{channel}.\n\n"
            "تأكد من:\n"
            "• اسم المستخدم صحيح\n"
            "• القناة عامة\n"
            "• البوت موجود في القناة\n"
            "• البوت مشرف في القناة"
        )

        return ADD_CHANNEL
