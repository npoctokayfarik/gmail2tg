import os
import asyncio
from dotenv import load_dotenv
from telegram import Bot
from telegram.error import RetryAfter, TimedOut, NetworkError

from gmail_client import (
    get_gmail_service,
    list_unread,
    get_message,
    mark_as_read,
)


def _write_if_env(path: str, env_name: str) -> None:
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


def _header(payload, name: str) -> str:
    for h in payload.get("headers", []) or []:
        if (h.get("name") or "").lower() == name.lower():
            return h.get("value", "")
    return ""


def build_digest(messages) -> str:
    if not messages:
        return ""

    lines = [f"📩 Новые письма: {len(messages)}\n"]

    for i, msg in enumerate(messages, 1):
        payload = msg.get("payload", {}) or {}
        from_ = _header(payload, "From")
        subject = _header(payload, "Subject")

        if len(subject) > 80:
            subject = subject[:80] + "…"
        if len(from_) > 60:
            from_ = from_[:60] + "…"

        link = f"https://mail.google.com/mail/u/0/#inbox/{msg.get('id')}"
        lines.append(f"{i}. {subject}\n   {from_}\n   {link}\n")

    return "\n".join(lines)


async def send_once_no_wait(bot: Bot, chat_id: int, text: str) -> bool:
    """
    1 попытка отправить.
    Если flood (RetryAfter) — НЕ ждём 900 секунд, а выходим.
    Следующий запуск Actions попробует снова.
    """
    try:
        await bot.send_message(chat_id=chat_id, text=text)
        return True
    except RetryAfter as e:
        wait_s = int(getattr(e, "retry_after", 5))
        print(f"TG FLOOD: retry after {wait_s}s. Exit now.")
        return False
    except (TimedOut, NetworkError) as e:
        print(f"TG NETWORK/TIMEOUT: {e}. Exit now.")
        return False


async def main():
    load_dotenv()

    # GitHub Actions: файлы создаются из secrets
    _write_if_env("credentials.json", "GOOGLE_CREDENTIALS_JSON")
    _write_if_env("token.json", "GOOGLE_TOKEN_JSON")

    tg_token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    chat_id_raw = (os.getenv("TARGET_CHAT_ID") or "").strip()
    max_emails = _get_int("MAX_EMAILS_PER_POLL", 5)

    if not tg_token:
        raise SystemExit("❌ TELEGRAM_BOT_TOKEN пустой")
    if not chat_id_raw:
        raise SystemExit("❌ TARGET_CHAT_ID пустой")

    try:
        chat_id = int(chat_id_raw)
    except ValueError:
        raise SystemExit("❌ TARGET_CHAT_ID должен быть числом")

    bot = Bot(token=tg_token)
    gmail = get_gmail_service()

    unread = list_unread(gmail, max_results=max_emails)
    if not unread:
        print("No unread emails")
        return

    messages = [get_message(gmail, item["id"]) for item in unread]
    text = build_digest(messages)

    ok = await send_once_no_wait(bot, chat_id, text)
    if not ok:
        # не помечаем письма прочитанными — отправим позже
        return

    for item in unread:
        mark_as_read(gmail, item["id"])

    print(f"Done. Sent {len(messages)} emails.")


if __name__ == "__main__":
    asyncio.run(main())
