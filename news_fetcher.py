import logging
from typing import List, Dict
from google_news_api import GoogleNewsClient
from googlenewsdecoder import gnewsdecoder  # Декодер для посилань Google News

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
    Internal function to fetch news in a specific language.
    """
    news_list = []
    try:
        if lang_code == "uk":
            language = "uk"
            country = "UA"
        else:  # lang_code == "en"
            language = "en"
            country = "US"

        client = GoogleNewsClient(language=language, country=country)
        search_results = client.search(f"{company} stock", when="8h")

        for result in search_results:
            original_url = result.get('link', '')
            decoded_url = original_url

            # Decode only links that contain news.google.com
            if original_url and 'news.google.com' in original_url:
                try:
                    # Use gnewsdecoder as it's more robust than the deprecated new_decoderv1
                    decoded_result = gnewsdecoder(original_url)
                    if decoded_result and decoded_result.get('status'):
                        decoded_url = decoded_result['decoded_url']
                        logger.debug(f"Successfully decoded URL for {company}: {decoded_url}")
                    else:
                        error_msg = decoded_result.get('message', 'Unknown error')
                        logger.warning(f"Failed to decode URL: {original_url} - Reason: {error_msg}")
                except Exception as e:
                    logger.error(f"Error decoding URL for {company}: {e}")
            else:
                decoded_url = original_url

            news_list.append({
                "title": result.get('title', 'Без назви'),
                "link": decoded_url,  # Now contains the direct article link
                "published": result.get('published', ''),
                "company": company,
                "language": lang_code
            })
    except Exception as e:
        logger.error(f"Error fetching news for {company} in language {lang_code}: {e}")

    return news_list