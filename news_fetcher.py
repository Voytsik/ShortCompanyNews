import logging
from typing import List, Dict
from google_news_api import GoogleNewsClient
from googlenewsdecoder import new_decoderv1  # Декодер для посилань Google News

logger = logging.getLogger(__name__)

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
            decoded_url = original_url
            
            # Декодуємо тільки посилання, що містять news.google.com
            if original_url and 'news.google.com' in original_url:
                try:
                    decoded_result = new_decoderv1(original_url)
                    if decoded_result and decoded_result.get('decoded_url'):
                        decoded_url = decoded_result['decoded_url']
                        logger.debug(f"Декодовано посилання для {company}: {decoded_url}")
                    else:
                        logger.warning(f"Не вдалося декодувати URL: {original_url}")
                except Exception as e:
                    logger.error(f"Помилка декодування URL для {company}: {e}")
            else:
                decoded_url = original_url
            
            news_list.append({
                "title": result.get('title', 'Без назви'),
                "link": decoded_url,  # Тут вже пряме посилання
                "published": result.get('published', ''),
                "company": company,
                "language": lang_code
            })
    except Exception as e:
        logger.error(f"Помилка при отриманні новин для {company} мовою {lang_code}: {e}")
    
    return news_list