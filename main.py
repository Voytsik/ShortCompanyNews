from contextlib import asynccontextmanager
import asyncio
from fastapi import FastAPI, Request, HTTPException
from telegram import Update
from telegram.ext import Application, CommandHandler
import uvicorn

from config import logger, TELEGRAM_TOKEN, WEBHOOK_URL, TRIGGER_SECRET, PORT
from handlers import start, test_now
from publisher import publish_news

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ініціалізація Telegram Application
    telegram_app = Application.builder().token(TELEGRAM_TOKEN).build()
    telegram_app.add_handler(CommandHandler("start", start))
    telegram_app.add_handler(CommandHandler("test", test_now))
    await telegram_app.initialize()
    await telegram_app.bot.set_webhook(WEBHOOK_URL, allowed_updates=Update.ALL_TYPES)
    logger.info(f"✅ Webhook встановлено на {WEBHOOK_URL}")
    app.state.telegram_app = telegram_app
    yield
    await telegram_app.stop()
    logger.info("🛑 Додаток завершує роботу")

fastapi_app = FastAPI(lifespan=lifespan)

@fastapi_app.post("/webhook")
async def webhook(request: Request):
    telegram_app = request.app.state.telegram_app
    update = Update.de_json(await request.json(), telegram_app.bot)
    await telegram_app.process_update(update)
    return {"status": "ok"}

@fastapi_app.get("/health")
async def health():
    return {"status": "alive"}

@fastapi_app.get("/trigger_news")
async def trigger_news(secret: str):
    """Ендпоінт для виклику публікації новин (з GitHub Actions)."""
    if secret != TRIGGER_SECRET:
        raise HTTPException(status_code=403, detail="Invalid secret")
    asyncio.create_task(publish_news())
    return {"status": "News publication started"}

@fastapi_app.get("/")
async def root():
    return {"message": "Telegram News Bot is running. Use /trigger_news?secret=... to publish news."}

if __name__ == "__main__":
    uvicorn.run(fastapi_app, host="0.0.0.0", port=PORT)