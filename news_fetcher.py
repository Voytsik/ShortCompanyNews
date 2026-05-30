import logging
import base64
import re
from datetime import datetime
from typing import List, Dict
import requests
import feedparser
from googlenewsdecoder import new_decoderv1

logger = logging.getLogger(__name__)

def decode_google_news_url(google_url: str) -> str:
    """
    Декодує довге посилання Google News у пряме посилання на оригінальну статтю.
    Використовує new_decoderv1, а у разі невдачі — вбудований base64 fallback.
    """
    if not google_url or 'news.google.com' not in google_url:
        return google_url

    # Спроба 1: Використання new_decoderv1 (найкращий варіант)
    try:
        decoded_result = new_decoderv1(google_url)
        if decoded_result and decoded_result.get("status"):
            return decoded_result["decoded_url"]
    except Exception as e:
        logger.debug(f"new_decoderv1 failed: {e}")

    # Спроба 2: Вбудований base64 метод (надійний fallback)
    try:
        match = re.search(r'/articles/([^?]+)', google_url)
        if match:
            encoded_part = match.group(1)
            # Додаємо необхідний padding для base64
            padding = 4 - (len(encoded_part) % 4)
            if padding != 4:
                encoded_part += '=' * padding
            
            decoded_bytes = base64.urlsafe_b64decode(encoded_part)
            decoded_str = decoded_bytes.decode('utf-8', errors='ignore')
            # Шукаємо будь-яке посилання в декодованих даних
            url_match = re.search(r'https?://[^\s\x00-\x1f\x7f-\x9f]+', decoded_str)
            if url_match:
                return url_match.group(0)
    except Exception as e:
        logger.debug(f"Fallback decoding failed: {e}")
    
    # Якщо нічого не спрацювало, повертаємо оригінал
    logger.warning(f"Не вдалося розкодувати URL: {google_url}")
    return google_url

def fetch_news_for_company(company: str) -> List[Dict[str, str]]:
    """Отримує новини для заданої компанії."""
    all_news = []
    
    # Запит до Google News RSS (українською)
    uk_rss_url = f"https://news.google.com/rss/search?q={company}+stock&hl=uk&gl=UA&ceid=UA:uk"
    all_news += _parse_rss_feed(uk_rss_url, company, "uk")
    logger.info(f"✅ {company}: знайдено {len(all_news)} українських новин за останні 8 годин")
    
    # Якщо українських новин менше 5, додаємо англійські
    if len(all_news) < 5:
        en_rss_url = f"https://news.google.com/rss/search?q={company}+stock&hl=en&gl=US&ceid=US:en"
        en_news = _parse_rss_feed(en_rss_url, company, "en")
        all_news.extend(en_news)
        logger.info(f"✅ {company}: додано {len(en_news)} англійських новин (всього: {len(all_news)})")
    
    return all_news

def _parse_rss_feed(url: str, company: str, lang_code: str) -> List[Dict[str, str]]:
    """Парсить RSS стрічку Google News та повертає список новин."""
    news_list = []
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        feed = feedparser.parse(response.content)
        
        for entry in feed.entries[:5]:
            decoded_url = decode_google_news_url(entry.link)
            news_list.append({
                "title": entry.get('title', 'Без назви'),
                "link": decoded_url,
                "published": entry.get('published', datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")),
                "company": company,
                "language": lang_code
            })
    except Exception as e:
        logger.error(f"Помилка при отриманні новин з {url}: {e}")
    return news_list