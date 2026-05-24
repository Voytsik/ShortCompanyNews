import os
import logging
import asyncio
import urllib.parse
from datetime import datetime, timezone, timedelta
from typing import List, Dict
import xml.etree.ElementTree as ET

import requests
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

# ---------- Час ----------
NOW_UTC = datetime.now(timezone.utc)
EIGHT_HOURS_AGO = NOW_UTC - timedelta(hours=8)


# ---------- RSS парсер ----------
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
        logger.error(f"Помилка завантаження {company}: {e}")
        return []

    news_items = []
    for item in root.findall(".//item"):
        title_elem = item.find("title")
        link_elem = item.find("link")
        pub_elem = item.find("pubDate")
        if title_elem is None or link_elem is None or pub_elem is None:
            continue

        title = title_elem.text
        link = link_elem.text
        pub_date_str = pub_elem.text

        try:
            pub_time = datetime.strptime(pub_date_str, "%a, %d %b %Y %H:%M:%S %Z").replace(tzinfo=timezone.utc)
        except Exception:
            continue

        if pub_time >= EIGHT_HOURS_AGO:
            news_items.append({
                "title": title,
                "link": link,
                "published": pub_time.strftime("%Y-%m-%d %H:%M:%S UTC"),
                "company": company
            })
    logger.info(f"✅ {company}: знайдено {len(news_items)} новин за останні 8 годин")
    return news_items


# ---------- Gemini дайджест ----------
def generate_digest(news_list: List[Dict[str, str]]) -> str:
    if not news_list:
        return "ℹ️ За останні 8 годин нових новин не виявлено."

    news_text = ""
    for item in news_list:
        news_text += (
            f"**Компанія:** {item['company']}\n"
            f"**Заголовок:** {item['title']}\n"
            f"**Час:** {item['published']}\n"
            f"**Посилання:** {item['link']}\n\n"
        )

    prompt = f"""
Ти – асистент інвестора. Зроби короткий, інформативний дайджест новин за останні 8 годин.

Ось новини:
{news_text}

Вимоги:
- Пиши українською мовою.
- Згрупуй новини по компаніях.
- Для кожної компанії обери 2-3 найважливіші новини (якщо їх більше).
- Додай посилання на джерела.
- Стиль – діловий, лаконічний, обсяг до 500 слів.
"""
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        # Використовуємо стабільну модель gemini-1.5-flash (або gemini-2.0-flash, якщо доступна)
        response = client.models.generate_content(
            model="gemini-1.5-flash",
            contents=prompt
        )
        return response.text
    except Exception as e:
        logger.error(f"❌ Помилка Gemini: {e}")
        return "⚠️ Не вдалося згенерувати дайджест через технічну помилку."


# ---------- Надсилання в Telegram з обробкою flood control ----------
async def send_to_telegram(text: str):
    bot = Bot(token=TELEGRAM_TOKEN)
    try:
        await bot.send_message(chat_id=CHAT_ID, text=text, parse_mode="Markdown")
        logger.info("📨 Повідомлення надіслано")
    except RetryAfter as e:
        logger.warning(f"⏳ Flood control: треба почекати {e.retry_after} секунд")
        # Якщо потрібно, можна додати asyncio.sleep, але для cron-завдання краще просто вийти
    except Exception as e:
        logger.error(f"❌ Помилка Telegram: {e}")
    finally:
        try:
            await bot.close()
        except Exception as close_err:
            logger.warning(f"Помилка при закритті бота: {close_err}")


# ---------- Головна функція ----------
def main():
    logger.info(f"🚀 Запуск моніторингу (UTC: {NOW_UTC})")
    all_news = []
    for company in COMPANIES:
        news = fetch_news_for_company(company)
        all_news.extend(news)

    if not all_news:
        logger.info("📭 Немає свіжих новин. Завершення.")
        return

    logger.info(f"📰 Всього знайдено {len(all_news)} новин. Генеруємо дайджест...")

    digest = generate_digest(all_news)
    header = f"📊 *Дайджест новин за останні 8 годин*\n🕒 {NOW_UTC.strftime('%Y-%m-%d %H:%M UTC')}\n\n"
    full_message = header + digest

    if len(full_message) > 4096:
        full_message = full_message[:4093] + "..."

    # Запускаємо асинхронну відправку
    asyncio.run(send_to_telegram(full_message))
    logger.info("✅ Роботу завершено")


if __name__ == "__main__":
    main()