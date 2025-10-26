import os
import json
import pytz
import telebot
from datetime import datetime
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET

# Токен и настройки
TOKEN = os.getenv("TELEGRAM_HISTORY_TOKEN")
CHANNEL_ID = "@historySvoih"
SEEN_IDS_FILE = "seen_ids1.txt"
HISTORY_FILE = "public/history.html"
SITEMAP_FILE = "public/sitemap.xml"
moscow = pytz.timezone("Europe/Moscow")

bot = telebot.TeleBot(TOKEN)

# === Вспомогательные функции ===

def load_seen_ids():
    """Загружает ID уже обработанных сообщений."""
    if os.path.exists(SEEN_IDS_FILE):
        with open(SEEN_IDS_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    return set()

def save_seen_ids(ids):
    """Сохраняет список обработанных сообщений."""
    with open(SEEN_IDS_FILE, "w", encoding="utf-8") as f:
        json.dump(list(ids), f)

def format_post(message):
    """Форматирует пост в HTML и возвращает данные для JSON-LD."""
    timestamp = message.date
    iso_time = datetime.fromtimestamp(timestamp, moscow).strftime("%Y-%m-%dT%H:%M:%S+03:00")
    caption = message.caption or ""
    text = message.text or ""
    html = "<article class='news-item'>\n"
    json_ld_article = {
        "@type": "Article",
        "headline": caption[:200] or text[:200] or "Историческое событие",
        "description": text[:500] or caption[:500] or "",
        "datePublished": iso_time,
        "author": {
            "@type": "Organization",
            "name": "SVOih History Team"
        },
        "url": f"https://t.me/{CHANNEL_ID[1:]}/{message.message_id}"
    }
    file_url = None

    if message.content_type == "photo":
        photos = message.photo
        file_info = bot.get_file(photos[-1].file_id)
        file_url = f"https://api.telegram.org/file/bot{TOKEN}/{file_info.file_path}"
        html += f"<img src='{file_url}' alt='Фото события' class='history-image' />\n"
        json_ld_article["image"] = {
            "@type": "ImageObject",
            "url": file_url,
            "width": photos[-1].width,
            "height": photos[-1].height
        }
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
                print(f"⛔️ Пропущено видео >20MB: {size}")
                return "", None
        except Exception as e:
            print(f"⚠️ Ошибка при видео: {e}")
            return "", None

    if caption:
        html += f"<p><b>{caption}</b></p>\n"
    if text and text != caption:
        html += f"<p>{text}</p>\n"

    html += f"<a href='https://t.me/{CHANNEL_ID[1:]}/{message.message_id}' target='_blank'>Читать в Telegram</a>\n"
    html += f"<div class='timestamp'>{iso_time}</div>\n"
    html += "</article>\n"
    return html, json_ld_article

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
        print(f"✅ Обновлён sitemap.xml для history.html: {now}")
    except FileNotFoundError:
        print(f"⚠️ Файл {SITEMAP_FILE} не найден. Убедитесь, что bot.py создал sitemap.xml.")
    except Exception as e:
        print(f"⚠️ Ошибка при обновлении sitemap.xml: {e}")

def update_history_html(html, json_ld_article):
    """Добавляет пост и обновляет JSON-LD в history.html."""
    os.makedirs("public", exist_ok=True)

    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            soup = BeautifulSoup(f, "html.parser")
    else:
        soup = BeautifulSoup(open("history.html").read(), "html.parser")

    history_container = soup.find("div", id="history-container")
    if history_container:
        new_article = BeautifulSoup(html, "html.parser")
        history_container.insert(0, new_article)

    schema_script = soup.find("script", id="schema-org")
    if schema_script and json_ld_article:
        schema_data = json.loads(schema_script.string)
        schema_data["mainEntity"]["itemListElement"].insert(0, {
            "@type": "ListItem",
            "position": len(schema_data["mainEntity"]["itemListElement"]) + 1,
            "item": json_ld_article
        })
        schema_script.string = json.dumps(schema_data, ensure_ascii=False, indent=2)

    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        f.write(str(soup))

    # Обновляем sitemap.xml только для history.html
    if os.path.exists(SITEMAP_FILE):
        update_sitemap()

# === Основная логика ===

@bot.channel_post_handler(func=lambda m: True)
def handle_channel_post(message):
    """Обрабатывает новые посты из канала."""
    if message.chat.username != CHANNEL_ID[1:]:
        return

    seen_ids = load_seen_ids()
    if message.message_id in seen_ids:
        return

    html, json_ld_article = format_post(message)
    if html and json_ld_article:
        update_history_html(html, json_ld_article)
        seen_ids.add(message.message_id)
        save_seen_ids(seen_ids)
        print(f"✅ Добавлен пост {message.message_id}")

print("🤖 Бот слушает канал...")
bot.polling(none_stop=True, timeout=60)