import os
import re
import json
import hashlib
import pytz
import telebot
import vk_api
from datetime import datetime, timedelta
import xml.etree.ElementTree as ET

# === Настройки ===
TOKEN = os.getenv("TELEGRAM_TOKEN")
CHANNEL_ID = "@newsSVOih"
SEEN_IDS_FILE = "seen_ids.txt"

VK_TOKEN = os.getenv("VK_TOKEN")
VK_GROUP_ID = "your_vk_group_id_or_screen_name"  # Например 'public12345678' или 'mygroup'

bot = telebot.TeleBot(TOKEN)
moscow = pytz.timezone("Europe/Moscow")

# === Функции для обработки текста ===
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
                thumb_url = f"https://api.telegram.org/file/bot{TOKEN}/{thumb_info.file_id}"

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
    html += "</article>\n"
    return html

def extract_timestamp(html_block):
    match = re.search(r" (\d{2}\.\d{2}\.\d{4} \d{2}:\d{2})", html_block)
    if match:
        try:
            return datetime.strptime(match.group(1), "%d.%m.%Y %H:%M").replace(tzinfo=moscow)
        except Exception:
            return None
    return None

def hash_html_block(html):
    return hashlib.md5(html.encode("utf-8")).hexdigest()

# === VK интеграция ===
def fetch_vk_posts(count=5):
    """Получение последних постов из группы ВКонтакте"""
    if not VK_TOKEN or not VK_GROUP_ID:
        print("VK_TOKEN или VK_GROUP_ID не настроены")
        return []

    try:
        vk_session = vk_api.VkApi(token=VK_TOKEN)
        vk = vk_session.get_api()
        owner_id = f"-{VK_GROUP_ID}" if VK_GROUP_ID.isdigit() else VK_GROUP_ID
        response = vk.wall.get(owner_id=owner_id, count=count)
        posts = response.get("items", [])
        vk_news = []

        for post in posts:
            text = post.get("text", "")
            attachments = post.get("attachments", [])
            html = "<article class='news-item'>\n"

            if attachments:
                for att in attachments:
                    if att["type"] == "photo":
                        sizes = att["photo"]["sizes"]
                        url = sizes[-1]["url"]  # берем самое большое фото
                        html += f"<img src='{url}' alt='Фото' />\n"
                    elif att["type"] == "video":
                        html += f"<p>Видео: <a href='https://vk.com/video{att['video']['owner_id']}_{att['video']['id']}' target='_blank'>Смотреть</a></p>\n"

            text_clean = re.sub(r'\s+', ' ', text).strip()
            if text_clean:
                html += f"<div class='text-block'><p>{text_clean}</p></div>\n"

            ts = datetime.fromtimestamp(post.get("date"), moscow)
            iso_time = ts.strftime("%Y-%m-%dT%H:%M:%S+03:00")
            formatted_time = ts.strftime("%d.%m.%Y %H:%M")
            html += f"<p class='timestamp' data-ts='{iso_time}'> {formatted_time}</p>\n"
            html += f"<p class='source'>Источник: ВКонтакте</p>\n"
            html += "</article>\n"
            vk_news.append(html)

        return vk_news
    except Exception as e:
        print(f"Ошибка при получении постов VK: {e}")
        return []

# === Работа с seen_ids ===
def load_seen_ids():
    if not os.path.exists(SEEN_IDS_FILE):
        return set()
    with open(SEEN_IDS_FILE, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f)

def save_seen_ids(seen_ids):
    with open(SEEN_IDS_FILE, "w", encoding="utf-8") as f:
        for post_id in seen_ids:
            f.write(f"{post_id}\n")

# === Получение последних постов Telegram ===
def fetch_latest_posts():
    updates = bot.get_updates()
    posts = [
        u.channel_post
        for u in updates
        if u.channel_post and u.channel_post.chat.username == CHANNEL_ID[1:]
    ]
    return list(reversed(posts[-12:])) if posts else []

def is_older_than_two_days(timestamp):
    post_time = datetime.fromtimestamp(timestamp, moscow)
    now = datetime.now(moscow)
    return now - post_time >= timedelta(days=2)

# === Основная функция ===
def main():
    posts = fetch_latest_posts()
    vk_news = fetch_vk_posts(5)  # последние 5 постов VK
    seen_ids = load_seen_ids()
    new_ids = set()
    seen_html_hashes = set()

    os.makedirs("public", exist_ok=True)

    fresh_news = []
    if os.path.exists("public/news.html"):
        with open("public/news.html", "r", encoding="utf-8") as f:
            raw = f.read()
            fresh_news = re.findall(r"<article class='news-item.*?>.*?</article>", raw, re.DOTALL)
            for block in fresh_news:
                seen_html_hashes.add(hash_html_block(block))

    # Объединяем с VK постами
    fresh_news.extend(vk_news)

    # === Добавление новых постов Telegram (как раньше) ===
    grouped = {}
    urgent_post = None
    for post in posts:
        key = getattr(post, "media_group_id", None) or post.message_id
        grouped.setdefault(str(key), []).append(post)

    visible_limit = 12
    visible_count = sum(1 for block in fresh_news if "hidden" not in block)
    any_new = False

    for group_id, group_posts in grouped.items():
        post_id = str(group_id)
        first = group_posts[0]
        last = group_posts[-1]

        if post_id in seen_ids or post_id in new_ids:
            continue

        raw_caption = first.caption or ""
        raw_text = last.text or ""
        is_urgent = "#срочно" in (raw_caption + raw_text).lower()

        if is_urgent:
            urgent_post = (last, first, len(group_posts), post_id)
            continue

        html = format_post(last, caption_override=first.caption, group_size=len(group_posts), is_urgent=False)
        if not html:
            continue

        html_hash = hash_html_block(html)
        if html_hash in seen_html_hashes or html in fresh_news:
            continue

        if visible_count >= visible_limit:
            html = html.replace("<article class='news-item", "<article class='news-item hidden")

        fresh_news.insert(0, html)
        visible_count += 1
        new_ids.add(post_id)
        seen_html_hashes.add(html_hash)
        any_new = True

    # === Срочные посты Telegram ===
    if urgent_post:
        last, first, group_size, post_id = urgent_post
        urgent_html = format_post(last, caption_override=first.caption, group_size=group_size, is_urgent=True)
        if urgent_html and urgent_html not in fresh_news:
            fresh_news.insert(0, urgent_html)
            new_ids.add(post_id)
            print("Добавлена СРОЧНАЯ карточка (только вверху)")
            any_new = True

    if not any_new:
        print("Новых Telegram/ВК карточек нет — news.html не изменён")
        return

    # === Обновление news.html ===
    with open("public/news.html", "w", encoding="utf-8") as news_file:
        news_file.write("""
<style>
  body { font-family: sans-serif; line-height: 1.6; padding: 10px; background: #f9f9f9; }
  .news-item { margin-bottom: 30px; padding: 15px; background: #fff; border-radius: 8px; box-shadow: 0 0 5px rgba(0,0,0,0.05); border-left: 4px solid #0077cc; }
  .news-item img, .news-item video { max-width: 100%; margin: 10px 0; border-radius: 4px; }
  .timestamp { font-size: 0.9em; color: #666; margin-top: 10px; }
  .source { font-size: 0.85em; color: #999; }
  h2 { margin-top: 40px; font-size: 22px; border-bottom: 2px solid #ccc; padding-bottom: 5px; }
  .text-block p { margin-bottom: 10px; }
</style>
        """)
        for block in fresh_news:
            news_file.write(block + "\n")

        if any("hidden" in block for block in fresh_news):
            news_file.write("""
<button id="show-more">Показать ещё</button>
<script>
document.getElementById("show-more").onclick = () => {
  document.querySelectorAll(".news-item.hidden").forEach(el => el.classList.remove("hidden"));
  document.getElementById("show-more").style.display = "none";
};
</script>
""")

    save_seen_ids(seen_ids.union(new_ids))
    print(f"news.html обновлён, добавлено новых карточек: {len(new_ids)}")

if __name__ == "__main__":
    main()