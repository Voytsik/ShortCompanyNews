# news_fetcher.py
import logging
import base64
import re
from typing import List, Dict
from google_news_api import GoogleNewsClient

logger = logging.getLogger(__name__)

def decode_google_news_url(google_url: str) -> str:
    """Декодує довге посилання Google News у пряме посилання на оригінальну статтю."""
    if not google_url or 'news.google.com' not in google_url:
        return google_url
    
    try:
        # 1. Витягуємо закодовану частину (після /articles/ або /read/)
        match = re.search(r'/(?:articles|read)/([^?)]+)', google_url)
        if not match:
            logger.debug(f"Can't find encoded part in URL: {google_url}")
            return google_url
        
        encoded = match.group(1)
        
        # 2. Додаємо необхідний padding для base64
        # Оригінальний base64url decoded part may be padded with '=' at the end
        padding = 4 - (len(encoded) % 4)
        if padding != 4:
            encoded += '=' * padding
        
        # 3. Замінюємо символи base64url на стандартні base64
        encoded = encoded.replace('-', '+').replace('_', '/')
        
        # 4. Декодуємо
        decoded_bytes = base64.b64decode(encoded)
        decoded_str = decoded_bytes.decode('utf-8', errors='ignore')
        
        # 5. Шукаємо підрядок, що починається з 'http'
        url_match = re.search(r'https?://[^\s]+', decoded_str)
        if url_match:
            return url_match.group(0)
        
        logger.warning(f"Could not find URL in decoded string: {decoded_str[:100]}")
        return google_url
        
    except Exception as e:
        logger.warning(f"Error decoding URL {google_url}: {e}")
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