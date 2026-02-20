import os
import asyncio
from dotenv import load_dotenv
from telegram import Bot

from gmail_client import (
    get_gmail_service,
    list_unread,
    get_message,
    mark_as_read,
    format_for_telegram,
)
from tg_client import send_long


def write_file_from_env(path: str, env_name: str) -> None:
    """
    Для deploy (Railway/Render): сохраняем JSON из переменных окружения в файл,
    чтобы gmail_client.py работал как обычно.
    """
    content = os.getenv(env_name)
    if not content:
        return

    # Если файл уже есть — не трогаем (чтобы не ломать локальный режим)
    if os.path.exists(path):
        return

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def get_int_env(name: str, default: int) -> int:
    v = os.getenv(name)
    if not v:
        return default
    try:
        return int(v)
    except ValueError:
        return default


async def main():
    # Локально подтянет .env, на Railway просто проигнорит если файла нет
    load_dotenv()

    # 1) Deploy helper: создаём файлы из env (если передали в Railway Variables)
    write_file_from_env("credentials.json", "GOOGLE_CREDENTIALS_JSON")
    write_file_from_env("token.json", "GOOGLE_TOKEN_JSON")

    # 2) Настройки
    tg_token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    chat_id_raw = (os.getenv("TARGET_CHAT_ID") or "").strip()

    poll_seconds = get_int_env("POLL_SECONDS", 60)
    max_emails = get_int_env("MAX_EMAILS_PER_POLL", 10)

    if not tg_token:
        raise SystemExit("❌ TELEGRAM_BOT_TOKEN пустой (добавь в .env или Railway Variables)")

    if not chat_id_raw:
        raise SystemExit("❌ TARGET_CHAT_ID пустой (добавь в .env или Railway Variables)")

    try:
        chat_id = int(chat_id_raw)
    except ValueError:
        raise SystemExit("❌ TARGET_CHAT_ID должен быть числом (например 123456789)")

    # 3) Клиенты
    bot = Bot(token=tg_token)
    gmail = get_gmail_service()

    # 4) Стартовый пинг
    try:
        await bot.send_message(chat_id=chat_id, text="✅ Gmail2TG запущен.")
    except Exception as e:
        print("TG START MSG ERROR:", e)

    # 5) Основной цикл
    while True:
        try:
            unread = list_unread(gmail, max_results=max_emails)

            # Чтобы шло “от старых к новым”
            for item in reversed(unread):
                msg_id = item["id"]
                msg = get_message(gmail, msg_id)
                text = format_for_telegram(msg)

                await send_long(bot, chat_id, text)
                mark_as_read(gmail, msg_id)

        except Exception as e:
            # Не падаем — просто логируем
            print("LOOP ERROR:", e)

        await asyncio.sleep(poll_seconds)


if __name__ == "__main__":
    asyncio.run(main())