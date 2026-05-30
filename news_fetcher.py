import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict
from GoogleNews import GoogleNews

# Налаштування логування (використовуємо той самий формат, що й у config.py)
logger = logging.getLogger(__name__)

def fetch_news_for_company(company: str, prefer_ukrainian: bool = True) -> List[Dict[str, str]]:
    """
    Отримує новини для заданої компанії.
    
    Args:
        company: Назва компанії для пошуку
        prefer_ukrainian: Якщо True, спочатку шукає українські новини,
                         потім англійські, якщо українських недостатньо
    
    Returns:
        Список словників з новинами, кожен містить:
        - title: заголовок новини
        - link: пряме посилання на оригінальну статтю
        - published: дата публікації
        - company: назва компанії
        - language: мова новини ('uk' або 'en')
    """
    all_news = []
    now_utc = datetime.now(timezone.utc)
    eight_hours_ago = now_utc - timedelta(hours=8)
    
    if prefer_ukrainian:
        # Спочатку пробуємо отримати українські новини
        uk_news = _fetch_news_by_language(company, 'uk', eight_hours_ago)
        all_news.extend(uk_news)
        logger.info(f"✅ {company}: знайдено {len(uk_news)} українських новин за останні 8 годин")
        
        # Якщо українських новин менше 5, додаємо англійські
        if len(uk_news) < 5:
            en_news = _fetch_news_by_language(company, 'en', eight_hours_ago)
            all_news.extend(en_news)
            logger.info(f"✅ {company}: додано {len(en_news)} англійських новин (всього: {len(all_news)})")
    else:
        # Якщо не потрібно优先українські, просто шукаємо англійські
        en_news = _fetch_news_by_language(company, 'en', eight_hours_ago)
        all_news.extend(en_news)
        logger.info(f"✅ {company}: {len(en_news)} новин за останні 8 годин")
    
    return all_news

def _fetch_news_by_language(company: str, language: str, since_time: datetime) -> List[Dict[str, str]]:
    """
    Внутрішня функція для отримання новин конкретною мовою.
    
    Args:
        company: Назва компанії
        language: Код мови ('uk' для української, 'en' для англійської)
        since_time: Час, з якого шукати новини
    
    Returns:
        Список новин вказаною мовою
    """
    news_list = []
    
    try:
        # Ініціалізуємо Googlenews з відповідними параметрами
        googlenews = GoogleNews(
            lang=language,      # мова пошуку
            region='UA' if language == 'uk' else 'US',  # регіон
            period='7d',        # шукаємо за останні 7 днів (потім відфільтруємо за 8 годин)
            encode='utf-8'
        )
        
        # Виконуємо пошук
        googlenews.search(f"{company} stock")
        
        # Отримуємо результати
        results = googlenews.results()
        
        for result in results:
            try:
                # Отримуємо дату публікації (якщо доступна)
                pub_date_str = result.get('date', '')
                pub_time = _parse_google_news_date(pub_date_str)
                
                # Фільтруємо за останні 8 годин
                if pub_time and pub_time >= since_time:
                    # GoogleNews вже повертає прямі посилання на статті
                    news_list.append({
                        "title": result.get('title', 'Без назви'),
                        "link": result.get('link', ''),
                        "published": pub_time.strftime("%Y-%m-%d %H:%M:%S UTC"),
                        "company": company,
                        "language": language
                    })
            except Exception as e:
                logger.warning(f"Помилка при обробці новини для {company}: {e}")
                continue
                
    except Exception as e:
        logger.error(f"Помилка при отриманні новин для {company} мовою {language}: {e}")
    
    return news_list

def _parse_google_news_date(date_str: str) -> datetime:
    """
    Парсить дату з результатів Google News у формат datetime.
    
    Google News може повертати дати у різних форматах:
    - "2025-05-30 10:30:00"
    - "2 hours ago"
    - "May 30, 2025"
    """
    if not date_str:
        return datetime.now(timezone.utc) - timedelta(hours=9)  # фолбек: 9 годин тому
    
    try:
        # Спробуємо розпізнати різні формати
        now_utc = datetime.now(timezone.utc)
        
        # Формат "X hours ago"
        if 'hours ago' in date_str:
            hours = int(date_str.split()[0])
            return now_utc - timedelta(hours=hours)
        
        # Формат "X minutes ago"
        elif 'minutes ago' in date_str:
            minutes = int(date_str.split()[0])
            return now_utc - timedelta(minutes=minutes)
        
        # Формат "Yesterday"
        elif 'yesterday' in date_str.lower():
            return now_utc - timedelta(days=1)
        
        # Формат "Month Day, Year" (наприклад, "May 30, 2025")
        else:
            from datetime import datetime as dt
            try:
                return dt.strptime(date_str, "%B %d, %Y").replace(tzinfo=timezone.utc)
            except ValueError:
                pass
            
            # Формат "YYYY-MM-DD HH:MM:SS"
            try:
                return dt.strptime(date_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            except ValueError:
                pass
            
            # Якщо нічого не підійшло, вважаємо новину свіжою (остання година)
            return now_utc - timedelta(hours=1)
            
    except Exception as e:
        logger.warning(f"Не вдалося розпарсити дату '{date_str}': {e}")
        return datetime.now(timezone.utc) - timedelta(hours=8)

# Додаткова функція для сумісності з існуючим кодом
def fetch_news_for_company_legacy(company: str) -> List[Dict[str, str]]:
    """
    Застаріла функція для сумісності зі старим кодом.
    Просто викликає нову версію з параметром prefer_ukrainian=True
    """
    return fetch_news_for_company(company, prefer_ukrainian=True)