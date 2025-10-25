import os
import re
import json
import hashlib
import pytz
import telebot
from datetime import datetime, timedelta

# Настройки
TOKEN = os.getenv("TELEGRAM_HISTORY_TOKEN")
CHANNEL_ID = "@historySvoih"
SEEN_IDS_FILE = "seen_ids.txt"
HISTORY_FILE = "public/history.html"
moscow = pytz.timezone("Europe/Moscow")

# Инициализация бота
bot = telebot.TeleBot(TOKEN)

# Чтение обработанных ID
def load_seen_ids():
    if os.path.exists(SEEN_IDS_FILE):
        with open(SEEN_IDS_FILE, "r") as f:
            return set(json.load(f))
    return set()

# Сохранение обработанных ID
def save_seen_ids(seen_ids):
    with open(SEEN_IDS_FILE, "w") as f:
        json.dump(list(seen_ids), f)

# Парсинг даты и текста
def parse_message_content(message_text):
    if not message_text:
        return None, None, None
    date_match = re.search(r'(\d{2}\.\d{2}\.\d{4}): (.+)', message_text)
    if not date_match:
        return None, None, None
    event_date_str, content = date_match.groups()
    event_date = datetime.strptime(event_date_str, '%d.%m.%Y').replace(tzinfo=moscow).date()
    return event_date, event_date_str, content

# Получение медиа
def get_media_url(message):
    if message.photo:
        file_id = message.photo[-1].file_id  # Берем самую большую версию
        file = bot.get_file(file_id)
        file_path = file.file_path
        downloaded_file = bot.download_file(file_path)
        media_dir = "public/media"
        os.makedirs(media_dir, exist_ok=True)
        file_name = f"photo_{hashlib.md5(file_id.encode()).hexdigest()}.jpg"
        with open(os.path.join(media_dir, file_name), "wb") as new_file:
            new_file.write(downloaded_file)
        return f"/media/{file_name}"
    elif message.video:
        file_id = message.video.file_id
        file = bot.get_file(file_id)
        file_path = file.file_path
        downloaded_file = bot.download_file(file_path)
        media_dir = "public/media"
        os.makedirs(media_dir, exist_ok=True)
        file_name = f"video_{hashlib.md5(file_id.encode()).hexdigest()}.mp4"
        with open(os.path.join(media_dir, file_name), "wb") as new_file:
            new_file.write(downloaded_file)
        return f"/media/{file_name}"
    return None

# Обновление history.html
def update_history_html(messages, seen_ids):
    if not os.path.exists(HISTORY_FILE):
        return

    with open(HISTORY_FILE, "r", encoding="utf-8") as file:
        html_content = file.read()

    container_start = html_content.find('<div id="history-container" class="news-grid">')
    if container_start == -1:
        return

    container_end = html_content.find("</div>", container_start)
    if container_end == -1:
        return

    container_content = html_content[container_start:container_end]
    new_items = []

    target_date = datetime.now(moscow) - timedelta(days=10)
    for msg in messages:
        if msg.message_id in seen_ids:
            continue
        if msg.date.replace(tzinfo=moscow) < target_date:
            continue

        event_date, event_date_str, content = parse_message_content(msg.text)
        if not event_date:
            continue

        media_url = get_media_url(msg)
        item_html = f'<article class="news-item">'
        if media_url:
            if msg.photo:
                item_html += f'<img src="{media_url}" alt="Фото события" class="history-image" />'
            elif msg.video:
                item_html += f'<a href="{media_url}" class="telegram-video-link">Смотреть видео</a>'
        item_html += f'<p>{event_date_str}: {content}</p>'
        item_html += f'<div class="timestamp" data-ts="{int(msg.date.timestamp() * 1000)}">{(datetime.now(moscow) - msg.date.replace(tzinfo=moscow)).days} дней назад</div>'
        item_html += '</article>'
        new_items.append(item_html)
        seen_ids.add(msg.message_id)

    if new_items:
        new_container = html_content[:container_start + len('<div id="history-container" class="news-grid">')] + '\n'.join(new_items) + html_content[container_end:]
        with open(HISTORY_FILE, "w", encoding="utf-8") as file:
            file.write(new_container)
        save_seen_ids(seen_ids)

# Получение обновлений
def check_updates():
    seen_ids = load_seen_ids()
    offset = 0
    while True:
        updates = bot.get_updates(offset=offset, timeout=30)
        for update in updates:
            if update.message and update.message.chat.username == CHANNEL_ID.replace("@", ""):
                update_history_html([update.message], seen_ids)
            offset = update.update_id + 1
        if not updates:
            break

# Основной цикл
def main():
    try:
        print("Запуск проверки обновлений из @historySvoih...")
        check_updates()
        print("Проверка завершена.")
    except Exception as e:
        print(f"Ошибка: {e}")

if __name__ == "__main__":
    main()