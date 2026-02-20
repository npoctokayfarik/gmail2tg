import os
import json
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

STATE_FILE = "state.json"


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


def load_state() -> dict:
    if not os.path.exists(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(state: dict) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


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


async def send_safe(bot: Bot, chat_id: int, text: str) -> None:
    while True:
        try:
            await bot.send_message(chat_id=chat_id, text=text)
            return
        except RetryAfter as e:
            wait_s = int(getattr(e, "retry_after", 5)) + 1
            await asyncio.sleep(wait_s)
        except (TimedOut, NetworkError):
            await asyncio.sleep(3)


async def poll_loop():
    load_dotenv()

    # Для Render будем хранить эти файлы на диске (или задавать через env)
    _write_if_env("credentials.json", "GOOGLE_CREDENTIALS_JSON")
    _write_if_env("token.json", "GOOGLE_TOKEN_JSON")

    tg_token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    chat_id_raw = (os.getenv("TARGET_CHAT_ID") or "").strip()

    poll_seconds = _get_int("POLL_SECONDS", 30)
    max_emails = _get_int("MAX_EMAILS_PER_POLL", 3)

    if not tg_token:
        raise SystemExit("❌ TELEGRAM_BOT_TOKEN пустой")
    if not chat_id_raw:
        raise SystemExit("❌ TARGET_CHAT_ID пустой")

    chat_id = int(chat_id_raw)

    bot = Bot(token=tg_token)
    gmail = get_gmail_service()
    state = load_state()

    await send_safe(bot, chat_id, "✅ Gmail2TG 24/7: запущен.")

    while True:
        try:
            unread = list_unread(gmail, max_results=max_emails)

            if unread:
                messages = [get_message(gmail, item["id"]) for item in unread]
                text = build_digest(messages)

                # отправляем 1 сообщением
                await send_safe(bot, chat_id, text)

                # отмечаем прочитанными
                for item in unread:
                    mark_as_read(gmail, item["id"])

            # сохраняем state (на будущее расширения)
            save_state(state)

        except Exception as e:
            # не падаем, просто лог
            print("LOOP ERROR:", e)

        await asyncio.sleep(max(10, poll_seconds))


if __name__ == "__main__":
    asyncio.run(poll_loop())
