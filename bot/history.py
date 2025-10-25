import os
import json
import pytz
import telebot
from datetime import datetime

# Токен и настройки
TOKEN = os.getenv("TELEGRAM_HISTORY_TOKEN")
CHANNEL_ID = "@historySvoih"
SEEN_IDS_FILE = "seen_ids1.txt"
HISTORY_FILE = "public/history.html"
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
    """Форматирует пост в HTML."""
    timestamp = message.date
    iso_time = datetime.fromtimestamp(timestamp, moscow).strftime("%Y-%m-%dT%H:%M:%S%z")

    caption = message.caption or ""
    text = message.text or ""
    html = "<article class='news-item'>\n"
    file_url = None

    # Обработка фото
    if message.content_type == "photo":
        photos = message.photo
        file_info = bot.get_file(photos[-1].file_id)
        file_url = f"https://api.telegram.org/file/bot{TOKEN}/{file_info.file_path}"
        html += f"<img src='{file_url}' alt='Фото события' class='history-image' />\n"

    # Обработка видео
    elif message.content_type == "video":
        try:
            size = getattr(message.video, "file_size", 0)
            if size <= 20_000_000:
                file_info = bot.get_file(message.video.file_id)
                file_url = f"https://api.telegram.org/file/bot{TOKEN}/{file_info.file_path}"
                html += f"<video controls src='{file_url}'></video>\n"
            else:
                print(f"⛔️ Пропущено видео >20MB: {size}")
                return ""
        except Exception as e:
            print(f"⚠️ Ошибка при видео: {e}")
            return ""

    # Добавляем текст
    if caption:
        html += f"<p><b>{caption}</b></p>\n"
    if text and text != caption:
        html += f"<p>{text}</p>\n"

    html += f"<a href='https://t.me/{CHANNEL_ID[1:]}/{message.message_id}' target='_blank'>Читать в Telegram</a>\n"
    html += f"<div class='timestamp'>{iso_time}</div>\n"
    html += "</article>\n"
    return html

def append_to_history(html):
    """Добавляет пост в начало history.html."""
    os.makedirs("public", exist_ok=True)

    if not os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            f.write("<html><body>\n")

    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        old = f.read()

    new_html = html + "\n" + old
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        f.write(new_html)

# === Основная логика ===

@bot.channel_post_handler(func=lambda m: True)
def handle_channel_post(message):
    """Обрабатывает новые посты из канала."""
    if message.chat.username != CHANNEL_ID[1:]:
        return

    seen_ids = load_seen_ids()
    if message.message_id in seen_ids:
        return  # уже обработано

    html = format_post(message)
    if html:
        append_to_history(html)
        seen_ids.add(message.message_id)
        save_seen_ids(seen_ids)
        print(f"✅ Добавлен пост {message.message_id}")

print("🤖 Бот слушает канал...")
bot.polling(none_stop=True, timeout=60)