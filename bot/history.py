import os
import json
import pytz
import telebot
from datetime import datetime

# Настройки
TOKEN = os.getenv("TELEGRAM_HISTORY_TOKEN")
CHANNEL_ID = "@historySvoih"
SEEN_IDS_FILE = "seen_ids1.txt"
HISTORY_FILE = "public/history.html"
moscow = pytz.timezone("Europe/Moscow")

bot = telebot.TeleBot(TOKEN)

def format_post(message, caption_override=None, group_size=1):
    timestamp = message.date
    iso_time = datetime.fromtimestamp(timestamp, moscow).strftime("%Y-%m-%dT%H:%M:%S%z")

    caption = caption_override or message.caption or ""
    text = message.text or ""
    file_url = None
    html = ""

    html += f"<article class='news-item' itemscope itemtype='https://schema.org/NewsArticle'>\n"

    if message.content_type == "photo":
        photos = message.photo
        file_info = bot.get_file(photos[-1].file_id)
        file_url = f"https://api.telegram.org/file/bot{TOKEN}/{file_info.file_path}"
        html += f"<img src='{file_url}' alt='Фото события' class='history-image' itemprop='image' />\n"
    elif message.content_type == "video":
        try:
            size = getattr(message.video, "file_size", 0)
            if size == 0 or size <= 20_000_000:
                file_info = bot.get_file(message.video.file_id)
                file_url = f"https://api.telegram.org/file/bot{TOKEN}/{file_info.file_path}"
                html += f"<video controls src='{file_url}' itemprop='video'></video>\n"
            else:
                print(f"⛔️ Пропущено видео >20MB: {size} байт")
                return ""
        except Exception as e:
            print(f"⚠️ Ошибка при обработке видео: {e}")
            return ""

    if caption:
        html += f"<p itemprop='headline'>{caption}</p>\n"
    if text and text != caption:
        html += f"<p>{text}</p>\n"

    html += f"<div class='timestamp' data-ts='{int(timestamp * 1000)}'>{(datetime.now(moscow) - datetime.fromtimestamp(timestamp, moscow)).days} дней назад</div>\n"
    html += f"<a href='https://t.me/{CHANNEL_ID[1:]}/{message.message_id}' target='_blank'>Читать в Telegram</a>\n"
    html += f"<p class='source'>Источник: {message.chat.title if hasattr(message.chat, 'title') else 'Канал'}</p>\n"

    if group_size > 1:
        html += (
            f"<p><a href='https://t.me/{CHANNEL_ID[1:]}/{message.message_id}' "
            f"target='_blank'>📷 Смотреть остальные фото/видео в Telegram</a></p>\n"
        )

    microdata = {
        "@context": "https://schema.org",
        "@type": "NewsArticle",
        "headline": caption or text or "Новость",
        "datePublished": iso_time,
        "author": {"@type": "Organization", "name": "Новости для Своих"},
        "publisher": {
            "@type": "Organization",
            "name": "Новости для Своих",
            "logo": {"@type": "ImageObject", "url": "https://newsforsvoi.ru/logo.png"}
        },
        "articleBody": (caption + "\n" + text).strip()
    }
    if file_url:
        microdata["image" if message.photo else "video"] = file_url

    html += f"<script type='application/ld+json' itemprop='mainEntityOfPage'>{json.dumps(microdata, ensure_ascii=False)}</script>\n"
    html += "</article>\n"
    return html

def load_seen_ids():
    if not os.path.exists(SEEN_IDS_FILE):
        return set()
    with open(SEEN_IDS_FILE, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f)

def save_seen_ids(seen_ids):
    with open(SEEN_IDS_FILE, "w", encoding="utf-8") as f:
        for post_id in seen_ids:
            f.write(f"{post_id}\n")

def fetch_latest_posts():
    updates = bot.get_updates()
    posts = [
        u.channel_post
        for u in updates
        if u.channel_post and u.channel_post.chat.username == CHANNEL_ID[1:]
    ]
    return list(reversed(posts[-10:])) if posts else []

def main():
    posts = fetch_latest_posts()
    seen_ids = load_seen_ids()
    new_ids = set()

    if not posts:
        print("⚠️ Новых постов нет — выходим")
        return

    os.makedirs("public", exist_ok=True)

    grouped = {}
    for post in posts:
        key = getattr(post, "media_group_id", None) or post.message_id
        grouped.setdefault(str(key), []).append(post)

    fresh_news = []
    for group_id, group_posts in grouped.items():
        post_id = str(group_id)
        first = group_posts[0]
        last = group_posts[-1]

        if post_id in seen_ids or post_id in new_ids:
            continue

        html = format_post(last, caption_override=first.caption, group_size=len(group_posts))
        if not html:
            continue

        fresh_news.append(html)
        new_ids.add(post_id)

    if not fresh_news:
        print("⚠️ Новых карточек нет — history.html не изменен")
        return

    if not os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            f.write("""
<!DOCTYPE html>
<html>
<head>
    <title>История - Новости для Своих</title>
    <meta charset="UTF-8">
    <style>
        body { font-family: sans-serif; line-height: 1.6; padding: 10px; background: #f9f9f9; }
        .news-item { margin-bottom: 30px; padding: 15px; background: #fff; border-radius: 8px; box-shadow: 0 0 5px rgba(0,0,0,0.05); border-left: 4px solid #0077cc; }
        .news-item img, .news-item video { max-width: 100%; margin: 10px 0; border-radius: 4px; }
        .timestamp { font-size: 0.9em; color: #666; margin-top: 10px; }
        .source { font-size: 0.85em; color: #999; }
    </style>
</head>
<body>
    <div id="history-container" class="news-grid">
</div>
</body>
</html>
""")

    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        existing_html = f.read()

    new_html = "\n".join(fresh_news) + "\n" + existing_html

    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        f.write(new_html)

    save_seen_ids(seen_ids.union(new_ids))
    print(f"✅ history.html обновлен, добавлено новых карточек: {len(new_ids)}")

if __name__ == "__main__":
    main()