import asyncio
from datetime import datetime, timezone
from telegram import Bot
from config import logger, TELEGRAM_TOKEN, CHAT_ID, COMPANIES
from news_fetcher import fetch_news_for_company
from news_processor import generate_digest

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