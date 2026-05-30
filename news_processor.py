from typing import List, Dict
from google import genai
from config import logger, GEMINI_API_KEY

def make_fallback_digest(news_list: List[Dict[str, str]]) -> str:
    grouped = {}
    for item in news_list:
        grouped.setdefault(item["company"], []).append(item)
    result = "⚠️ *Автоматичний дайджест (без ШІ)*\n\n"
    for company, items in grouped.items():
        result += f"*{company}*:\n"
        for i, news in enumerate(items[:5], 1):
            result += f"{i}. [{news['title']}]({news['link']})\n"
        result += "\n"
    return result

def generate_digest(news_list: List[Dict[str, str]]) -> str:
    if not news_list:
        return "ℹ️ За останні 8 годин нових новин не виявлено."

    news_text = "\n".join(
        f"**{item['company']}** – {item['title']} ({item['published']})\n{item['link']}"
        for item in news_list[:30]
    )
    prompt = f"""
Ти асистент інвестора. Зроби короткий дайджест новин за останні 8 годин українською мовою.
Новини:
{news_text}
Вимоги: згрупуй по компаніях, обери 2-3 головні новини для кожної, додай посилання, стиль діловий, до 500 слів.
"""
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        models_to_try = ["gemini-1.5-flash", "gemini-2.0-flash-lite", "gemini-2.0-flash"]
        for model_name in models_to_try:
            try:
                response = client.models.generate_content(model=model_name, contents=prompt)
                logger.info(f"✅ Gemini використано модель: {model_name}")
                return response.text
            except Exception as e:
                logger.warning(f"Модель {model_name} не вдалася: {e}")
                continue
        return make_fallback_digest(news_list)
    except Exception as e:
        logger.error(f"Помилка Gemini: {e}")
        return make_fallback_digest(news_list)