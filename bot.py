import os
import logging
import asyncio
import urllib.parse
from datetime import datetime, timezone, timedelta
from typing import List, Dict

import requests
import xml.etree.ElementTree as ET
from google import genai
from telegram import Bot
from telegram.error import RetryAfter

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# ---------- Змінні середовища ----------
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
COMPANIES_RAW = os.environ.get("COMPANIES", "")

missing_vars = []
if not TELEGRAM_TOKEN:
    missing_vars.append("TELEGRAM_BOT_TOKEN")
if not CHAT_ID:
    missing_vars.append("TELEGRAM_CHAT_ID")
if not GEMINI_API_KEY:
    missing_vars.append("GEMINI_API_KEY")
if not COMPANIES_RAW:
    missing_vars.append("COMPANIES")

if missing_vars:
    logger.error(f"❌ Не вистачає змінних середовища: {', '.join(missing_vars)}")
    exit(1)

COMPANIES = [c.strip() for c in COMPANIES_RAW.split(",") if c.strip()]
logger.info(f"📋 Список компаній: {COMPANIES}")

# ---------- Парсинг RSS ----------
def fetch_news_for_company(company: str) -> List[Dict[str, str]]:
    query = f"{company} stock"
    encoded_query = urllib.parse.quote_plus(query)
    url = f"https://news.google.com/rss/search?q={encoded_query}&hl=en&gl=US&ceid=US:en"
    logger.info(f"🔍 Завантаження RSS для {company}")

    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
    except Exception as e:
        logger.error(f"Помилка завантаження/парсингу {company}: {e}")
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
        except Exception:
            continue

        if pub_time >= eight_hours_ago:
            news_items.append({
                "title": title,
                "link": link,
                "published": pub_time.strftime("%Y-%m-%d %H:%M:%S UTC"),
                "company": company
            })
    logger.info(f"✅ {company}: знайдено {len(news_items)} новин за останні 8 годин")
    return news_items

# ---------- Резервний дайджест (без ШІ) ----------
def make_fallback_digest(news_list: List[Dict[str, str]]) -> str:
    grouped = {}
    for item in news_list:
        grouped.setdefault(item["company"], []).append(item)

    result = "⚠️ *Дайджест згенеровано автоматично (без ШІ через ліміти API)*\n\n"
    for company, items in grouped.items():
        result += f"*{company}*:\n"
        for i, news in enumerate(items[:5], 1):  # максимум 5 найсвіжіших
            result += f"{i}. [{news['title']}]({news['link']})\n"
        result += "\n"
    return result

# ---------- Пошук доступної моделі Gemini ----------
def get_available_gemini_model(client: genai.Client) -> str:
    try:
        models = client.models.list()
        for model in models:
            name = model.name
            if "flash" in name and "generateContent" in str(model.supported_methods):
                logger.info(f"Знайдено модель: {name}")
                return name
        for model in models:
            if "generateContent" in str(model.supported_methods):
                logger.info(f"Використовуємо: {model.name}")
                return model.name
    except Exception as e:
        logger.warning(f"Не вдалося отримати список моделей: {e}")
    return None

# ---------- Генерація дайджесту (Gemini або fallback) ----------
def generate_digest(news_list: List[Dict[str, str]]) -> str:
    if not news_list:
        return "ℹ️ За останні 8 годин нових новин не виявлено."

    # Підготовка даних для ШІ
    news_text = "\n".join(
        f"**{item['company']}** – {item['title']} ({item['published']})\n{item['link']}"
        for item in news_list
    )
    prompt = f"""
Ти – асистент інвестора. Зроби короткий дайджест новин за останні 8 годин українською мовою.
Новини:
{news_text}

Вимоги: згрупуй по компаніях, обери 2-3 головні новини для кожної, додай посилання, стиль діловий, до 500 слів.
"""
    client = genai.Client(api_key=GEMINI_API_KEY)
    model_name = get_available_gemini_model(client)
    if not model_name:
        logger.warning("Немає доступної моделі Gemini → резервний дайджест")
        return make_fallback_digest(news_list)

    try:
        response = client.models.generate_content(model=model_name, contents=prompt)
        logger.info(f"✅ Gemini ({model_name}) спрацював")
        return response.text
    except Exception as e:
        logger.error(f"Помилка Gemini: {e} → резервний дайджест")
        return make_fallback_digest(news_list)

# ---------- Надсилання довгих повідомлень частинами ----------
async def send_long_message(bot: Bot, chat_id: str, text: str, parse_mode: str = "Markdown"):
    MAX_LEN = 4096
    if len(text) <= MAX_LEN:
        await bot.send_message(chat_id=chat_id, text=text, parse_mode=parse_mode)
        return

    # Розбиваємо по рядках, намагаючись не розірвати Markdown-посилання
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
        await asyncio.sleep(1)  # пауза, щоб уникнути флуду

async def send_to_telegram(text: str):
    bot = Bot(token=TELEGRAM_TOKEN)
    try:
        await send_long_message(bot, CHAT_ID, text, parse_mode="Markdown")
        logger.info("📨 Повідомлення надіслано")
    except Exception as e:
        logger.error(f"❌ Помилка при надсиланні: {e}")
    finally:
        try:
            await bot.close()
        except RetryAfter as e:
            logger.warning(f"Flood control при закритті, ігноруємо: {e}")
        except Exception as e:
            logger.warning(f"Помилка при закритті бота: {e}")

# ---------- Головна функція ----------
def main():
    now_utc = datetime.now(timezone.utc)
    logger.info(f"🚀 Запуск моніторингу (UTC: {now_utc})")

    all_news = []
    for company in COMPANIES:
        news = fetch_news_for_company(company)
        all_news.extend(news)

    if not all_news:
        logger.info("📭 Немає свіжих новин. Завершення.")
        return

    logger.info(f"📰 Всього знайдено {len(all_news)} новин. Генеруємо дайджест...")
    digest = generate_digest(all_news)
    header = f"📊 *Дайджест новин за останні 8 годин*\n🕒 {now_utc.strftime('%Y-%m-%d %H:%M UTC')}\n\n"
    full_message = header + digest

    asyncio.run(send_to_telegram(full_message))
    logger.info("✅ Роботу завершено")

if __name__ == "__main__":
    main()