import os
import telebot
from datetime import datetime, timedelta
import pytz
import re

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHANNEL_ID = "@newsSVOih"
SEEN_IDS_FILE = "seen_ids.txt"

bot = telebot.TeleBot(TOKEN)
moscow = pytz.timezone('Europe/Moscow')

def clean_text(text):
    unwanted = [
        "💪Подписаться на новости для своих🇷🇺",
        "Подписаться на новости для своих",
        "https://t.me/newsSVOih"
    ]
    for phrase in unwanted:
        text = text.replace(phrase, "")
    return text.strip()

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

def is_older_than_two_days(timestamp):
    post_time = datetime.fromtimestamp(timestamp, moscow)
    now = datetime.now(moscow)
    return now - post_time >= timedelta(days=2)

def format_post(message, caption_override=None, group_size=1):
    if message.content_type == 'video' and message.video.file_size > 20_000_000:
        print(f"⛔ Пропускаем пост {message.message_id} — видео > 20MB")
        return ""

    html = "<article class='news-item'>\n"
    timestamp = message.date
    formatted_time = datetime.fromtimestamp(timestamp, moscow).strftime("%d.%m.%Y %H:%M")

    caption = clean_text(caption_override or message.caption or "")
    text = clean_text(message.text or "")
if message.content_type == 'photo':
        photos = message.photo
        file_info = bot.get_file(photos[-1].file_id)
        file_url = f"https://api.telegram.org/file/bot{TOKEN}/{file_info.file_path}"
        html += f"<img src='{file_url}' alt='Фото' />\n"
        if caption:
            html += f"<p>{caption}</p>\n"
        if group_size > 1:
            html += f"<a href='https://t.me/{CHANNEL_ID[1:]}/{message.message_id}' target='_blank'>📷 Смотреть все фото в Telegram</a>\n"

    elif message.content_type == 'video':
        file_info = bot.get_file(message.video.file_id)
        file_url = f"https://api.telegram.org/file/bot{TOKEN}/{file_info.file_path}"
        html += f"<video controls src='{file_url}'></video>\n"
        if caption:
            html += f"<p>{caption}</p>\n"
        if group_size > 1:
            html += f"<a href='https://t.me/{CHANNEL_ID[1:]}/{message.message_id}' target='_blank'>🎥 Смотреть все видео в Telegram</a>\n"

    if text and text != caption:
        html += f"<p>{text}</p>\n"

    html += f"<p class='timestamp'>🕒 {formatted_time}</p>\n"
    html += f"<a href='https://t.me/{CHANNEL_ID[1:]}/{message.message_id}' target='_blank'>Читать в Telegram</a>\n"
    html += f"<p class='source'>Источник: {message.chat.title}</p>\n"
    html += "</article>\n"
    return html

def extract_timestamp(html_block):
    match = re.search(r"🕒 (\d{2}\.\d{2}\.\d{4} \d{2}:\d{2})", html_block)
    if match:
        try:
            return datetime.strptime(match.group(1), "%d.%m.%Y %H:%M").replace(tzinfo=moscow)
        except:
            return None
    return None

def main():
    posts = fetch_latest_posts()
    seen_ids = load_seen_ids()
    new_ids = set()

    print("📥 Получено постов:", len(posts))
    print("📄 Уже обработанные ID:", seen_ids)

    os.makedirs("public", exist_ok=True)

    old_news = []
    if os.path.exists("public/news.html"):
        with open("public/news.html", "r", encoding="utf-8") as f:
            raw = f.read()
            old_news = re.findall(r"<article class='news-item.*?>.*?</article>", raw, re.DOTALL)

    fresh_news = []
    with open("public/archive.html", "a", encoding="utf-8") as archive_file:
        for block in old_news:
            ts = extract_timestamp(block)
            if ts and is_older_than_two_days(ts.timestamp()):
                archive_file.write(block + "\n")
            else:
                fresh_news.append(block)

    visible_limit = 12
    visible_count = sum(1 for block in fresh_news if "hidden" not in block)

    grouped = {}
    for post in posts:
        key = post.media_group_id or post.message_id
        grouped.setdefault(key, []).append(post)

    for group_id, group_posts in grouped.items():
        first = group_posts[0]
        last = group_posts[-1]
        post_id = str(first.message_id)

        print(f"🔍 Проверка группы {group_id} — {'новая' if post_id not in seen_ids else 'уже была'}")

        if post_id in seen_ids:
            continue

        print(f"📦 Пост {post_id} тип: {last.content_type}, caption: {first.caption}")
        print("🕒 Дата:", datetime.fromtimestamp(last.date, moscow))
        print("📆 Сейчас:", datetime.now(moscow))
        print("⏳ Старше 2 дней:", is_older_than_two_days(last.date))

        html = format_post(last, caption_override=first.caption, group_size=len(group_posts))
        print(f"🧾 Сформирован HTML для {post_id}: {'да' if html else 'нет'}")

        if not html:
            continue

        if is_older_than_two_days(last.date):
            with open("public/archive.html", "a", encoding="utf-8") as archive_file:
                archive_file.write(html + "\n")
        else:
            if visible_count >= visible_limit:
                html = html.replace("<article", "<article class='news-item hidden'")
            fresh_news.insert(0, html)
            visible_count += 1
            new_ids.add(post_id)

    with open("public/news.html", "w", encoding="utf-8") as news_file:
        news_file.write(f"<!-- Обновлено: {datetime.now(moscow)} -->\n")
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

    print("✅ news.html записан")
    print("📦 Количество блоков в fresh_news:", len(fresh_news))

    with open("public/news.html", "r", encoding="utf-8") as f:
        preview = f.read(300)
        print("📄 Превью news.html:")
        print(preview if preview else "⚠️ news.html пустой")

    print("🆕 Новые ID для сохранения:", new_ids)
    save_seen_ids(seen_ids.union(new_ids))

if __name__ == "__main__":
    main()