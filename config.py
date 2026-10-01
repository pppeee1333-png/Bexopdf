import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


def _csv_ints(value: str):
    return [int(x.strip()) for x in value.split(",") if x.strip()]


class Config:
    BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
    ADMINS = _csv_ints(os.getenv("ADMINS", ""))

    # القناة الثابتة + القنوات الإضافية من لوحة الإدارة
    FORCED_CHANNEL = os.getenv("FORCED_CHANNEL", "bexo50").lstrip("@")
    FORCED_CHANNELS = []

    # حد التطبيق: 500 MiB. Local Bot API نفسه يسمح حتى 2000 MB،
    # لكن البوت يرفض أي ملف أكبر من هذا الحد قبل المعالجة.
    MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE_MB", "500")) * 1024 * 1024

    BASE_DIR = Path(__file__).resolve().parent
    TEMP_DIR = str(BASE_DIR / "temp")
    LOG_DIR = str(BASE_DIR / "logs")
    DATA_DIR = str(BASE_DIR / "data")
    USER_SESSION_DIR = str(BASE_DIR / "sessions")

    # تنظيف مستمر
    MAX_SESSION_TIME = int(os.getenv("MAX_SESSION_TIME", "600"))
    CLEANUP_INTERVAL = int(os.getenv("CLEANUP_INTERVAL", "300"))
    MAX_FILE_AGE = int(os.getenv("MAX_FILE_AGE", "900"))
    MAX_FILES_PER_SESSION = int(os.getenv("MAX_FILES_PER_SESSION", "50"))

    # تقليل استهلاك الـ VPS
    MAX_CONCURRENT_JOBS = int(os.getenv("MAX_CONCURRENT_JOBS", "1"))
    MAX_TEMP_DIR_MB = int(os.getenv("MAX_TEMP_DIR_MB", "1200"))

    # Local Bot API
    LOCAL_BOT_API = os.getenv("LOCAL_BOT_API", "true").lower() in {"1", "true", "yes", "on"}
    LOCAL_BOT_API_HOST = os.getenv("LOCAL_BOT_API_HOST", "127.0.0.1")
    LOCAL_BOT_API_PORT = int(os.getenv("LOCAL_BOT_API_PORT", "8081"))

    # Telegram User API (Telethon) - اختياري ولا يمنع البوت من العمل إن لم يتم تسجيل الحساب.
    USER_API_ENABLED = os.getenv("USER_API_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
    TELEGRAM_API_ID = int(os.getenv("TELEGRAM_API_ID", "0") or 0)
    TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH", "").strip()
    USER_SESSION_NAME = os.getenv("USER_SESSION_NAME", "pdf_user")
    USER_SESSION_PATH = str(Path(USER_SESSION_DIR) / USER_SESSION_NAME)

    SUPPORTED_EXTENSIONS = {
        '.pdf', '.doc', '.docx', '.docm',
        '.xls', '.xlsx', '.xlsm', '.xlsb', '.csv',
        '.ppt', '.pptx', '.pptm', '.ppsx', '.pps',
        '.txt', '.rtf', '.md', '.markdown',
        '.odt', '.ods', '.odp',
        '.html', '.htm', '.xml', '.json',
        '.epub', '.mobi', '.fb2', '.tex',
        '.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tiff', '.gif',
        '.zip', '.rar', '.7z', '.gz', '.tar', '.tgz', '.bz2', '.xz',
    }

    @classmethod
    def ensure_dirs(cls):
        for directory in (cls.TEMP_DIR, cls.LOG_DIR, cls.DATA_DIR, cls.USER_SESSION_DIR):
            Path(directory).mkdir(parents=True, exist_ok=True)
