import os
import telebot
from datetime import datetime

# Загружаем токен из переменной окружения (GitHub Secrets)
TOKEN = os.getenv("TELEGRAM_TOKEN")
CHANNEL_ID = "@newsSVOih"
SEEN_IDS_FILE = "seen_ids.txt"

bot = telebot.TeleBot(TOKEN)

# Удаляем ссылку на канал из текста
def clean_text(text):
    return text.replace("https://t.me/newsSVOih", "").strip()

# Загружаем уже обработанные ID
def load_seen_ids():
    if not os.path.exists(SEEN_IDS_FILE):
        return set()
    with open(SEEN_IDS_FILE, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f)

# Сохраняем новые ID
def save_seen_ids(seen_ids):
    with open(SEEN_IDS_FILE, "w", encoding="utf-8") as f:
        for post_id in seen_ids:
            f.write(f"{post_id}\n")

# Получаем последние посты из канала
def fetch_latest_posts():
    updates = bot.get_updates()
    posts = [
        u.channel_post
        for u in updates
        if u.channel_post and u.channel_post.chat.username == CHANNEL_ID[1:]
    ]
    return posts[-10:] if posts else []

# Формируем HTML-карточку поста
def format_post(message):
    html = "<article class='news-item'>\n"

    # Текстовый пост
    if message.content_type == 'text':
        html += f"<p>{clean_text(message.text)}</p>\n"

    # Фото
    elif message.content_type == 'photo':
        photos = message.photo
        file_info = bot.get_file(photos[-1].file_id)
        file_url = f"https://api.telegram.org/file/bot{TOKEN}/{file_info.file_path}"
        caption = clean_text(message.caption or "")
        html += f"<img src='{file_url}' alt='Фото' />\n"
        html += f"<p>{caption}</p>\n"

        # Если фото больше одного — добавляем ссылку
        if len(photos) > 1:
            html += f"<a class='telegram-video-link' href='https://t.me/newsSVOih/{message.message_id}' target='_blank'>🖼 Смотреть остальные фото в Telegram</a>\n"

    # Видео
    elif message.content_type == 'video':
        file_info = bot.get_file(message.video.file_id)
        file_url = f"https://api.telegram.org/file/bot{TOKEN}/{file_info.file_path}"
        caption = clean_text(message.caption or "")
        html += f"<video controls src='{file_url}'></video>\n"
        html += f"<p>{caption}</p>\n"

        # Если в подписи намёк на несколько видео — добавляем ссылку
        if "ещё" in caption.lower() or "другие" in caption.lower():
            html += f"<a class='telegram-video-link' href='https://t.me/newsSVOih/{message.message_id}' target='_blank'>📹 Смотреть другие видео в Telegram</a>\n"

    # Ссылка на Telegram и источник
    html += f"<a href='https://t.me/newsSVOih/{message.message_id}' target='_blank'>Читать в Telegram</a>\n"
    html += f"<p class='source'>Источник: {message.chat.title}</p>\n"
    html += "</article>\n"
    return html

# Основной запуск
def main():
    posts = fetch_latest_posts()
    seen_ids = load_seen_ids()
    new_ids = set()

    os.makedirs("public", exist_ok=True)
    with open("public/news.html", "w", encoding="utf-8") as f:
        if not posts:
            f.write(f"<p>Нет новых постов — {datetime.now()}</p>")
        else:
            for post in posts:
                post_id = str(post.message_id)
                if post_id in seen_ids:
                    continue
                f.write(format_post(post))
                new_ids.add(post_id)

    save_seen_ids(seen_ids.union(new_ids))

# ✅ Запуск
if __name__ == "__main__":
    main()