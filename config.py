import os
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# ----- Змінні середовища -----
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
COMPANIES_RAW = os.environ.get("COMPANIES", "")
WEBHOOK_PATH = "/webhook"
TRIGGER_SECRET = os.environ.get("TRIGGER_SECRET", "default_secret_change_me")
PORT = int(os.environ.get("PORT", 10000))
BASE_URL = os.environ.get("RENDER_EXTERNAL_URL")

# Перевірка обов'язкових змінних
missing_vars = []
if not TELEGRAM_TOKEN:
    missing_vars.append("TELEGRAM_BOT_TOKEN")
if not CHAT_ID:
    missing_vars.append("TELEGRAM_CHAT_ID")
if not GEMINI_API_KEY:
    missing_vars.append("GEMINI_API_KEY")
if not COMPANIES_RAW:
    missing_vars.append("COMPANIES")
if not BASE_URL:
    missing_vars.append("RENDER_EXTERNAL_URL")

if missing_vars:
    logger.error(f"❌ Не вистачає змінних: {', '.join(missing_vars)}")
    exit(1)

COMPANIES = [c.strip() for c in COMPANIES_RAW.split(",") if c.strip()]
WEBHOOK_URL = f"{BASE_URL}{WEBHOOK_PATH}"

logger.info(f"📋 Компанії: {COMPANIES}")
logger.info(f"🔗 Webhook URL: {WEBHOOK_URL}")