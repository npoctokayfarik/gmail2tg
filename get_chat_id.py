import os
from dotenv import load_dotenv
from telegram.ext import Application, CommandHandler

load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

async def start(update, context):
    await update.message.reply_text(f"chat_id: {update.effective_chat.id}")

app = Application.builder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))

print("Bot started...")
app.run_polling()