import os
import re
import time
import logging
import shutil
from logging.handlers import RotatingFileHandler
from pathlib import Path
from config import Config

Config.ensure_dirs()
logger = logging.getLogger("pdf_bot")
logger.setLevel(logging.INFO)
if not logger.handlers:
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    handler = RotatingFileHandler(
        Path(Config.LOG_DIR) / "bot.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=2,
        encoding="utf-8",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    logger.addHandler(console)

active_users = set()

def is_user_busy(user_id: int) -> bool:
    return user_id in active_users

def set_user_busy(user_id: int, busy: bool = True):
    if busy:
        active_users.add(user_id)
    else:
        active_users.discard(user_id)

def _iter_temp_files():
    root = Path(Config.TEMP_DIR)
    if not root.exists():
        return []
    return [p for p in root.rglob('*') if p.is_file()]

def temp_dir_size() -> int:
    total = 0
    for p in _iter_temp_files():
        try:
            total += p.stat().st_size
        except OSError:
            pass
    return total

def clean_old_files(max_age: int | None = None, protected_paths=None):
    max_age = Config.MAX_FILE_AGE if max_age is None else max_age
    protected = {str(Path(x).resolve()) for x in (protected_paths or []) if x}
    now = time.time()
    deleted = 0
    deleted_bytes = 0
    root = Path(Config.TEMP_DIR)
    if not root.exists():
        return {"deleted": 0, "bytes": 0}
    for p in list(root.rglob('*')):
        try:
            if p.is_file() and str(p.resolve()) not in protected and now - p.stat().st_mtime > max_age:
                size = p.stat().st_size
                p.unlink(missing_ok=True)
                deleted += 1
                deleted_bytes += size
        except OSError:
            pass
    for p in sorted(root.rglob('*'), reverse=True):
        try:
            if p.is_dir() and not any(p.iterdir()):
                p.rmdir()
        except OSError:
            pass
    if deleted:
        logger.info("🧹 cleanup: deleted=%s size=%s", deleted, format_size(deleted_bytes))
    return {"deleted": deleted, "bytes": deleted_bytes}

def safe_remove(file_path: str | None) -> bool:
    if not file_path:
        return False
    try:
        p = Path(file_path)
        if p.is_file():
            p.unlink()
            return True
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)
            return True
    except OSError:
        pass
    return False

def format_size(size: int) -> str:
    if size < 1024:
        return f"{size} ب"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} كيلوبايت"
    if size < 1024 * 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} ميجابايت"
    return f"{size / (1024 * 1024 * 1024):.2f} جيجابايت"

def sanitize_filename(filename: str) -> str:
    if not filename:
        return "ملف"
    filename = re.sub(r'[\/*?:"<>|]', "", filename)
    filename = re.sub(r'\s+', " ", filename).strip()
    return filename or "ملف"

def ensure_extension(filename: str) -> str:
    filename = sanitize_filename(filename)
    if not filename:
        return "ملف.pdf"
    if Path(filename).suffix.lower() in Config.SUPPORTED_EXTENSIONS:
        return filename
    return filename + ".pdf"

def get_file_extension(filename: str) -> str:
    return Path(filename).suffix.lower()

def is_supported_file(filename: str) -> bool:
    return get_file_extension(filename) in Config.SUPPORTED_EXTENSIONS

def get_file_type_arabic(filename: str) -> str:
    ext = get_file_extension(filename)
    types = {
        '.pdf': '📄 PDF', '.doc': '📝 Word', '.docx': '📝 Word',
        '.xls': '📊 Excel', '.xlsx': '📊 Excel', '.ppt': '📽️ PowerPoint',
        '.pptx': '📽️ PowerPoint', '.txt': '📃 نص', '.jpg': '🖼️ صورة',
        '.jpeg': '🖼️ صورة', '.png': '🖼️ صورة', '.webp': '🖼️ صورة',
        '.zip': '📦 ZIP', '.rar': '📦 RAR', '.7z': '📦 7Z',
    }
    return types.get(ext, '📁 ملف')

def validate_page_range(range_str: str, total: int) -> list[int]:
    if not range_str:
        raise ValueError("أدخل نطاق الصفحات")
    pages = set()
    for part in range_str.replace(" ", "").split(","):
        if not part:
            continue
        try:
            if "-" in part:
                s, e = map(int, part.split("-", 1))
                if not (1 <= s <= e <= total):
                    raise ValueError
                pages.update(range(s, e + 1))
            else:
                p = int(part)
                if not (1 <= p <= total):
                    raise ValueError
                pages.add(p)
        except ValueError:
            raise ValueError(f"نطاق أو صفحة غير صالحة: {part}")
    if not pages:
        raise ValueError("لم يتم تحديد صفحات")
    return sorted(pages)

def ensure_temp_capacity(extra_bytes: int = 0) -> bool:
    limit = Config.MAX_TEMP_DIR_MB * 1024 * 1024
    return temp_dir_size() + max(0, extra_bytes) <= limit
