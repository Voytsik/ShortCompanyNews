from telegram import Update
from telegram.ext import ContextTypes
from publisher import publish_news

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привіт! Я бот для моніторингу новин компаній.\n"
        "Новини публікуються автоматично кожні 8 годин за допомогою GitHub Actions."
    )

async def test_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Розпочинаю примусову перевірку...")
    await publish_news()