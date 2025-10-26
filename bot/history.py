import os
import json
import pytz
import telebot
import logging
from datetime import datetime
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
import re
import sys

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("history.log"),
        logging.StreamHandler()
    ]
)

# Токен и настройки
TOKEN = os.getenv("TELEGRAM_HISTORY_TOKEN")
CHANNEL_ID = "@historySvoih"
SEEN_IDS_FILE = "seen_ids1.txt"
HISTORY_FILE = "public/history.html"
SITEMAP_FILE = "public/sitemap.xml"
RSS_FILE = "public/history_rss.xml"
moscow = pytz.timezone("Europe/Moscow")

# Проверка токена
if not TOKEN:
    logging.error("TELEGRAM_HISTORY_TOKEN не найден в переменных окружения")
    sys.exit(1)

bot = telebot.TeleBot(TOKEN)

# Проверка доступа бота
try:
    bot.get_me()
    logging.info("Бот успешно авторизован")
except Exception as e:
    logging.error(f"Ошибка авторизации бота: {e}")
    sys.exit(1)

# === Вспомогательные функции ===

def load_seen_ids():
    if not os.path.exists(SEEN_IDS_FILE):
        with open(SEEN_IDS_FILE, "w", encoding="utf-8") as f:
            json.dump([], f)
        return set()
    try:
        with open(SEEN_IDS_FILE, "r", encoding="utf-8") as f:
            content = f.read().strip()
            return set(json.loads(content)) if content else set()
    except Exception as e:
        logging.error(f"Ошибка чтения {SEEN_IDS_FILE}: {e}")
        return set()

def save_seen_ids(ids):
    try:
        with open(SEEN_IDS_FILE, "w", encoding="utf-8") as f:
            json.dump(list(ids), f)
    except Exception as e:
        logging.error(f"Ошибка записи в {SEEN_IDS_FILE}: {e}")

def clean_text(text):
    if not text:
        return ""
    unwanted = ["Подписаться на историю для своих", "https://t.me/historySvoih"]
    for phrase in unwanted:
        text = text.replace(phrase, "")
    return text.strip()

def format_post(message):
    timestamp = message.date
    iso_time = datetime.fromtimestamp(timestamp, moscow).strftime("%Y-%m-%dT%H:%M:%S+03:00")
    formatted_time = datetime.fromtimestamp(timestamp, moscow).strftime("%d.%m.%Y %H:%M")
    caption = clean_text(message.caption or "")
    text = clean_text(message.text or "")
    html = "<article class='news-item'>\n"
    json_ld_article = {
        "@type": "NewsArticle",
        "headline": caption[:200] or text[:200] or "Историческое событие",
        "description": text[:500] or caption[:500] or "",
        "datePublished": iso_time,
        "author": {"@type": "Organization", "name": "SVOih History Team"},
        "publisher": {
            "@type": "Organization",
            "name": "Новости для Своих",
            "logo": {"@type": "ImageObject", "url": "https://newsforsvoi.ru/logo.png"}
        },
        "url": f"https://t.me/{CHANNEL_ID[1:]}/{message.message_id}"
    }
    file_url = None

    if message.content_type == "photo":
        try:
            file_info = bot.get_file(message.photo[-1].file_id)
            file_url = f"https://api.telegram.org/file/bot{TOKEN}/{file_info.file_path}"
            html += f"<img src='{file_url}' alt='Фото события' class='history-image' />\n"
            json_ld_article["image"] = {
                "@type": "ImageObject",
                "url": file_url,
                "width": message.photo[-1].width,
                "height": message.photo[-1].height
            }
        except Exception as e:
            logging.error(f"Ошибка фото {message.message_id}: {e}")
            return "", None

    elif message.content_type == "video":
        try:
            size = getattr(message.video, "file_size", 0)
            if size <= 20_000_000:
                file_info = bot.get_file(message.video.file_id)
                file_url = f"https://api.telegram.org/file/bot{TOKEN}/{file_info.file_path}"
                html += f"<video controls src='{file_url}'></video>\n"
                json_ld_article["video"] = {
                    "@type": "VideoObject",
                    "contentUrl": file_url,
                    "uploadDate": iso_time
                }
            else:
                logging.warning(f"Пропущено видео >20MB: {size}")
                return "", None
        except Exception as e:
            logging.error(f"Ошибка видео {message.message_id}: {e}")
            return "", None

    if caption:
        html += f"<p><b>{caption}</b></p>\n"
    if text and text != caption:
        html += f"<p>{text}</p>\n"

    html += f"<a href='https://t.me/{CHANNEL_ID[1:]}/{message.message_id}' target='_blank'>Читать в Telegram</a>\n"
    html += f"<div class='timestamp' data-ts='{iso_time}'>🕒 {formatted_time}</div>\n"
    html += "</article>\n"
    return html, json_ld_article
def update_history_html(html, json_ld_article):
    os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
    try:
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                soup = BeautifulSoup(f, "html.parser")
        else:
            with open("history.html", "r", encoding="utf-8") as f:
                soup = BeautifulSoup(f, "html.parser")
    except Exception as e:
        logging.error(f"Ошибка чтения history.html: {e}")
        return

    container = soup.find("div", id="history-container")
    if container:
        container.insert(0, BeautifulSoup(html, "html.parser"))
    else:
        logging.error("Контейнер #history-container не найден")
        return

    schema_script = soup.find("script", id="schema-org")
    if schema_script and json_ld_article:
        try:
            schema_data = json.loads(schema_script.string)
            schema_data["mainEntity"]["itemListElement"].insert(0, {
                "@type": "ListItem",
                "position": len(schema_data["mainEntity"]["itemListElement"]) + 1,
                "item": json_ld_article
            })
            schema_script.string = json.dumps(schema_data, ensure_ascii=False, indent=2)
        except Exception as e:
            logging.error(f"Ошибка JSON-LD: {e}")

    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            f.write(str(soup))
    except Exception as e:
        logging.error(f"Ошибка записи history.html: {e}")

def handle_channel_post(message):
    if message.chat.username != CHANNEL_ID[1:]:
        return
    seen_ids = load_seen_ids()
    if message.message_id in seen_ids:
        return
    html, json_ld = format_post(message)
    if html and json_ld:
        update_history_html(html, json_ld)
        seen_ids.add(message.message_id)
        save_seen_ids(seen_ids)
        logging.info(f"Добавлен пост {message.message_id}")

@bot.channel_post_handler(func=lambda m: True)
def channel_listener(message):
    handle_channel_post(message)

if __name__ == "__main__":
    logging.info("Запуск бота @historySvoih")
    bot.polling(none_stop=True)