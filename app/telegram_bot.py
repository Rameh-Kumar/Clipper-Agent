"""
Telegram Bot Handler
====================
Parses incoming Telegram webhook updates and sends messages back.
"""

import re
import os
import requests

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

# YouTube URL patterns
YT_PATTERN = re.compile(
    r'(https?://)?(www\.)?(youtube\.com/watch\?v=|youtu\.be/|youtube\.com/shorts/)[\w\-]+'
)

# Language override pattern (e.g., "lang:en" or "lang:hi")
LANG_PATTERN = re.compile(r'lang:(\w{2,5})', re.IGNORECASE)


def parse_update(body: dict) -> dict:
    """Extract useful info from a Telegram webhook update."""
    message = body.get("message", {})
    text = message.get("text", "").strip()
    chat_id = message.get("chat", {}).get("id")
    user = message.get("from", {}).get("first_name", "User")

    # Check for YouTube URL
    yt_match = YT_PATTERN.search(text)
    youtube_url = yt_match.group(0) if yt_match else None

    # Check for language override (e.g., "lang:en")
    lang_match = LANG_PATTERN.search(text)
    lang = lang_match.group(1).lower() if lang_match else ""

    # Check for commands
    is_done_reviewing = text.lower() in ["done reviewing", "done", "/done"]
    is_status = text.lower() in ["/status", "status"]
    is_help = text.lower() in ["/help", "help", "/start", "hi", "hello"]

    return {
        "chat_id": chat_id,
        "text": text,
        "user": user,
        "youtube_url": youtube_url,
        "lang": lang,
        "is_done_reviewing": is_done_reviewing,
        "is_status": is_status,
        "is_help": is_help,
    }


def send_message(chat_id: int, text: str) -> dict:
    """Send a message to a Telegram chat."""
    url = f"{TELEGRAM_API}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }
    response = requests.post(url, json=payload)
    return response.json()


def register_webhook(webhook_url: str) -> dict:
    """Register a webhook URL with Telegram."""
    url = f"{TELEGRAM_API}/setWebhook"
    payload = {"url": webhook_url}
    response = requests.post(url, json=payload)
    return response.json()


def get_webhook_info() -> dict:
    """Get current webhook info from Telegram."""
    url = f"{TELEGRAM_API}/getWebhookInfo"
    response = requests.get(url)
    return response.json()
