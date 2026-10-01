import os
import time
import asyncio
import gc
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List, Dict

from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, filters,
    ContextTypes, ConversationHandler, CallbackQueryHandler,
)
from pypdf import PdfReader

from config import Config
from utils import (
    logger, set_user_busy, is_user_busy, clean_old_files,
    validate_page_range, format_size, safe_remove, ensure_extension,
    get_file_extension, temp_dir_size, ensure_temp_capacity,
)
from file_engine import FileEngine
from keyboards import (
    MAIN_MENU,
    ACTION_MENU,
    CANCEL_BTN,
    ADMIN_MENU,
    compression_levels_keyboard,
)
from admin import AdminSystem, admin_panel, admin_callback_handler, add_channel_handler, admin_add_channel_entry, ADD_CHANNEL
from subscription import check_subscription, check_subscription_callback
from user_stats import UserStats
from user_api import start_user_api, stop_user_api
from maintenance import MaintenanceSystem
from broadcast import broadcast_handler, BROADCAST

Config.ensure_dirs()

@dataclass
class Session:
    files: List[str] = field(default_factory=list)
    action: Optional[str] = None
    val1: Optional[str] = None
    custom_name: Optional[str] = None
    expecting_name: bool = False
    expecting_data: bool = False
    last_active: float = field(default_factory=time.time)
    text_title: Optional[str] = None
    compression_level: Optional[str] = None

user_sessions: Dict[int, Session] = {}
SELECT_ACTION, WAIT_FILE, WAIT_DATA, WAIT_NAME = range(4)
JOB_SEMAPHORE = asyncio.Semaphore(max(1, Config.MAX_CONCURRENT_JOBS))


def _cleanup_session(session: Session):
    for file_path in list(session.files):
        safe_remove(file_path)
    session.files.clear()
    gc.collect()


def _local_file_path(file_obj) -> Optional[str]:
    value = getattr(file_obj, "file_path", None)
    if value and os.path.isabs(value) and os.path.isfile(value):
        return value
    return None


async def _get_downloaded_path(context, file_id: str, destination: str) -> str:
    """Use the absolute path returned by Local Bot API when available."""
    file_obj = await context.bot.get_file(file_id)
    local_path = _local_file_path(file_obj)
    if local_path:
        # Local Bot API already downloaded the file. Copy it into our isolated temp dir
        # so the app can safely remove it after processing.
        import shutil
        shutil.copy2(local_path, destination)
        safe_remove(local_path)
        return destination
    await file_obj.download_to_drive(destination)
    return destination


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    UserStats.track_user(uid, update.effective_user.username, update.effective_user.first_name)

    if MaintenanceSystem.is_enabled() and not AdminSystem.is_admin(uid):
        await update.message.reply_text(
            "🛠️ **البوت تحت الصيانة حاليًا**\n\n"
            "نعتذر عن الإزعاج، يرجى المحاولة لاحقًا. 🔧",
            parse_mode="Markdown"
        )
        return SELECT_ACTION

    if not await check_subscription(update, context):
        return SELECT_ACTION
    old = user_sessions.pop(uid, None)
    if old:
        _cleanup_session(old)
    user_sessions[uid] = Session()
    welcome = (
        "👋 **مرحباً بك في بوت المستندات!**\n\n"
        "📁 الميزات المتاحة:\n"
        "• 📎 دمج PDF\n• 🖼️ صور لـ PDF\n• 📸 استخراج صور\n"
        "• 🔢 ترقيم الصفحات\n• ✂️ تقسيم\n• 🗑️ حذف صفحات\n"
        "• 📉 ضغط\n• 🔒 حماية\n• 🔓 إزالة الحماية\n\n"
        "اختر الأداة من القائمة 🚀"
    )
    await update.message.reply_text(welcome, parse_mode="Markdown", reply_markup=MAIN_MENU)
    if AdminSystem.is_admin(uid):
        await update.message.reply_text("👑 مرحباً أيها المشرف!", reply_markup=ADMIN_MENU)
    return SELECT_ACTION


async def choose_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    action_text = update.message.text
    UserStats.track_user(uid, update.effective_user.username, update.effective_user.first_name)

    if action_text == "📝 نص إلى PDF":
        return await handle_text_to_pdf(update, context)
    if action_text == "👑 لوحة التحكم":
        if not AdminSystem.is_admin(uid):
            await update.message.reply_text("❌ غير مصرح!", reply_markup=MAIN_MENU)
            return SELECT_ACTION
        await admin_panel(update, context)
        return SELECT_ACTION
    if action_text == "❌ إلغاء":
        return await cancel(update, context)
    if not await check_subscription(update, context):
        return SELECT_ACTION
    if is_user_busy(uid):
        await update.message.reply_text("⏳ لديك عملية جارية...", reply_markup=MAIN_MENU)
        return SELECT_ACTION

    session = user_sessions.setdefault(uid, Session())
    session.action = action_text
    session.last_active = time.time()
    prompts = {
        "📎 دمج PDF": "📤 أرسل الملفات للدمج",
        "🖼️ صور لـ PDF": "📤 أرسل الصور للتحويل إلى PDF",
        "📸 استخراج صور": "📤 أرسل ملف PDF لاستخراج الصور منه",
        "🔢 ترقيم الصفحات": "📤 أرسل ملف PDF لإضافة أرقام الصفحات",
        "✂️ تقسيم": "📤 أرسل ملف PDF ثم أدخل نطاق الصفحات",
        "🗑️ حذف صفحات": "📤 أرسل ملف PDF ثم أدخل الصفحات للحذف",
        "📉 ضغط": "📤 أرسل ملف PDF لضغطه",
        "🔒 حماية": "📤 أرسل ملف PDF ثم أدخل كلمة المرور",
        "🔓 إزالة الحماية": "📤 أرسل ملف PDF لإزالة الحماية",
    }
    if action_text not in prompts:
        await update.message.reply_text("❓ اختر أداة من القائمة.", reply_markup=MAIN_MENU)
        return SELECT_ACTION
    await update.message.reply_text(prompts[action_text], reply_markup=ACTION_MENU)
    return WAIT_FILE


async def handle_text_to_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not await check_subscription(update, context):
        return SELECT_ACTION
    session = user_sessions.setdefault(uid, Session())
    session.action = "📝 نص إلى PDF"
    session.last_active = time.time()
    session.expecting_name = True
    await update.message.reply_text(
        "📝 **تحويل النص إلى PDF**\n\n"
        "📌 الخطوة 1: أرسل عنوان المستند\n"
        "📌 الخطوة 2: أرسل النص\n\n📤 أرسل العنوان الآن:",
        reply_markup=CANCEL_BTN, parse_mode="Markdown"
    )
    return WAIT_NAME


async def receive_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not await check_subscription(update, context):
        return SELECT_ACTION
    session = user_sessions.setdefault(uid, Session())
    session.last_active = time.time()
    if len(session.files) >= Config.MAX_FILES_PER_SESSION:
        await update.message.reply_text(f"❌ الحد الأقصى {Config.MAX_FILES_PER_SESSION} ملفاً.")
        return WAIT_FILE
    photo = update.message.photo[-1]
    if (getattr(photo, "file_size", 0) or 0) > Config.MAX_FILE_SIZE:
        await update.message.reply_text(f"❌ الصورة أكبر من {format_size(Config.MAX_FILE_SIZE)}.")
        return WAIT_FILE
    filename = f"photo_{uid}_{os.urandom(4).hex()}.jpg"
    path = str(Path(Config.TEMP_DIR) / filename)
    try:
        if not ensure_temp_capacity(getattr(photo, "file_size", 0) or 0):
            await update.message.reply_text("⚠️ مساحة التخزين المؤقت ممتلئة مؤقتاً. حاول بعد قليل.")
            return WAIT_FILE
        await _get_downloaded_path(context, photo.file_id, path)
        session.files.append(path)
        await update.message.reply_text(
            f"✅ تم استلام الصورة!\n📌 العدد: {len(session.files)}/{Config.MAX_FILES_PER_SESSION}",
            reply_markup=ACTION_MENU,
        )
    except Exception as exc:
        safe_remove(path)
        logger.exception("photo receive failed: %s", exc)
        await update.message.reply_text("❌ تعذر تحميل الصورة.")
    return WAIT_FILE


async def receive_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    session = user_sessions.get(uid)
    if not session:
        return await start(update, context)
    if update.message.text == "❌ إلغاء":
        return await cancel(update, context)
    name = update.message.text.strip()
    if session.action == "📝 نص إلى PDF":
        if not name:
            await update.message.reply_text("❌ العنوان فارغ.", reply_markup=CANCEL_BTN)
            return WAIT_NAME
        session.text_title = name[:150]
        session.expecting_name = False
        await update.message.reply_text("📤 أرسل النص الآن.", reply_markup=ACTION_MENU)
        return WAIT_FILE
    session.custom_name = None if name.lower() == "تخطي" else ensure_extension(name[:120])
    session.expecting_name = False
    return await process_work(update, context, session)


async def receive_files(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not await check_subscription(update, context):
        return SELECT_ACTION
    session = user_sessions.get(uid)
    if not session:
        return await start(update, context)
    session.last_active = time.time()

    if update.message.text and session.action == "📝 نص إلى PDF":
        text = update.message.text.strip()
        if len(text) <= 3:
            await update.message.reply_text("❌ النص قصير جداً.")
            return WAIT_FILE
        try:
            async with JOB_SEMAPHORE:
                pdf_path = FileEngine.text_to_pdf(text, session.text_title or "نص")
            try:
                await _send_result(update, pdf_path, Path(pdf_path).name, "✅ تم تحويل النص إلى PDF بنجاح!")
            finally:
                safe_remove(pdf_path)
            return SELECT_ACTION
        except Exception as exc:
            logger.exception("text to pdf failed: %s", exc)
            await update.message.reply_text(f"❌ خطأ: {str(exc)[:200]}")
            return WAIT_FILE

    if update.message.text:
        text = update.message.text.strip()
        if text == "❌ إلغاء":
            return await cancel(update, context)
        if text == "➕ إضافة ملفات أخرى":
            await update.message.reply_text("📤 أرسل الملف التالي.", reply_markup=ACTION_MENU)
            return WAIT_FILE
        if text == "✅ إنهاء العملية":
            if not session.files:
                await update.message.reply_text("⚠️ لم ترسل أي ملفات!", reply_markup=ACTION_MENU)
                return WAIT_FILE
            data_actions = {"✂️ تقسيم": "📝 أدخل نطاق الصفحات:", "🗑️ حذف صفحات": "📝 أدخل الصفحات للحذف:", "🔒 حماية": "📝 أدخل كلمة المرور:"}
            if session.action in data_actions:
                session.expecting_data = True
                await update.message.reply_text(data_actions[session.action], reply_markup=CANCEL_BTN)
                return WAIT_DATA
            session.expecting_name = True
            await update.message.reply_text("📝 أرسل اسم الملف أو اكتب تخطي:", reply_markup=CANCEL_BTN)
            return WAIT_NAME
        if session.expecting_data:
            return await receive_data(update, context)

    document = update.message.document
    if not document:
        await update.message.reply_text("📤 أرسل ملفاً أو استخدم أزرار العملية.")
        return WAIT_FILE
    filename = document.file_name or "file"
    size = document.file_size or 0
    if size > Config.MAX_FILE_SIZE:
        await update.message.reply_text(f"❌ حجم الملف أكبر من الحد المسموح: {format_size(Config.MAX_FILE_SIZE)}")
        return WAIT_FILE
    if len(session.files) >= Config.MAX_FILES_PER_SESSION:
        await update.message.reply_text(f"❌ الحد الأقصى {Config.MAX_FILES_PER_SESSION} ملفاً.")
        return WAIT_FILE
    ext = get_file_extension(filename)
    if not ext or ext not in Config.SUPPORTED_EXTENSIONS:
        await update.message.reply_text("❌ صيغة الملف غير مدعومة.")
        return WAIT_FILE
    if not ensure_temp_capacity(size):
        await update.message.reply_text("⚠️ مساحة التخزين المؤقت ممتلئة مؤقتاً. حاول بعد قليل.")
        return WAIT_FILE
    path = str(Path(Config.TEMP_DIR) / f"f_{uid}_{len(session.files)}_{os.urandom(4).hex()}{ext}")
    try:
        await _get_downloaded_path(context, document.file_id, path)
        session.files.append(path)
        if session.action == "📉 ضغط":
            original_mb = size / (1024 * 1024)

            await update.message.reply_text(
                "✅ تم استلام الملف بنجاح!\n\n"
                f"📄 الملف: {Path(filename).name}\n"
                f"📊 حجم الملف الأصلي: {original_mb:.2f} MB\n\n"
                "اختر مستوى الجودة المطلوب من الخيارات أدناه:",
                reply_markup=compression_levels_keyboard(),
            )
        else:
            await update.message.reply_text(
                f"✅ تم الاستلام!\n"
                f"📁 {Path(filename).name}\n"
                f"📌 {len(session.files)}/{Config.MAX_FILES_PER_SESSION}",
                reply_markup=ACTION_MENU,
            )
    except Exception as exc:
        safe_remove(path)
        logger.exception("document receive failed: %s", exc)
        await update.message.reply_text("❌ تعذر تحميل الملف. حاول مرة أخرى.")
    return WAIT_FILE


async def receive_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    session = user_sessions.get(uid)
    if not session:
        return await start(update, context)
    if update.message.text == "❌ إلغاء":
        return await cancel(update, context)
    session.val1 = update.message.text.strip()
    session.expecting_data = False
    session.expecting_name = True
    await update.message.reply_text("📝 أرسل اسم الملف أو اكتب تخطي:", reply_markup=CANCEL_BTN)
    return WAIT_NAME


async def _send_result(update: Update, path: str, filename: str, caption: str):
    if not path or not os.path.isfile(path):
        raise FileNotFoundError("ملف الناتج غير موجود")

    message = update.effective_message

    if message is None:
        raise RuntimeError("لا توجد رسالة صالحة لإرسال النتيجة")

    size = os.path.getsize(path)

    if size > Config.MAX_FILE_SIZE:
        raise ValueError(
            f"الناتج أكبر من حد {format_size(Config.MAX_FILE_SIZE)}"
        )

    with open(path, "rb") as fh:
        await message.reply_document(
            document=fh,
            filename=filename,
            caption=caption,
            reply_markup=MAIN_MENU,
        )


async def process_work(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session):
    uid = update.effective_user.id
    message = update.effective_message
    if not session.files:
        await message.reply_text("❌ لا توجد ملفات.")
        return SELECT_ACTION
    set_user_busy(uid, True)
    try:
        action = session.action
        result_path = None
        extra_info = ""
        result_data = None
        result_filename = None
        default_names = {
            "📎 دمج PDF": "ملفات_مدمجة.pdf", "🖼️ صور لـ PDF": "صور_محولة.pdf", "📸 استخراج صور": "صور_مستخرجة.zip",
            "🔢 ترقيم الصفحات": "ملف_مرقم.pdf", "📉 ضغط": "ملف_مضغوط.pdf", "🔒 حماية": "ملف_محمي.pdf",
            "✂️ تقسيم": "ملف_مقسم.pdf", "🗑️ حذف صفحات": "ملف_معدل.pdf", "🔓 إزالة الحماية": "ملف_غير_محمي.pdf",
        }
        final_name = session.custom_name or default_names.get(action, "ملف.pdf")
        await message.reply_text("⏳ جاري المعالجة...")
        async with JOB_SEMAPHORE:
            if action == "📎 دمج PDF":
                result_path = FileEngine.merge_documents(session.files)
            elif action == "🖼️ صور لـ PDF":
                result_path = FileEngine.images_to_pdf(session.files)
            elif action == "📸 استخراج صور":
                if len(session.files) != 1: raise ValueError("يجب إرسال ملف واحد")
                result_path, result_filename = FileEngine.extract_images_from_pdf(session.files[0])
            elif action == "🔢 ترقيم الصفحات":
                if len(session.files) != 1: raise ValueError("يجب إرسال ملف واحد")
                result_path = FileEngine.add_page_numbers(session.files[0])
            elif action == "📉 ضغط":
                if len(session.files) != 1: raise ValueError("يجب إرسال ملف واحد")
                result_path, before, after = FileEngine.compress_pdf(
                    session.files[0],
                    session.compression_level or "ebook",
                )
                if before != after:
                    reduction = (1 - after / before) * 100 if before else 0
                    saved = before - after

                    level_names = {
                        "screen": "📱 Screen — 72 DPI",
                        "ebook": "📖 E-book — 150 DPI",
                        "printer": "🖨️ Printer — 300 DPI",
                    }

                    level_name = level_names.get(
                        session.compression_level or "ebook",
                        "📖 E-book — 150 DPI",
                    )

                    extra_info = (
                        f"\\n\\n"
                        f"📦 الحجم الأصلي: {format_size(before)}\\n"
                        f"📉 الحجم الجديد: {format_size(after)}\\n"
                        f"💾 التوفير: {format_size(saved)}\\n"
                        f"📊 نسبة التخفيض: {reduction:.1f}%\\n"
                        f"🎯 المستوى: {level_name}"
                    )
                else:
                    extra_info = (
                        "\\n\\n"
                        "⚠️ لم ينخفض حجم الملف بشكل أكبر."
                    )
            elif action == "🔒 حماية":
                if len(session.files) != 1: raise ValueError("يجب إرسال ملف واحد")
                password = session.val1 or "1234"
                result_path = FileEngine.encrypt_pdf(session.files[0], password)
                extra_info = f"\n🔑 كلمة المرور: `{password}`"
            elif action == "✂️ تقسيم":
                if len(session.files) != 1: raise ValueError("يجب إرسال ملف واحد")
                result_path = FileEngine.split_pdf(session.files[0], session.val1 or "1")
            elif action == "🗑️ حذف صفحات":
                if len(session.files) != 1: raise ValueError("يجب إرسال ملف واحد")
                reader = PdfReader(session.files[0])
                pages = validate_page_range(session.val1 or "1", len(reader.pages))
                result_path = FileEngine.delete_pages(session.files[0], pages)
            elif action == "🔓 إزالة الحماية":
                if len(session.files) != 1: raise ValueError("يجب إرسال ملف واحد")
                result_path = FileEngine.remove_password(session.files[0], session.val1 or "")
                extra_info = "\n🔓 تم إزالة الحماية"
            else:
                raise ValueError("عملية غير معروفة")

        if result_path:
            try:
                await _send_result(update, result_path, result_filename or final_name, f"✅ تمت العملية{extra_info}")
            finally:
                if result_path not in session.files:
                    safe_remove(result_path)
        elif result_data:
            if len(result_data) > Config.MAX_FILE_SIZE:
                raise ValueError("الناتج أكبر من الحد المسموح")
            await message.reply_document(document=result_data, filename=result_filename or final_name, caption=f"✅ تمت العملية{extra_info}", reply_markup=MAIN_MENU)
        return SELECT_ACTION
    except Exception as exc:
        logger.exception("processing failed for %s: %s", uid, exc)
        await message.reply_text(f"❌ {str(exc)[:300]}", reply_markup=MAIN_MENU)
        return SELECT_ACTION
    finally:
        set_user_busy(uid, False)
        _cleanup_session(session)
        user_sessions.pop(uid, None)


async def compression_callback_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if not query or not update.effective_user:
        return SELECT_ACTION

    await query.answer()

    uid = update.effective_user.id
    session = user_sessions.get(uid)

    if not session or not session.files:
        await query.edit_message_text(
            "❌ انتهت جلسة الملف. أرسل الملف من جديد."
        )
        return SELECT_ACTION

    data = query.data or ""

    levels = {
        "compress_screen": "screen",
        "compress_ebook": "ebook",
        "compress_printer": "printer",
    }

    if data not in levels:
        return WAIT_FILE

    session.compression_level = levels[data]
    session.last_active = time.time()

    names = {
        "screen": "📱 Screen — 72 DPI",
        "ebook": "📖 E-book — 150 DPI",
        "printer": "🖨️ Printer — 300 DPI",
    }

    await query.edit_message_text(
        f"⏳ جاري ضغط الملف...\\n\\n"
        f"🎯 المستوى: {names[session.compression_level]}"
    )

    return await process_work(update, context, session)


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    session = user_sessions.pop(uid, None)
    if session:
        _cleanup_session(session)
    await update.message.reply_text("✅ تم الإلغاء", reply_markup=MAIN_MENU)
    return SELECT_ACTION


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not AdminSystem.is_admin(uid):
        await update.message.reply_text("❌ هذا الأمر مخصص للمشرفين فقط!", reply_markup=MAIN_MENU)
        return SELECT_ACTION
    await admin_panel(update, context)
    return SELECT_ACTION


async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.exception("Unhandled Telegram error: %s", context.error)


async def cleanup_task(context: ContextTypes.DEFAULT_TYPE):
    # لا نحذف ملفات جلسة مستخدم ما زالت فعالة حتى لو تجاوزت مدة الملف.
    protected = [path for session in user_sessions.values() for path in session.files]
    clean_old_files(protected_paths=protected)
    now = time.time()
    for uid, session in list(user_sessions.items()):
        if now - session.last_active > Config.MAX_SESSION_TIME:
            logger.info("🧹 Expiring session %s", uid)
            _cleanup_session(session)
            user_sessions.pop(uid, None)
    # Emergency pressure relief: if temp exceeds the configured cap, remove oldest files first.
    limit = Config.MAX_TEMP_DIR_MB * 1024 * 1024
    if temp_dir_size() > limit:
        files = []
        for p in Path(Config.TEMP_DIR).rglob('*'):
            if p.is_file():
                try: files.append((p.stat().st_mtime, p))
                except OSError: pass
        for _, p in sorted(files):
            if str(p.resolve()) in {str(Path(x).resolve()) for x in protected}:
                continue
            if temp_dir_size() <= limit * 0.80:
                break
            safe_remove(str(p))
    gc.collect()


async def post_init(application):
    await start_user_api()


async def post_shutdown(application):
    await stop_user_api()


def main():
    if not Config.BOT_TOKEN:
        raise SystemExit("❌ BOT_TOKEN غير موجود في .env")
    Config.FORCED_CHANNELS = AdminSystem.load_channels()
    builder = ApplicationBuilder().token(Config.BOT_TOKEN)
    if Config.LOCAL_BOT_API:
        base = f"http://{Config.LOCAL_BOT_API_HOST}:{Config.LOCAL_BOT_API_PORT}/bot"
        file_base = f"http://{Config.LOCAL_BOT_API_HOST}:{Config.LOCAL_BOT_API_PORT}/file/bot"
        builder = builder.base_url(base).base_file_url(file_base).local_mode(True)
    builder = (
        builder.concurrent_updates(False)
        .connection_pool_size(4)
        .pool_timeout(60)
        .connect_timeout(20)
        .read_timeout(60)
        .write_timeout(60)
        .media_write_timeout(300)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
    )
    app = builder.build()
    add_channel_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_add_channel_entry, pattern=r"^admin_add_channel$")],
        states={ADD_CHANNEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_channel_handler)]},
        fallbacks=[CommandHandler("cancel", cancel)], per_user=True,
    )
    app.add_handler(add_channel_conv)

    broadcast_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                admin_callback_handler,
                pattern=r"^admin_broadcast$"
            )
        ],
        states={
            BROADCAST: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    broadcast_handler
                )
            ]
        },
        fallbacks=[
            CommandHandler("cancel", cancel)
        ],
        per_user=True,
    )

    app.add_handler(broadcast_conv)

    app.add_handler(
        CallbackQueryHandler(
            admin_callback_handler,
            pattern=r"^(admin_|remove_)"
        )
    )
    app.add_handler(CallbackQueryHandler(check_subscription_callback, pattern=r"^check_subscription$"))
    app.add_handler(CommandHandler("admin", admin_command))
    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start), CommandHandler("cancel", cancel)],
        states={
            SELECT_ACTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_action)],
            WAIT_FILE: [
                CallbackQueryHandler(
                    compression_callback_handler,
                    pattern=r"^compress_(screen|ebook|printer)$",
                ),
                MessageHandler(
                    filters.PHOTO & ~filters.COMMAND,
                    receive_photo,
                ),
                MessageHandler(
                    filters.Document.ALL & ~filters.COMMAND,
                    receive_files,
                ),
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    receive_files,
                ),
            ],
            WAIT_DATA: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_data)],
            WAIT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_name)],
        },
        fallbacks=[CommandHandler("start", start), CommandHandler("cancel", cancel)], per_user=True,
    )
    app.add_handler(conv)
    app.add_error_handler(global_error_handler)
    app.job_queue.run_repeating(cleanup_task, interval=Config.CLEANUP_INTERVAL, first=15)
    logger.info("🚀 PDF Bot started | local_api=%s | max_file=%s | concurrency=%s", Config.LOCAL_BOT_API, format_size(Config.MAX_FILE_SIZE), Config.MAX_CONCURRENT_JOBS)
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
