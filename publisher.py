import asyncio
from datetime import datetime, timezone
from telegram import Bot
from telegram.error import RetryAfter
from config import logger, TELEGRAM_TOKEN, CHAT_ID, COMPANIES
from news_fetcher import fetch_news_for_company
from news_processor import generate_digest

async def send_long_message(bot: Bot, chat_id: str, text: str, parse_mode: str = "Markdown"):
    """
    Надсилає довге повідомлення, розбиваючи на частини до 4096 символів.
    При помилці RetryAfter чекає вказаний час і повторює спробу.
    """
    MAX_LEN = 4096
    if len(text) <= MAX_LEN:
        await send_with_retry(bot, chat_id, text, parse_mode)
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
        await send_with_retry(bot, chat_id, header + part, parse_mode)
        await asyncio.sleep(2)  # Збільшили паузу між частинами до 2 секунд

async def send_with_retry(bot: Bot, chat_id: str, text: str, parse_mode: str, max_retries: int = 3):
    """
    Надсилає повідомлення з повторними спробами у разі помилки RetryAfter.
    """
    for attempt in range(max_retries):
        try:
            await bot.send_message(chat_id=chat_id, text=text, parse_mode=parse_mode)
            return
        except RetryAfter as e:
            wait_time = e.retry_after
            logger.warning(f"Flood control exceeded. Retry after {wait_time} seconds. Attempt {attempt+1}/{max_retries}")
            await asyncio.sleep(wait_time)
        except Exception as e:
            logger.error(f"Unexpected error sending message: {e}")
            if attempt == max_retries - 1:
                raise
            await asyncio.sleep(2 ** attempt)  # exponential backoff
    logger.error(f"Failed to send message after {max_retries} attempts")

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
        # Надаємо час для завершення всіх запитів, потім закриваємо бота
        await asyncio.sleep(1)
        await bot.close()