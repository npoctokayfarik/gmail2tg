import asyncio
from telegram import Bot
from telegram.error import RetryAfter, TimedOut, NetworkError


async def send_long(
    bot: Bot,
    chat_id: int,
    text: str,
    chunk_size: int = 3500,
    per_chunk_delay: float = 1.2,
) -> None:
    """
    Отправляет длинный текст кусками + антифлуд.
    Если Telegram отвечает RetryAfter — ждём сколько попросил и продолжаем.
    """
    if not text:
        return

    chunks = [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]

    for chunk in chunks:
        while True:
            try:
                await bot.send_message(chat_id=chat_id, text=chunk)
                break
            except RetryAfter as e:
                # Telegram говорит: подожди N секунд
                wait_s = int(getattr(e, "retry_after", 5)) + 1
                await asyncio.sleep(wait_s)
            except (TimedOut, NetworkError):
                # сеть/таймаут — небольшая пауза и повтор
                await asyncio.sleep(3)

        # маленькая пауза между кусками, чтобы не словить флуд
        await asyncio.sleep(per_chunk_delay)