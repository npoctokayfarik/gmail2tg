import os
import asyncio
import threading
from flask import Flask
from dotenv import load_dotenv
from telegram import Bot
from telegram.error import RetryAfter

from gmail_client import get_gmail_service, list_unread, get_message, mark_as_read

app = Flask(__name__)


def get_int(name, default):
    try:
        return int(os.getenv(name, default))
    except:
        return default


async def send_safe(bot, chat_id, text):
    while True:
        try:
            await bot.send_message(chat_id=chat_id, text=text)
            return
        except RetryAfter as e:
            await asyncio.sleep(e.retry_after + 1)
        except Exception:
            await asyncio.sleep(3)


def build_text(messages):
    text = f"📩 Новые письма: {len(messages)}\n\n"

    for i, msg in enumerate(messages, 1):
        payload = msg.get("payload", {})
        headers = payload.get("headers", [])

        subject = next((h["value"] for h in headers if h["name"] == "Subject"), "No subject")
        sender = next((h["value"] for h in headers if h["name"] == "From"), "Unknown")

        link = f"https://mail.google.com/mail/u/0/#inbox/{msg['id']}"

        text += f"{i}. {subject}\n{sender}\n{link}\n\n"

    return text


async def loop():
    load_dotenv()

    bot = Bot(os.getenv("TELEGRAM_BOT_TOKEN"))
    chat_id = int(os.getenv("TARGET_CHAT_ID"))

    poll_seconds = get_int("POLL_SECONDS", 30)
    max_emails = get_int("MAX_EMAILS_PER_POLL", 3)

    gmail = get_gmail_service()

    await send_safe(bot, chat_id, "🚀 Бот запущен (24/7 Web Service)")

    while True:
        try:
            unread = list_unread(gmail, max_results=max_emails)

            if unread:
                messages = [get_message(gmail, m["id"]) for m in unread]
                text = build_text(messages)

                await send_safe(bot, chat_id, text)

                for m in unread:
                    mark_as_read(gmail, m["id"])

        except Exception as e:
            print("ERROR:", e)

        await asyncio.sleep(poll_seconds)


def run_async_loop():
    asyncio.run(loop())


@app.route("/")
def home():
    return "Bot is running"


if __name__ == "__main__":
    threading.Thread(target=run_async_loop).start()
    app.run(host="0.0.0.0", port=10000)
