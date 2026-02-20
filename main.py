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


def _write_if_env(path: str, env_name: str) -> None:
    """
    GitHub Actions / Railway: если передали JSON в env — создаём файл.
    """
    val = os.getenv(env_name)
    if not val:
        return
    if os.path.exists(path):
        return
    with open(path, "w", encoding="utf-8") as f:
        f.write(val)


def _get_int(name: str, default: int) -> int:
    v = os.getenv(name)
    if not v:
        return default
    try:
        return int(v)
    except ValueError:
        return default


def _get_float(name: str, default: float) -> float:
    v = os.getenv(name)
    if not v:
        return default
    try:
        return float(v)
    except ValueError:
        return default


async def process_once(bot: Bot, chat_id: int, gmail, max_emails: int, per_email_delay: float) -> int:
    """
    Одна проверка: взять unread, отправить в TG, пометить прочитанным.
    Возвращает сколько писем отправили.
    """
    sent = 0
    unread = list_unread(gmail, max_results=max_emails)

    # старые -> новые
    for item in reversed(unread):
        msg_id = item["id"]
        msg = get_message(gmail, msg_id)
        text = format_for_telegram(msg)

        await send_long(bot, chat_id, text)
        # антифлуд между письмами (важно!)
        await asyncio.sleep(per_email_delay)

        mark_as_read(gmail, msg_id)
        sent += 1

    return sent


async def main():
    # локально подтянет .env, в Actions может не быть — норм
    load_dotenv()

    # Actions/Railway: создаём файлы из Secrets/Variables
    _write_if_env("credentials.json", "GOOGLE_CREDENTIALS_JSON")
    _write_if_env("token.json", "GOOGLE_TOKEN_JSON")

    tg_token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    chat_id_raw = (os.getenv("TARGET_CHAT_ID") or "").strip()

    run_mode = (os.getenv("RUN_MODE") or "once").strip().lower()  # once / loop

    max_emails = _get_int("MAX_EMAILS_PER_POLL", 2)               # по дефолту мало, чтобы не флудить
    poll_seconds = _get_int("POLL_SECONDS", 60)
    per_email_delay = _get_float("PER_EMAIL_DELAY", 2.0)          # антифлуд между письмами

    if not tg_token:
        raise SystemExit("❌ TELEGRAM_BOT_TOKEN пустой (добавь в GitHub Secrets)")
    if not chat_id_raw:
        raise SystemExit("❌ TARGET_CHAT_ID пустой (добавь в GitHub Secrets)")

    try:
        chat_id = int(chat_id_raw)
    except ValueError:
        raise SystemExit("❌ TARGET_CHAT_ID должен быть числом")

    bot = Bot(token=tg_token)
    gmail = get_gmail_service()

    # Пинг (один раз, чтобы понять что всё живое)
    try:
        await bot.send_message(chat_id=chat_id, text="✅ Gmail2TG: старт.")
        await asyncio.sleep(1.0)  # антифлуд
    except Exception as e:
        print("TG START MSG ERROR:", e)

    if run_mode == "once":
        sent = await process_once(bot, chat_id, gmail, max_emails, per_email_delay)
        print(f"Done. Sent {sent} emails.")
        return

    # loop режим (если когда-то будешь держать 24/7 на сервере)
    while True:
        try:
            sent = await process_once(bot, chat_id, gmail, max_emails, per_email_delay)
            print(f"Loop tick. Sent {sent} emails.")
        except Exception as e:
            print("LOOP ERROR:", e)

        await asyncio.sleep(max(5, poll_seconds))


if __name__ == "__main__":
    asyncio.run(main())