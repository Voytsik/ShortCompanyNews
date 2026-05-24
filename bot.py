import os
import logging
import asyncio
import urllib.parse
from datetime import datetime, timezone, timedelta
from typing import List, Dict
from contextlib import asynccontextmanager

import requests
import xml.etree.ElementTree as ET
from google import genai
from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, ContextTypes
from fastapi import FastAPI, Request, HTTPException
import uvicorn

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# ---------- Змінні середовища ----------
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
COMPANIES_RAW = os.environ.get("COMPANIES", "")
WEBHOOK_PATH = "/webhook"
TRIGGER_SECRET = os.environ.get("TRIGGER_SECRET", "default_secret_change_me")
PORT = int(os.environ.get("PORT", 10000))
BASE_URL = os.environ.get("RENDER_EXTERNAL_URL")

missing_vars = []
if not TELEGRAM_TOKEN:
    missing_vars.append("TELEGRAM_BOT_TOKEN")
if not CHAT_ID:
    missing_vars.append("TELEGRAM_CHAT_ID")
if not GEMINI_API_KEY:
    missing_vars.append("GEMINI_API_KEY")
if not COMPANIES_RAW:
    missing_vars.append("COMPANIES")
if not BASE_URL:
    missing_vars.append("RENDER_EXTERNAL_URL")
if missing_vars:
    logger.error(f"❌ Не вистачає змінних: {', '.join(missing_vars)}")
    exit(1)

COMPANIES = [c.strip() for c in COMPANIES_RAW.split(",") if c.strip()]
WEBHOOK_URL = f"{BASE_URL}{WEBHOOK_PATH}"
logger.info(f"📋 Компанії: {COMPANIES}")
logger.info(f"🔗 Webhook URL: {WEBHOOK_URL}")

# ---------- Функції для роботи з новинами (без змін) ----------
def fetch_news_for_company(company: str) -> List[Dict[str, str]]:
    query = f"{company} stock"
    encoded_query = urllib.parse.quote_plus(query)
    url = f"https://news.google.com/rss/search?q={encoded_query}&hl=en&gl=US&ceid=US:en"
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
    except Exception as e:
        logger.error(f"Помилка RSS {company}: {e}")
        return []

    news_items = []
    now_utc = datetime.now(timezone.utc)
    eight_hours_ago = now_utc - timedelta(hours=8)

    for item in root.findall(".//item"):
        title_elem = item.find("title")
        link_elem = item.find("link")
        pub_elem = item.find("pubDate")
        if None in (title_elem, link_elem, pub_elem):
            continue
        title = title_elem.text
        link = link_elem.text
        pub_date_str = pub_elem.text
        try:
            pub_time = datetime.strptime(pub_date_str, "%a, %d %b %Y %H:%M:%S %Z").replace(tzinfo=timezone.utc)
        except:
            continue
        if pub_time >= eight_hours_ago:
            news_items.append({
                "title": title,
                "link": link,
                "published": pub_time.strftime("%Y-%m-%d %H:%M:%S UTC"),
                "company": company
            })
    logger.info(f"✅ {company}: {len(news_items)} новин за останні 8 годин")
    return news_items

def make_fallback_digest(news_list: List[Dict[str, str]]) -> str:
    grouped = {}
    for item in news_list:
        grouped.setdefault(item["company"], []).append(item)
    result = "⚠️ *Автоматичний дайджест (без ШІ)*\n\n"
    for company, items in grouped.items():
        result += f"*{company}*:\n"
        for i, news in enumerate(items[:5], 1):
            result += f"{i}. [{news['title']}]({news['link']})\n"
        result += "\n"
    return result

def generate_digest(news_list: List[Dict[str, str]]) -> str:
    if not news_list:
        return "ℹ️ За останні 8 годин нових новин не виявлено."
    # Обмежуємо кількість новин для Gemini, щоб не перевищити токени
    news_text = "\n".join(
        f"**{item['company']}** – {item['title']} ({item['published']})\n{item['link']}"
        for item in news_list[:30]
    )
    prompt = f"""
Ти асистент інвестора. Зроби короткий дайджест новин за останні 8 годин українською мовою.
Новини:
{news_text}
Вимоги: згрупуй по компаніях, обери 2-3 головні новини для кожної, додай посилання, стиль діловий, до 500 слів.
"""
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        models_to_try = ["gemini-1.5-flash", "gemini-2.0-flash-lite", "gemini-2.0-flash"]
        for model_name in models_to_try:
            try:
                response = client.models.generate_content(model=model_name, contents=prompt)
                logger.info(f"✅ Gemini використано модель: {model_name}")
                return response.text
            except Exception as e:
                logger.warning(f"Модель {model_name} не вдалася: {e}")
                continue
        return make_fallback_digest(news_list)
    except Exception as e:
        logger.error(f"Помилка Gemini: {e}")
        return make_fallback_digest(news_list)

async def send_long_message(bot: Bot, chat_id: str, text: str, parse_mode: str = "Markdown"):
    MAX_LEN = 4096
    if len(text) <= MAX_LEN:
        await bot.send_message(chat_id=chat_id, text=text, parse_mode=parse_mode)
        return
    parts = []
    while len(text) > MAX_LEN:
        split_at = text.rfind('\n', 0, MAX_LEN)
        if split_at == -1:
            split_at = MAX_LEN
        parts.append(text[:split_at])
        text = text[split_at:]
    if text:
        parts.append(text)
    for i, part in enumerate(parts):
        header = f"📄 Частина {i+1}/{len(parts)}\n\n" if len(parts) > 1 else ""
        await bot.send_message(chat_id=chat_id, text=header + part, parse_mode=parse_mode)
        await asyncio.sleep(1)

async def publish_news():
    """Основна функція: збір новин, генерація дайджесту, надсилання в Telegram."""
    logger.info("🔍 Початок публікації новин (тригер від GitHub Actions)")
    now_utc = datetime.now(timezone.utc)
    all_news = []
    for company in COMPANIES:
        news = fetch_news_for_company(company)
        all_news.extend(news)

    if not all_news:
        logger.info("📭 Немає свіжих новин. Нічого не публікуємо.")
        return

    logger.info(f"📰 Всього знайдено {len(all_news)} новин. Генеруємо дайджест...")
    digest = generate_digest(all_news)
    header = f"📊 *Дайджест новин за останні 8 годин*\n🕒 {now_utc.strftime('%Y-%m-%d %H:%M UTC')}\n\n"
    full_message = header + digest

    bot = Bot(token=TELEGRAM_TOKEN)
    try:
        await send_long_message(bot, CHAT_ID, full_message, parse_mode="Markdown")
        logger.info("📨 Дайджест успішно надіслано в Telegram")
    except Exception as e:
        logger.error(f"❌ Помилка при надсиланні: {e}")
    finally:
        await bot.close()

# ---------- Telegram Handlers для команд ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привіт! Я бот для моніторингу новин компаній.\n"
        "Новини публікуються автоматично кожні 8 годин за допомогою GitHub Actions."
    )

async def test_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Розпочинаю примусову перевірку...")
    await publish_news()

# ---------- FastAPI з Lifespan ----------
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

@fastapi_app.post(WEBHOOK_PATH)
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
    # Запускаємо публікацію у фоновому режимі, щоб не блокувати відповідь
    asyncio.create_task(publish_news())
    return {"status": "News publication started"}

@fastapi_app.get("/")
async def root():
    return {"message": "Telegram News Bot is running. Use /trigger_news?secret=... to publish news."}

if __name__ == "__main__":
    uvicorn.run(fastapi_app, host="0.0.0.0", port=PORT)