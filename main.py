import os
import asyncio
from dotenv import load_dotenv
from telegram import Bot
import os
import json

# создаем файлы из env (для Render)
if os.getenv("GOOGLE_CREDENTIALS_JSON"):
    with open("credentials.json", "w", encoding="utf-8") as f:
        f.write(os.getenv("GOOGLE_CREDENTIALS_JSON"))

if os.getenv("GOOGLE_TOKEN_JSON"):
    with open("token.json", "w", encoding="utf-8") as f:
        f.write(os.getenv("GOOGLE_TOKEN_JSON"))

from gmail_client import (
    get_gmail_service,
    list_unread,
    get_message,
    mark_as_read,
    format_for_telegram
)
from tg_client import send_long


async def run():
    load_dotenv()

    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id_raw = os.getenv("TARGET_CHAT_ID", "").strip()
    poll_seconds = int(os.getenv("POLL_SECONDS", "60"))
    max_emails = int(os.getenv("MAX_EMAILS_PER_POLL", "10"))

    if not token:
        raise SystemExit("❌ TELEGRAM_BOT_TOKEN пустой в .env")
    if not chat_id_raw:
        raise SystemExit("❌ TARGET_CHAT_ID пустой в .env (см. шаг ниже как узнать)")

    chat_id = int(chat_id_raw)
    bot = Bot(token=token)

    gmail = get_gmail_service()

    await bot.send_message(chat_id=chat_id, text="✅ Gmail2TG запущен.")

    while True:
        try:
            unread = list_unread(gmail, max_results=max_emails)

            # обрабатываем от старых к новым, чтобы читать логично
            for item in reversed(unread):
                msg_id = item["id"]
                msg = get_message(gmail, msg_id)
                text = format_for_telegram(msg)

                await send_long(bot, chat_id, text)
                mark_as_read(gmail, msg_id)

        except Exception as e:
            # чтобы не падало — просто лог + уведомление (по желанию)
            print("ERROR:", e)

        await asyncio.sleep(poll_seconds)


if __name__ == "__main__":
    asyncio.run(run())