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
SEEN_IDS_FILE = "seen_ids1.txt"  # В корне проекта
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
    """Загружает ID уже обработанных сообщений."""
    logging.info(f"Попытка загрузки {SEEN_IDS_FILE}")
    if not os.path.exists(SEEN_IDS_FILE):
        logging.info(f"Файл {SEEN_IDS_FILE} не существует, создаём пустой список")
        with open(SEEN_IDS_FILE, "w", encoding="utf-8") as f:
            json.dump([], f)
        return set()
    
    try:
        with open(SEEN_IDS_FILE, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                logging.info(f"Файл {SEEN_IDS_FILE} пуст, возвращаем пустой список")
                return set()
            return set(json.loads(content))
    except json.JSONDecodeError as e:
        logging.error(f"Ошибка JSON в {SEEN_IDS_FILE}: {e}. Сбрасываем файл")
        with open(SEEN_IDS_FILE, "w", encoding="utf-8") as f:
            json.dump([], f)
        return set()
    except Exception as e:
        logging.error(f"Ошибка чтения {SEEN_IDS_FILE}: {e}")
        return set()

def save_seen_ids(ids):
    """Сохраняет список обработанных сообщений."""
    try:
        with open(SEEN_IDS_FILE, "w", encoding="utf-8") as f:
            json.dump(list(ids), f)
        logging.info(f"Сохранено {len(ids)} ID в {SEEN_IDS_FILE}")
    except Exception as e:
        logging.error(f"Ошибка записи в {SEEN_IDS_FILE}: {e}")

def clean_text(text):
    """Очищает текст от нежелательных фраз."""
    if not text:
        return ""
    unwanted = ["Подписаться на историю для своих", "https://t.me/historySvoih"]
    for phrase in unwanted:
        text = text.replace(phrase, "")
    return text.strip()

def format_post(message):
    """Форматирует пост в HTML и возвращает данные для JSON-LD и RSS."""
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
        "author": {
            "@type": "Organization",
            "name": "SVOih History Team"
        },
        "publisher": {
            "@type": "Organization",
            "name": "Новости для Своих",
            "logo": {"@type": "ImageObject", "url": "https://newsforsvoi.ru/logo.png"}
        },
        "url": f"https://t.me/{CHANNEL_ID[1:]}/{message.message_id}"
    }
    file_url = None

    if message.content_type == "photo":
        photos = message.photo
        try:
            file_info = bot.get_file(photos[-1].file_id)
            file_url = f"https://api.telegram.org/file/bot{TOKEN}/{file_info.file_path}"
            html += f"<img src='{file_url}' alt='Фото события' class='history-image' />\n"
            json_ld_article["image"] = {
                "@type": "ImageObject",
                "url": file_url,
                "width": photos[-1].width,
                "height": photos[-1].height
            }
        except Exception as e:
            logging.error(f"Ошибка при обработке фото для поста {message.message_id}: {e}")
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
                logging.warning(f"Пропущено видео >20MB для поста {message.message_id}: {size}")
                return "", None
        except Exception as e:
            logging.error(f"Ошибка при обработке видео для поста {message.message_id}: {e}")
            return "", None

    if caption:
        html += f"<p><b>{caption}</b></p>\n"
    if text and text != caption:
        html += f"<p>{text}</p>\n"

    html += f"<a href='https://t.me/{CHANNEL_ID[1:]}/{message.message_id}' target='_blank'>Читать в Telegram</a>\n"
    html += f"<div class='timestamp' data-ts='{iso_time}'>🕒 {formatted_time}</div>\n"
    html += "</article>\n"
    return html, json_ld_article

def fetch_latest_posts():
    """Загружает последние посты из канала при запуске бота."""
    try:
        updates = bot.get_updates()
        posts = [
            u.channel_post
            for u in updates
            if u.channel_post and u.channel_post.chat.username == CHANNEL_ID[1:]
        ]
        logging.info(f"Загружено {len(posts)} постов из канала {CHANNEL_ID}")
        return list(reversed(posts[-12:])) if posts else []
    except Exception as e:
        logging.error(f"Ошибка при загрузке постов: {e}")
        return []

def update_sitemap():
    """Обновляет <lastmod> для history.html в sitemap.xml."""
    now = datetime.now(moscow).strftime("%Y-%m-%dT%H:%M:%S+03:00")
    try:
        tree = ET.parse(SITEMAP_FILE)
        root = tree.getroot()
        for url in root.findall("{http://www.sitemaps.org/schemas/sitemap/0.9}url"):
            loc = url.find("{http://www.sitemaps.org/schemas/sitemap/0.9}loc")
            if loc.text == "https://newsforsvoi.ru/history.html":
                lastmod = url.find("{http://www.sitemaps.org/schemas/sitemap/0.9}lastmod")
                lastmod.text = now
                break
        tree.write(SITEMAP_FILE, encoding="utf-8", xml_declaration=True)
        logging.info(f"Обновлён sitemap.xml для history.html: {now}")
    except FileNotFoundError:
        logging.error(f"Файл {SITEMAP_FILE} не найден. Убедитесь, что bot.py создал sitemap.xml.")
    except Exception as e:
        logging.error(f"Ошибка при обновлении sitemap.xml: {e}")

def generate_rss(posts):
    """Генерирует RSS для history.html."""
    rss_items = ""
    for html_block, json_ld in posts:
        title_match = re.search(r"<p><b>(.*?)</b></p>", html_block) or re.search(r"<p>(.*?)</p>", html_block)
        link_match = re.search(r"<a href='(https://t\.me/[^']+)'", html_block)
        date_match = re.search(r"data-ts='([^']+)'", html_block)

        title = title_match.group(1) if title_match else json_ld["headline"]
        link = link_match.group(1) if link_match else f"https://t.me/{CHANNEL_ID[1:]}"
        pub_date = (
            datetime.strptime(date_match.group(1), "%Y-%m-%dT%H:%M:%S+03:00").strftime("%a, %d %b %Y %H:%M:%S +0300")
            if date_match
            else datetime.now(moscow).strftime("%a, %d %b %Y %H:%M:%S +0300")
        )

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
    try:
        os.makedirs(os.path.dirname(RSS_FILE), exist_ok=True)
        with open(RSS_FILE, "w", encoding="utf-8") as f:
            f.write(rss)
        logging.info("history_rss.xml обновлён")
    except Exception as e:
        logging.error(f"Ошибка при записи history_rss.xml: {e}")

def update_history_html(html, json_ld_article):
    """Добавляет пост и обновляет JSON-LD в history.html."""
    os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)

    try:
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                soup = BeautifulSoup(f, "html.parser")
        else:
            logging.warning(f"Файл {HISTORY_FILE} не найден, используется шаблон history.html")
            with open("history.html", "r", encoding="utf-8") as f:
                soup = BeautifulSoup(f, "html.parser")
    except FileNotFoundError:
        logging.error(f"Файл history.html не найден, создайте шаблон в корне проекта")
        return
    except Exception as e:
        logging.error(f"Ошибка при чтении history.html: {e}")
        return

    history_container = soup.find("div", id="history-container")
    if history_container:
        new_article = BeautifulSoup(html, "html.parser")
        history_container.insert(0, new_article)
    else:
        logging.error("Контейнер #history-container не найден в history.html")
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
            logging.error(f"Ошибка при обновлении JSON-LD: {e}")

    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            f.write(str(soup))
        logging.info(f"Обновлён {HISTORY_FILE}")
    except Exception as e:
        logging.error(f"Ошибка при записи {HISTORY_FILE}: {e}")

    if os.path.exists(SITEMAP_FILE):
        update_sitemap()

# === Основная логика ===

def process_initial_posts():
    """Обрабатывает последние посты при запуске бота."""
    posts = fetch_latest_posts()
    seen_ids = load_seen_ids()
    new_posts = []

    for post in posts:
        if post.message_id in seen_ids:
            logging.info(f"Пропущен пост {post.message_id}: уже обработан")
            continue

        html, json_ld_article = format_post(post)
        if html and json_ld_article:
            update_history_html(html, json_ld_article)
            new_posts.append((html, json_ld_article))
            seen_ids.add(post.message_id)
            logging.info(f"Добавлен начальный пост {post.message_id}")
        else:
            logging.warning(f"Не удалось обработать пост {post.message_id}")

    if new_posts:
        save_seen_ids(seen_ids)
        generate_rss(new_posts)
        logging.info(f"Обработано {len(new_posts)} начальных постов")
    else:
        logging.info("Новых постов для обработки при запуске нет")

def handle_channel_post(message):
    """Обрабатывает новые посты из канала в реальном времени."""
    if message.chat.username != CHANNEL_ID[1:]:
        logging.warning(f"Получен пост из другого канала: {message.chat.username}")
        return

    seen_ids = load_seen_ids()
    if message.message_id in seen_ids:
        logging.info(f"Пропущен пост {message.message_id}: уже обработан")
        return

    html, json_ld_article = format_post(message)
    if html and json_ld_article:
        update_history_html(html, json_ld_article)
        seen_ids.add(message.message_id)
        save_seen_ids(seen_ids)
        generate_rss([(html, json_ld_article)])
        logging.info(f"Добавлен пост {message.message_id}")
    else:
        logging.warning(f"Не удалось обработать пост {message.message_id}")

if __name__ == "__main__":
    logging.info("Запуск бота для канала @historySvoih")
    process_initial_posts()
    logging.info("Завершение работы после обработки начальных постов")