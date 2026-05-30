# news_fetcher.py
import logging
import base64
import re
from typing import List, Dict
from google_news_api import GoogleNewsClient

try:
    from googlenewsdecoder import gnewsdecoder
    DECODER_AVAILABLE = True
except ImportError:
    DECODER_AVAILABLE = False
    logging.warning("Бібліотека 'googlenewsdecoder' не знайдена. Посилання не будуть декодуватися.")

logger = logging.getLogger(__name__)

def decode_google_news_url(google_url: str) -> str:
    """
    Декодує довге посилання Google News у пряме посилання на оригінальну статтю.
    Використовує бібліотеку googlenewsdecoder або власний fallback-метод.
    """
    if not google_url or 'news.google.com' not in google_url:
        return google_url

    # Fallback-метод на випадок, якщо бібліотека недоступна або не спрацювала
    # (на основі реалізації з newspaper4k, Issue #645)
    def try_fallback_decode(url: str) -> str:
        try:
            import base64
            import re
            _ENCODED_URL_PREFIX = "https://news.google.com/rss/articles/"
            _ENCODED_URL_PREFIX_WITH_CONSENT = "https://consent.google.com/m?continue=https://news.google.com/rss/articles/"
            _ENCODED_URL_RE = re.compile(rf"^(?:{re.escape(_ENCODED_URL_PREFIX_WITH_CONSENT)}|{re.escape(_ENCODED_URL_PREFIX)})(?P<encoded_url>[^?]+)")
            _DECODED_URL_RE = re.compile(rb'^\x08\x13".+?(?P<primary_url>http[^\xd2]+)\xd2\x01')
            match = _ENCODED_URL_RE.match(url)
            if not match:
                return url
            encoded_text = match.groupdict()["encoded_url"]
            encoded_text += "==="  # Фіксуємо неправильне padding
            decoded_text = base64.urlsafe_b64decode(encoded_text)
            match = _DECODED_URL_RE.match(decoded_text)
            if match:
                primary_url = match.groupdict()["primary_url"]
                return primary_url.decode()
            else:
                # Якщо не вдалося за match, пробуємо знайти посилання в декодованому тексті
                decoded_str = decoded_text.decode('utf-8', errors='ignore')
                url_match = re.search(r'https?://[^\s]+', decoded_str)
                if url_match:
                    return url_match.group(0)
            return url
        except Exception as e:
            logger.debug(f"Fallback decoding failed: {e}")
            return url

    # Спроба декодувати за допомогою бібліотеки
    if DECODER_AVAILABLE:
        try:
            decoded_result = gnewsdecoder(google_url)
            if decoded_result and decoded_result.get("status"):
                return decoded_result["decoded_url"]
        except Exception as e:
            logger.warning(f"Decoder library error: {e}")

    # Якщо бібліотека не впоралася, використовуємо fallback-метод
    return try_fallback_decode(google_url)

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