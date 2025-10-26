import os
import json
import pytz
import telebot
import logging
from datetime import datetime
from bs4 import BeautifulSoup
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
RSS_FILE = "public/history_rss.xml"
moscow = pytz.timezone("Europe/Moscow")

if not TOKEN:
    logging.error("TELEGRAM_HISTORY_TOKEN не найден в переменных окружения")
    sys.exit(1)

bot = telebot.TeleBot(TOKEN)

try:
    bot.get_me()
    logging.info("Бот успешно авторизован")
except Exception as e:
    logging.error(f"Ошибка авторизации бота: {e}")
    sys.exit(1)

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
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
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

def generate_rss(posts):
    if not posts:
        logging.info("Создаём пустой RSS — новых постов нет")
    rss_items = ""
    for _, json_ld in posts:
        title = json_ld["headline"]
        link = json_ld["url"]
        pub_date = json_ld["datePublished"].replace("T", " ").replace("+03:00", " +0300")
        rss_items += f"""
<item>
  <title>{title}</title>
  <link>{link}</link>
  <description>{json_ld["description"]}</description>
  <pubDate>{pub_date}</pubDate>
</item>
"""
    rss = f"""<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0">
  <channel>
    <title>История для Своих</title>
    <link>https://newsforsvoi.ru/history.html</link>
    <description>Исторические события из Telegram-канала История для Своих</description>
    {rss_items}
  </channel>
</rss>
"""
    os.makedirs(os.path.dirname(RSS_FILE), exist_ok=True)
    with open(RSS_FILE, "w", encoding="utf-8") as f:
        f.write(rss)
    logging.info(f"RSS записан в: {RSS_FILE}")

def process_initial_posts():
    try:
        bot.delete_webhook(drop_pending_updates=True)
        updates = bot.get_updates(timeout=30, limit=100)  # Добавлен тайма26        logging.info(f"Получено {len(updates)} обновлений")
        posts = [
            u.channel_post
            for u in updates
            if u.channel_post and u.channel_post.chat.username == CHANNEL_ID[1:]
        ]
        logging.info(f"Загружено {len(posts)} постов из канала @{CHANNEL_ID[1:]}")
        for post in posts:
            logging.info(f"Пост ID: {post.message_id}, Дата: {post.date}")
    except Exception as e:
        logging.error(f"Ошибка получения обновлений: {e}")
        generate_rss([])
        posts = []

    seen_ids = load_seen_ids()
    new_posts = []

    for post in posts:
        if post.message_id in seen_ids:
            continue
        html, json_ld = format_post(post)
        if html and json_ld:
            update_history_html(html, json_ld)
            seen_ids.add(post.message_id)
            new_posts.append((html, json_ld))

    if new_posts:
        generate_rss(new_posts)
        logging.info(f"Обработано {len(new_posts)} новых постов")
    else:
        logging.info("Новых постов не найдено, создаём пустой RSS")
        generate_rss([])

    save_seen_ids(seen_ids)

if __name__ == "__main__":
    logging.info("Запуск однократной обработки постов")
    try:
        process_initial_posts()
    except Exception as e:
        logging.error(f"Критическая ошибка: {e}")
        sys.exit(1)