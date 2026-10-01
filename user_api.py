"""اختياري: Telegram User API عبر Telethon.
لا يُشغّل أي شيء إذا كان USER_API_ENABLED=false أو لم توجد جلسة.
"""
from pathlib import Path
from typing import Optional
from config import Config
from utils import logger

try:
    from telethon import TelegramClient
except ImportError:
    TelegramClient = None

_client = None

def configured() -> bool:
    return bool(Config.USER_API_ENABLED and Config.TELEGRAM_API_ID and Config.TELEGRAM_API_HASH and TelegramClient)

async def start_user_api() -> Optional[object]:
    global _client
    if not configured():
        return None
    Path(Config.USER_SESSION_DIR).mkdir(parents=True, exist_ok=True)
    _client = TelegramClient(Config.USER_SESSION_PATH, Config.TELEGRAM_API_ID, Config.TELEGRAM_API_HASH)
    await _client.connect()
    if not await _client.is_user_authorized():
        logger.warning("Telegram User API غير مسجل الدخول. شغّل login_user.py مرة واحدة.")
        await _client.disconnect()
        _client = None
        return None
    logger.info("👤 Telegram User API session connected")
    return _client

async def stop_user_api() -> None:
    global _client
    if _client:
        await _client.disconnect()
        _client = None

def get_user_client():
    return _client
