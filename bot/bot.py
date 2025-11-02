import os
import re
import json
import hashlib
import pytz
import telebot
import requests
from datetime import datetime, timedelta
import xml.etree.ElementTree as ET

# === TELEGRAM ===
TOKEN = os.getenv("TELEGRAM_TOKEN")
CHANNEL_ID = "@newsSVOih"
SEEN_IDS_FILE = "seen_ids.txt"

bot = telebot.TeleBot(TOKEN)
moscow = pytz.timezone("Europe/Moscow")

# === VK ===
VK_TOKEN = os.getenv("VK_TOKEN")
VK_GROUP_ID = os.getenv("VK_GROUP_ID")
VK_API = "https://api.vk.com/method/"

# === Функции очистки текста ===
def clean_text(text):
    if not text:
        return ""
    unwanted_patterns = [
        r"💪\s*Подписаться на новости для своих\s*🇷🇺",
        r"Подписаться на новости для своих",
        r"https://t\.me/newsSVOih",
    ]
    for pattern in unwanted_patterns:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE)
    emoji_pattern = (
        r'[\U0001F600-\U0001F64F'
        r'\U0001F300-\U0001F5FF'
        r'\U0001F680-\U0001F6FF'
        r'\U0001F1E0-\U0001F1FF'
        r'\U00002600-\U000026FF'
        r'\U00002700-\U000027BF'
        r'\U0001F900-\U0001F9FF]+'
    )
    text = re.sub(emoji_pattern, '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

# === Форматирование поста для сайта ===
def format_post(message, caption_override=None, group_size=1, is_urgent=False):
    timestamp = message.date
    formatted_time = datetime.fromtimestamp(timestamp, moscow).strftime("%d.%m.%Y %H:%M")
    iso_time = datetime.fromtimestamp(timestamp, moscow).strftime("%Y-%m-%dT%H:%M:%S+03:00")
    caption = clean_text(caption_override or message.caption or "")
    text = clean_text(message.text or "")
    full_text = caption + " " + text
    full_text = re.sub(r'#срочно', '', full_text, flags=re.IGNORECASE).strip()
    if caption and text:
        caption = full_text.split(text)[0].strip()
    else:
        caption = full_text
        text = ""

    file_url = None
    thumb_url = "https://newsforsvoi.ru/preview.jpg"
    html = ""

    if "Россия" in caption or "Россия" in text:
        html += "<h2>Россия</h2>\n"
    elif "Космос" in caption or "Космос" in text:
        html += "<h2>Космос</h2>\n"
    elif any(word in caption + text for word in ["Израиль", "Газа", "Мексика", "США", "Китай", "Тайвань", "Мир"]):
        html += "<h2>Мир</h2>\n"

    if is_urgent:
        html += "<article class='news-item' style='border-left: 6px solid #d32f2f; background: #ffebee;'>\n"
        html += "<p style='color: #d32f2f; font-weight: bold; margin-top: 0;'>СРОЧНО:</p>\n"
    else:
        html += "<article class='news-item'>\n"

    if message.content_type == "photo":
        photos = message.photo
        file_info = bot.get_file(photos[-1].file_id)
        file_url = f"https://api.telegram.org/file/bot{TOKEN}/{file_info.file_path}"
        html += f"<img src='{file_url}' alt='Фото' />\n"
        thumb_url = file_url

    elif message.content_type == "video":
        try:
            size = getattr(message.video, "file_size", 0)
            if size == 0 or size > 20_000_000:
                print(f"Пропущено видео >20MB: {size} байт")
                return ""

            file_info = bot.get_file(message.video.file_id)
            file_url = f"https://api.telegram.org/file/bot{TOKEN}/{file_info.file_path}"
            html += f"<video controls src='{file_url}'></video>\n"

            if hasattr(message.video, "thumbnail") and message.video.thumbnail:
                thumb_info = bot.get_file(message.video.thumbnail.file_id)
                thumb_url = f"https://api.telegram.org/file/bot{TOKEN}/{thumb_info.file_path}"

            duration_str = "PT1M"
            if hasattr(message.video, "duration") and message.video.duration:
                mins = message.video.duration // 60
                secs = message.video.duration % 60
                duration_str = f"PT{mins}M{secs}S"

            video_schema = {
                "@context": "https://schema.org",
                "@type": "VideoObject",
                "name": caption or text or "Видео-новость",
                "description": (caption or text or "Видео из Telegram-канала @newsSVOih")[:500],
                "thumbnailUrl": thumb_url,
                "uploadDate": iso_time,
                "duration": duration_str,
                "contentUrl": file_url,
                "embedUrl": file_url,
                "publisher": {
                    "@type": "NewsMediaOrganization",
                    "name": "Новости для Своих",
                    "logo": {
                        "@type": "ImageObject",
                        "url": "https://newsforsvoi.ru/logo.png"
                    }
                }
            }
            html += f"<script type='application/ld+json'>{json.dumps(video_schema, ensure_ascii=False)}</script>\n"

        except Exception as e:
            print(f"Ошибка при обработке видео: {e}")
            return ""

    if caption:
        html += f"<div class='text-block'><p>{caption}</p></div>\n"
    if text and text != caption:
        html += f"<div class='text-block'><p>{text}</p></div>\n"

    html += f"<p class='timestamp' data-ts='{iso_time}'> {formatted_time}</p>\n"
    html += f"<a href='https://t.me/{CHANNEL_ID[1:]}/{message.message_id}' target='_blank'>Читать в Telegram</a>\n"
    html += f"<p class='source'>Источник: Новости для Своих</p>\n"

    if group_size > 1:
        html += (
            f"<p><a href='https://t.me/{CHANNEL_ID[1:]}/{message.message_id}' "
            f"target='_blank'>Смотреть остальные фото/видео в Telegram</a></p>\n"
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
            "logo": {"@type": "ImageObject", "url": "https://newsforsvoi.ru/logo.png"},
        },
        "articleBody": (caption + "\n" + text).strip(),
    }

    if file_url:
        microdata["image"] = file_url
        if message.content_type == "video":
            microdata["video"] = {
                "@type": "VideoObject",
                "name": caption or text or "Видео",
                "thumbnailUrl": thumb_url,
                "contentUrl": file_url,
                "uploadDate": iso_time,
                "duration": duration_str
            }

    html += f"<script type='application/ld+json'>\n{json.dumps(microdata, ensure_ascii=False)}\n</script>\n"
    html += "</article>\n"
    return html

# === Хеширование HTML для проверки дубликатов ===
def hash_html_block(html):
    return hashlib.md5(html.encode("utf-8")).hexdigest()

# === Загрузка/сохранение просмотренных постов ===
def load_seen_ids():
    if not os.path.exists(SEEN_IDS_FILE):
        return set()
    with open(SEEN_IDS_FILE, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f)

def save_seen_ids(seen_ids):
    with open(SEEN_IDS_FILE, "w", encoding="utf-8") as f:
        for post_id in seen_ids:
            f.write(f"{post_id}\n")

# === Публикация в VK ===
def vk_post(text, file_url=None, is_video=False):
    try:
        # Получаем upload server
        if is_video:
            server_url = VK_API + "video.save"
            params = {
                "access_token": VK_TOKEN,
                "group_id": VK_GROUP_ID,
                "name": text[:50],
                "description": text,
                "v": "5.131"
            }
            r = requests.get(server_url, params=params).json()
            upload_url = r["response"]["upload_url"]
            # Скачиваем видео
            video_data = requests.get(file_url).content
            files = {"video_file": video_data}
            r_upload = requests.post(upload_url, files=files).json()
            video_id = r_upload["video_id"]
            owner_id = -int(VK_GROUP_ID)
            # Публикуем видео
            requests.get(VK_API + "wall.post", params={
                "owner_id": owner_id,
                "from_group": 1,
                "attachments": f"video{owner_id}_{video_id}",
                "access_token": VK_TOKEN,
                "v": "5.131"
            })
        else:
            attachments = ""
            if file_url:
                # Фото: получаем upload server
                r = requests.get(VK_API + "photos.getWallUploadServer", params={
                    "group_id": VK_GROUP_ID,
                    "access_token": VK_TOKEN,
                    "v": "5.131"
                }).json()
                upload_url = r["response"]["upload_url"]
                photo_data = requests.get(file_url).content
                files = {"photo": photo_data}
                r_upload = requests.post(upload_url, files=files).json()
                save_resp = requests.get(VK_API + "photos.saveWallPhoto", params={
                    "group_id": VK_GROUP_ID,
                    "server": r_upload["server"],
                    "photo": r_upload["photo"],
                    "hash": r_upload["hash"],
                    "access_token": VK_TOKEN,
                    "v": "5.131"
                }).json()
                photo = save_resp["response"][0]
                attachments = f"photo{photo['owner_id']}_{photo['id']}"
            # Публикуем пост
            requests.get(VK_API + "wall.post", params={
                "owner_id": -int(VK_GROUP_ID),
                "from_group": 1,
                "message": text,
                "attachments": attachments,
                "access_token": VK_TOKEN,
                "v": "5.131"
            })
        print("Пост опубликован в VK")
    except Exception as e:
        print(f"Ошибка VK: {e}")

# === Основная логика ===
def fetch_latest_posts():
    updates = bot.get_updates()
    posts = [
        u.channel_post
        for u in updates
        if u.channel_post and u.channel_post.chat.username == CHANNEL_ID[1:]
    ]
    return list(reversed(posts[-12:])) if posts else []

def main():
    posts = fetch_latest_posts()
    seen_ids = load_seen_ids()
    new_ids = set()
    seen_html_hashes = set()

    if not posts:
        print("Новых постов нет — выходим")
        return

    os.makedirs("public", exist_ok=True)

    fresh_news = []
    if os.path.exists("public/news.html"):
        with open("public/news.html", "r", encoding="utf-8") as f:
            raw = f.read()
            fresh_news = re.findall(r"<article class='news-item.*?>.*?</article>", raw, re.DOTALL)
            for block in fresh_news:
                seen_html_hashes.add(hash_html_block(block))

    # === Добавление новых постов ===
    for post in posts:
        post_id = str(post.message_id)
        if post_id in seen_ids:
            continue
        html = format_post(post)
        if not html:
            continue
        fresh_news.insert(0, html)
        new_ids.add(post_id)

        # === Публикация в VK ===
        caption_text = clean_text(post.caption or post.text or "")
        if post.content_type == "photo":
            photos = post.photo
            file_info = bot.get_file(photos[-1].file_id)
            file_url = f"https://api.telegram.org/file/bot{TOKEN}/{file_info.file_path}"
            vk_post(caption_text, file_url=file_url)
        elif post.content_type == "video":
            file_info = bot.get_file(post.video.file_id)
            file_url = f"https://api.telegram.org/file/bot{TOKEN}/{file_info.file_path}"
            vk_post(caption_text, file_url=file_url, is_video=True)
        else:
            vk_post(caption_text)

    # === Сохраняем новости на сайт ===
    with open("public/news.html", "w", encoding="utf-8") as news_file:
        news_file.write("<style>body{font-family:sans-serif;} .news-item{margin-bottom:30px;padding:15px;background:#fff;border-radius:8px;}</style>\n")
        for block in fresh_news:
            news_file.write(block + "\n")

    save_seen_ids(seen_ids.union(new_ids))
    print(f"news.html обновлён, добавлено новых карточек: {len(new_ids)}")

if __name__ == "__main__":
    main()