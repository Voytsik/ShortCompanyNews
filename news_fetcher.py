import logging
from datetime import datetime
from typing import List, Dict
from gnews import GNews
from googlenewsdecoder import new_decoderv1

logger = logging.getLogger(__name__)

def decode_google_news_url(google_url: str) -> str:
    """
    Декодує довге посилання Google News у пряме посилання на оригінальну статтю.
    Використовує new_decoderv1 з бібліотеки googlenewsdecoder.
    """
    if not google_url or 'news.google.com' not in google_url:
        return google_url

    try:
        decoded_result = new_decoderv1(google_url)
        if decoded_result and decoded_result.get("status"):
            return decoded_result["decoded_url"]
        else:
            logger.warning(f"Не вдалося розкодувати URL: {google_url}")
            return google_url
    except Exception as e:
        logger.error(f"Помилка при декодуванні URL {google_url}: {e}")
        return google_url

def fetch_news_for_company(company: str) -> List[Dict[str, str]]:
    """Отримує новини для заданої компанії."""
    all_news = []
    
    # Налаштування GNews для українських новин
    uk_client = GNews(language='uk', country='UA', max_results=5, period='8h')
    uk_news_items = uk_client.get_news(f"{company} stock")
    
    # Обробка українських новин
    for item in uk_news_items:
        decoded_url = decode_google_news_url(item.get('url', ''))
        all_news.append({
            "title": item.get('title', 'Без назви'),
            "link": decoded_url,
            "published": item.get('published date', datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")),
            "company": company,
            "language": "uk"
        })
    logger.info(f"✅ {company}: знайдено {len(uk_news_items)} українських новин за останні 8 годин")
    
    # Якщо українських новин менше 5, додаємо англійські
    if len(uk_news_items) < 5:
        en_client = GNews(language='en', country='US', max_results=5, period='8h')
        en_news_items = en_client.get_news(f"{company} stock")
        for item in en_news_items:
            decoded_url = decode_google_news_url(item.get('url', ''))
            all_news.append({
                "title": item.get('title', 'Без назви'),
                "link": decoded_url,
                "published": item.get('published date', datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")),
                "company": company,
                "language": "en"
            })
        logger.info(f"✅ {company}: додано {len(en_news_items)} англійських новин (всього: {len(all_news)})")
    
    return all_news