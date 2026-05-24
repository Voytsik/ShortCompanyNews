import os
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict
import asyncio

import feedparser
from google import genai
from telegram import Bot

# ------------------ Логування ------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# ------------------ Змінні середовища ------------------
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("@t1246fdf")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
COMPANIES_RAW = os.environ.get("Apple", "Tesla")   # наприклад "Apple,Microsoft,Tesla"

if not all([TELEGRAM_TOKEN, CHAT_ID, GEMINI_API_KEY, COMPANIES_RAW]):
    logger.error("❌ Не вистачає змінних середовища. Перевірте:")
    logger.error("   TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, GEMINI_API_KEY, COMPANIES")
    exit(1)

COMPANIES = [c.strip() for c in COMPANIES_RAW.split(",") if c.strip()]
logger.info(f"📋 Список компаній для моніторингу: {COMPANIES}")

# Часовий пояс – усюди UTC (RSS Google News повертає UTC)
NOW_UTC = datetime.now(timezone.utc)
EIGHT_HOURS_AGO = NOW_UTC - timedelta(hours=8)


# ------------------ Отримання новин ------------------
def fetch_news_for_company(company: str) -> List[Dict[str, str]]:
    """
    Завантажує RSS з Google News для компанії.
    Повертає список новин, опублікованих за останні 8 годин.
    """
    query = f"{company} stock"
    rss_url = f"https://news.google.com/rss/search?q={query}&hl=en&gl=US&ceid=US:en"
    logger.info(f"🔍 Опитуємо RSS для {company}: {rss_url}")

    news_items = []
    try:
        feed = feedparser.parse(rss_url)
        for entry in feed.entries:
            published_parsed = entry.get("published_parsed")
            if not published_parsed:
                continue

            pub_time = datetime.fromtimestamp(
                datetime(*published_parsed[:6]).timestamp(),
                tz=timezone.utc
            )
            if pub_time >= EIGHT_HOURS_AGO:
                news_items.append({
                    "title": entry.get("title", "Без заголовка"),
                    "link": entry.get("link", "#"),
                    "published": pub_time.strftime("%Y-%m-%d %H:%M:%S UTC"),
                    "company": company
                })
        logger.info(f"✅ {company}: знайдено {len(news_items)} новин за останні 8 годин")
    except Exception as e:
        logger.error(f"⚠️ Помилка при отриманні RSS для {company}: {e}")
    return news_items


# ------------------ Генерація дайджесту через Gemini ------------------
def generate_digest(news_list: List[Dict[str, str]]) -> str:
    """
    Відправляє знайдені новини в Gemini та отримує коротку вижимку.
    """
    if not news_list:
        return "ℹ️ За останні 8 годин нових новин не виявлено."

    # Формуємо промпт
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
        response = client.models.generate_content(
            model="gemini-2.0-flash-exp",
            contents=prompt
        )
        return response.text
    except Exception as e:
        logger.error(f"❌ Помилка Gemini: {e}")
        return "⚠️ Не вдалося згенерувати дайджест через технічну помилку."


# ------------------ Надсилання в Telegram ------------------
async def send_to_telegram(text: str):
    """Надсилає повідомлення в Telegram канал/чат."""
    bot = Bot(token=TELEGRAM_TOKEN)
    try:
        await bot.send_message(chat_id=CHAT_ID, text=text, parse_mode="Markdown")
        logger.info("📨 Повідомлення успішно надіслано")
    except Exception as e:
        logger.error(f"❌ Помилка Telegram: {e}")
    finally:
        await bot.close()


# ------------------ Головна функція ------------------
def main():
    logger.info(f"🚀 Запуск моніторингу (UTC: {NOW_UTC})")
    all_news = []

    # 1. Збираємо свіжі новини з усіх компаній
    for company in COMPANIES:
        news = fetch_news_for_company(company)
        all_news.extend(news)

    # 2. Якщо новин немає – завершуємо роботу
    if not all_news:
        logger.info("📭 Немає свіжих новин. Завершення.")
        return

    logger.info(f"📰 Всього знайдено {len(all_news)} новин. Генеруємо дайджест...")

    # 3. Генеруємо підсумок через Gemini
    digest = generate_digest(all_news)

    # 4. Додаємо заголовок із часом
    header = (
        f"📊 *Дайджест новин за останні 8 годин*\n"
        f"🕒 {NOW_UTC.strftime('%Y-%m-%d %H:%M UTC')}\n\n"
    )
    full_message = header + digest

    # 5. Обрізаємо, якщо перевищено ліміт Telegram (4096 символів)
    if len(full_message) > 4096:
        full_message = full_message[:4093] + "..."

    # 6. Надсилаємо повідомлення
    asyncio.run(send_to_telegram(full_message))
    logger.info("✅ Роботу завершено")


if __name__ == "__main__":
    main()