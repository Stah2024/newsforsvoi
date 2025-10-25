import os
import re
import json
import hashlib
import pytz
import telebot
from datetime import datetime

# Настройки
TOKEN = os.getenv("TELEGRAM_HISTORY_TOKEN")
CHANNEL_ID = "@historySvoih"
SEEN_IDS_FILE = "seen_ids1.txt"  # Изменено на seen_ids1.txt
HISTORY_FILE = "public/history.html"
moscow = pytz.timezone("Europe/Moscow")

# Инициализация бота
bot = telebot.TeleBot(TOKEN)

# Чтение обработанных ID
def load_seen_ids():
    if os.path.exists(SEEN_IDS_FILE):
        with open(SEEN_IDS_FILE, "r", encoding="utf-8") as f:
            return set(line.strip() for line in f)
    return set()

# Сохранение обработанных ID
def save_seen_ids(seen_ids):
    with open(SEEN_IDS_FILE, "w", encoding="utf-8") as f:
        for post_id in seen_ids:
            f.write(f"{post_id}\n")

# Получение медиа
def get_media_url(message):
    if message.photo:
        file_id = message.photo[-1].file_id
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

# Обновление history.html с разметкой
def update_history_html(messages, seen_ids):
    if not os.path.exists(HISTORY_FILE):
        print(f"⚠️ Файл {HISTORY_FILE} не найден")
        return

    with open(HISTORY_FILE, "r", encoding="utf-8") as file:
        html_content = file.read()

    container_start = html_content.find('<div id="history-container" class="news-grid">')
    if container_start == -1:
        print("⚠️ Контейнер #history-container не найден")
        return

    container_end = html_content.find("</div>", container_start)
    if container_end == -1:
        print("⚠️ Контейнер #history-container не закрыт")
        return

    new_items = []

    for msg in messages:
        if str(msg.message_id) in seen_ids:
            print(f"ℹ️ Сообщение {msg.message_id} уже обработано")
            continue

        content = msg.text or msg.caption or "Без текста"
        media_url = get_media_url(msg)
        iso_time = datetime.fromtimestamp(msg.date, moscow).strftime("%Y-%m-%dT%H:%M:%S%z")

        item_html = f'<article class="news-item" itemscope itemtype="https://schema.org/NewsArticle">'
        if media_url:
            if msg.photo:
                item_html += f'<img src="{media_url}" alt="Фото события" class="history-image" itemprop="image" />'
            elif msg.video:
                item_html += f'<a href="{media_url}" class="telegram-video-link" itemprop="video">Смотреть видео</a>'
        item_html += f'<p itemprop="headline">{content}</p>'
        item_html += f'<div class="timestamp" data-ts="{int(msg.date.timestamp() * 1000)}">{(datetime.now(moscow) - msg.date.replace(tzinfo=moscow)).days} дней назад</div>'
        # JSON-LD разметка
        microdata = {
            "@context": "https://schema.org",
            "@type": "NewsArticle",
            "headline": content[:50] + "..." if len(content) > 50 else content,
            "datePublished": iso_time,
            "author": {"@type": "Organization", "name": "Новости для Своих"},
            "publisher": {
                "@type": "Organization",
                "name": "Новости для Своих",
                "logo": {"@type": "ImageObject", "url": "https://newsforsvoi.ru/logo.png"}
            },
            "articleBody": content
        }
        if media_url:
            microdata["image"] = f"https://newsforsvoi.ru{media_url}" if msg.photo else None
        item_html += f'<script type="application/ld+json" itemprop="mainEntityOfPage">{json.dumps(microdata, ensure_ascii=False)}</script>'
        item_html += '</article>'
        new_items.append(item_html)
        seen_ids.add(str(msg.message_id))
        print(f"✅ Обработано сообщение {msg.message_id}: {content[:30]}...")

    if new_items:
        new_container = html_content[:container_start + len('<div id="history-container" class="news-grid">')] + '\n'.join(new_items) + html_content[container_end:]
        with open(HISTORY_FILE, "w", encoding="utf-8") as file:
            file.write(new_container)
        print(f"✅ Обновлён {HISTORY_FILE} с {len(new_items)} новыми элементами")
    else:
        print("⚠️ Нет новых элементов для добавления в history.html")

    save_seen_ids(seen_ids)

# Получение обновлений
def check_updates():
    seen_ids = load_seen_ids()
    offset = 0
    messages = []
    while True:
        updates = bot.get_updates(offset=offset, timeout=30)
        if not updates:
            break
        for update in updates:
            if update.message and update.message.chat.username == CHANNEL_ID.replace("@", ""):
                messages.append(update.message)
            offset = update.update_id + 1
    return messages

# Основной цикл
def main():
    try:
        print("Запуск проверки обновлений из @historySvoih...")
        messages = check_updates()
        print(f"Найдено {len(messages)} сообщений для обработки")
        update_history_html(messages, load_seen_ids())
        print("Проверка завершена.")
    except Exception as e:
        print(f"Ошибка: {e}")

if __name__ == "__main__":
    main()