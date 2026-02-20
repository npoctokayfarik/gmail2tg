from __future__ import annotations
from telegram import Bot


async def send_long(bot: Bot, chat_id: int, text: str) -> None:
    # лимит телеги ~4096, режем
    max_len = 3500
    if len(text) <= max_len:
        await bot.send_message(chat_id=chat_id, text=text, disable_web_page_preview=True)
        return

    for i in range(0, len(text), max_len):
        await bot.send_message(
            chat_id=chat_id,
            text=text[i:i + max_len],
            disable_web_page_preview=True
        )