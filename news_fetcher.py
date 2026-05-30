import logging
import base64
import re
from datetime import datetime
from typing import List, Dict
from google_news_api import GoogleNewsClient
from googlenewsdecoder import new_decoderv1

logger = logging.getLogger(__name__)

def decode_google_news_url(google_url: str) -> str:
    """
    Декодує довге посилання Google News у пряме посилання на оригінальну статтю.
    Використовує стабільний метод new_decoderv1 з бібліотеки googlenewsdecoder.
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
    """Отримує новини для заданої компанії. Спочатку шукає українські, потім англійські."""
    all_news = []
    
    # Спочатку пробуємо знайти українські новини
    uk_news = _fetch_news_by_language(company, "uk")
    all_news.extend(uk_news)
    logger.info(f"✅ {company}: знайдено {len(uk_news)} українських новин за останні 8 годин")
    
    # Якщо українських новин менше 5, додаємо англійські
    if len(uk_news) < 5:
        en_news = _fetch_news_by_language(company, "en")
        all_news.extend(en_news)
        logger.info(f"✅ {company}: додано {len(en_news)} англійських новин (всього: {len(all_news)})")
    
    return all_news

def _fetch_news_by_language(company: str, lang_code: str) -> List[Dict[str, str]]:
    """
    Внутрішня функція для отримання новин конкретною мовою.
    """
    news_list = []
    try:
        # Встановлюємо мову та регіон за кодом
        if lang_code == "uk":
            language = "uk"
            country = "UA"
        else:  # lang_code == "en"
            language = "en"
            country = "US"
        
        client = GoogleNewsClient(language=language, country=country)
        # Шукаємо новини, додаючи "stock" для релевантності та за останні 8 годин
        search_results = client.search(f"{company} stock", when="8h")
        
        for result in search_results:
            # Отримуємо URL та декодуємо його
            original_url = result.get('link', '')
            decoded_url = decode_google_news_url(original_url)
            
            # Перевіряємо чи published не є None, якщо так — використовуємо поточний час
            published = result.get('published')
            if published is None:
                published = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
            
            news_list.append({
                "title": result.get('title', 'Без назви'),
                "link": decoded_url,  # Тут вже пряме посилання
                "published": published,
                "company": company,
                "language": lang_code
            })
    except Exception as e:
        logger.error(f"Помилка при отриманні новин для {company} мовою {lang_code}: {e}")
    
    return news_list