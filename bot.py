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
    """Завантажує Google News RSS через requests та XML парсер."""
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

        if title_elem is None or link_elem is None or pub_elem is None:
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

# ---------- Резервний дайджест без ШІ ----------
def make_fallback_digest(news_list: List[Dict[str, str]]) -> str:
    """Формує простий текстовий дайджест у випадку недоступності Gemini."""
    grouped = {}
    for item in news_list:
        comp = item["company"]
        if comp not in grouped:
            grouped[comp] = []
        grouped[comp].append(item)

    result = "⚠️ *Дайджест згенеровано автоматично (без ШІ через ліміти API)*\n\n"
    for company, items in grouped.items():
        result += f"*{company}*:\n"
        for i, news in enumerate(items[:5], 1):  # максимум 5 новин на компанію
            result += f"{i}. [{news['title']}]({news['link']}) – {news['published']}\n"
        result += "\n"
    return result

# ---------- Генерація дайджесту через Gemini (з автоматичним вибором моделі) ----------
def get_available_gemini_model(client: genai.Client) -> str:
    """Повертає першу доступну модель, яка підтримує generateContent."""
    try:
        models = client.models.list()
        for model in models:
            name = model.name
            # Шукаємо моделі flash або pro
            if "gemini-2.0-flash" in name or "gemini-1.5-flash" in name:
                if "generateContent" in str(model.supported_methods):
                    logger.info(f"Знайдено доступну модель: {name}")
                    return name
        # Якщо не знайшли flash, беремо будь-яку модель з generateContent
        for model in models:
            if "generateContent" in str(model.supported_methods):
                logger.info(f"Використовуємо модель: {model.name}")
                return model.name
    except Exception as e:
        logger.warning(f"Не вдалося отримати список моделей: {e}")
    return None

def generate_digest(news_list: List[Dict[str, str]]) -> str:
    if not news_list:
        return "ℹ️ За останні 8 годин нових новин не виявлено."

    # Підготовка тексту новин для промпту
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
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    # Спроба знайти доступну модель
    model_name = get_available_gemini_model(client)
    if not model_name:
        logger.warning("Не знайдено жодної моделі для generateContent, використовуємо резервний дайджест")
        return make_fallback_digest(news_list)
    
    try:
        response = client.models.generate_content(model=model_name, contents=prompt)
        logger.info(f"✅ Gemini успішно використано модель: {model_name}")
        return response.text
    except Exception as e:
        logger.error(f"Помилка при генерації через {model_name}: {e}")
        # Спроба інших моделей (захардкоджені як запасний варіант)
        fallback_models = ["gemini-1.5-flash", "gemini-2.0-flash-lite"]
        for fb in fallback_models:
            try:
                response = client.models.generate_content(model=fb, contents=prompt)
                logger.info(f"✅ Fallback модель {fb} спрацювала")
                return response.text
            except Exception as fb_err:
                logger.warning(f"Fallback {fb} не вдався: {fb_err}")
        # Якщо нічого не допомогло – резервний дайджест
        logger.error("Всі спроби Gemini невдалі, використовуємо резервний дайджест")
        return make_fallback_digest(news_list)

# ---------- Надсилання в Telegram ----------
async def send_to_telegram(text: str):
    bot = Bot(token=TELEGRAM_TOKEN)
    try:
        await bot.send_message(chat_id=CHAT_ID, text=text, parse_mode="Markdown")
        logger.info("📨 Повідомлення надіслано")
    except Exception as e:
        logger.error(f"❌ Помилка Telegram при надсиланні: {e}")
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

    if len(full_message) > 4096:
        full_message = full_message[:4093] + "..."

    asyncio.run(send_to_telegram(full_message))
    logger.info("✅ Роботу завершено")

if __name__ == "__main__":
    main()