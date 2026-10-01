import asyncio
from getpass import getpass
from pathlib import Path
from config import Config

async def main():
    if not Config.TELEGRAM_API_ID or not Config.TELEGRAM_API_HASH:
        raise SystemExit("ضع TELEGRAM_API_ID و TELEGRAM_API_HASH في .env أولاً")
    from telethon import TelegramClient
    Path(Config.USER_SESSION_DIR).mkdir(parents=True, exist_ok=True)
    phone = input("رقم Telegram مع رمز الدولة: ").strip()
    client = TelegramClient(Config.USER_SESSION_PATH, Config.TELEGRAM_API_ID, Config.TELEGRAM_API_HASH)
    await client.start(phone=phone, password=lambda: getpass("2FA password (إذا موجود): "))
    me = await client.get_me()
    print(f"تم تسجيل الدخول بنجاح: {getattr(me, 'first_name', '')} (@{getattr(me, 'username', '') or 'بدون username'})")
    await client.disconnect()

if __name__ == '__main__':
    asyncio.run(main())
