import logging
import base64
import re
from typing import List, Dict
from google_news_api import GoogleNewsClient

logger = logging.getLogger(__name__)

def decode_google_news_url(google_url: str) -> str:
    """
    Декодує довге посилання Google News у пряме посилання на оригінальну статтю.
    Формат: https://news.google.com/rss/articles/CBM...?oc=5
    """
    if not google_url or 'news.google.com' not in google_url:
        return google_url
    
    try:
        # Витягуємо закодовану частину після "/articles/" до першого '?' або ')'
        match = re.search(r'/articles/([^?)]+)', google_url)
        if not match:
            return google_url
        
        encoded = match.group(1)
        # Додаємо необхідне padding для base64
        padding = 4 - (len(encoded) % 4)
        if padding != 4:
            encoded += '=' * padding
        
        # Замінюємо символи base64url на стандартні base64
        encoded = encoded.replace('-', '+').replace('_', '/')
        
        # Декодуємо
        decoded_bytes = base64.b64decode(encoded)
        decoded_str = decoded_bytes.decode('utf-8', errors='ignore')
        
        # Шукаємо підрядок, що починається з 'http'
        # Зазвичай оригінальне посилання починається після перших 4 байтів (не завжди)
        # Тому знаходимо перше входження 'http://' або 'https://'
        url_match = re.search(r'https?://[^\s]+', decoded_str)
        if url_match:
            return url_match.group(0)
        
        # Якщо не знайшли, повертаємо оригінал
        return google_url
    except Exception as e:
        logger.warning(f"Помилка декодування URL {google_url}: {e}")
        return google_url

def fetch_news_for_company(company: str) -> List[Dict[str, str]]:
    """
    Отримує новини для заданої компанії.
    Спочатку шукає новини українською, потім англійською.
    """
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
            original_url = result.get('link', '')
            # Декодуємо посилання, якщо воно від Google News
            decoded_url = decode_google_news_url(original_url)
            
            news_list.append({
                "title": result.get('title', 'Без назви'),
                "link": decoded_url,
                "published": result.get('published', ''),
                "company": company,
                "language": lang_code
            })
    except Exception as e:
        logger.error(f"Помилка при отриманні новин для {company} мовою {lang_code}: {e}")
    
    return news_list