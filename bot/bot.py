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

ARCHIVE_PATH = "public/archive.html"
NEWS_PATH = "public/news.html"
SITEMAP_PATH = "public/sitemap.xml"

ARCHIVE_TEMPLATE = """<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <title>Архив новостей</title>
  <link rel="stylesheet" href="style.css">
  <style>
    body { margin: 0; font-family: system-ui, sans-serif; background: #1c1c1c; color: #e0e0e0; }
    .news-item { background: #2a2a2a; margin: 1rem auto; padding: 1rem; border-radius: 8px; max-width: 800px; box-shadow: 0 2px 6px rgba(0,0,0,0.3); }
    .news-item img, .news-item video { max-width: 100%; border-radius: 6px; }
    .timestamp, .source { font-size: 0.9rem; color: #aaa; }
    .button { display: inline-block; margin-top: 1rem; padding: 0.5rem 1rem; background: #2F4F4F; color: #fff; text-decoration: none; border-radius: 4px; }
    .flag-icon { width: 48px; margin-bottom: 1rem; }
    header h1, header h2 { margin: 0.2rem 0; }
    input[type="search"] { margin-top: 1rem; padding: 0.5rem; width: 80%; max-width: 400px; border-radius: 4px; border: none; }
  </style>
</head>
<body>
<header style="background: linear-gradient(135deg, #444, #2f2f2f); color: #e0e0e0; text-align: center; padding: 3rem 1rem 2rem; border-bottom: 4px solid #2F4F4F; box-shadow: 0 4px 10px rgba(0,0,0,0.3);">
  <div class="header-content">
    <img src="rf-flag.svg" alt="Флаг" class="flag-icon">
    <div>
      <h1>Архив новостей</h1>
      <h2>Посты старше двух дней</h2>
      <a href="index.html" class="button">← Вернуться на главную</a>
      <br>
      <input type="search" placeholder="Поиск по архиву...">
    </div>
  </div>
</header>
<main>
"""

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
    try:
        return bot.get_chat_history(CHANNEL_ID, limit=10)
    except Exception as e:
        print("⚠️ Ошибка при получении истории канала:", e)
        return []

def update_sitemap():
    today = datetime.now(moscow).strftime("%Y-%m-%d")
    with open(SITEMAP_PATH, "r+", encoding="utf-8") as f:
        content = f.read()
        content = re.sub(r"<lastmod>\d{4}-\d{2}-\d{2}</lastmod>", f"<lastmod>{today}</lastmod>", content)
        f.seek(0)
        f.write(content)
        f.truncate()
def is_older_than_two_days(timestamp):
    post_time = datetime.fromtimestamp(timestamp, moscow)
    now = datetime.now(moscow)
    return now - post_time >= timedelta(days=2)

def format_post(message, caption_override=None, group_size=1):
    if message.content_type == 'video' and message.video.file_size > 20_000_000:
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

def ensure_archive_exists():
    if not os.path.exists(ARCHIVE_PATH):
        with open(ARCHIVE_PATH, "w", encoding="utf-8") as f:
            f.write(ARCHIVE_TEMPLATE + "\n</main>\n</body>\n</html>")

def append_to_archive(blocks):
    with open(ARCHIVE_PATH, "r+", encoding="utf-8") as f:
        content = f.read()
        if "</main>" in content:
            updated = content.replace("</main>", "\n" + "\n".join(blocks) + "\n</main>")
            f.seek(0)
            f.write(updated)
            f.truncate()

def main():
    ensure_archive_exists()
    posts = fetch_latest_posts()
    seen_ids = load_seen_ids()
    new_ids = set()

    os.makedirs("public", exist_ok=True)

    old_news = []
    if os.path.exists(NEWS_PATH):
        with open(NEWS_PATH, "r", encoding="utf-8") as f:
            raw = f.read()
            old_news = re.findall(r"<article class='news-item.*?>.*?</article>", raw, re.DOTALL)

    fresh_news = []
    archive_blocks = []
    for block in old_news:
        ts = extract_timestamp(block)
        if ts and is_older_than_two_days(ts.timestamp()):
            archive_blocks.append(block)
        else:
            fresh_news.append(block)

    if archive_blocks:
        append_to_archive(archive_blocks)

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

        if post_id in seen_ids:
            continue

        html = format_post(last, caption_override=first.caption, group_size=len(group_posts))
        if not html:
            continue

        if is_older_than_two_days(last.date):
            append_to_archive([html])
        else:
            if visible_count >= visible_limit:
                html = html.replace("<article", "<article class='news-item hidden'")
            fresh_news.insert(0, html)
            visible_count += 1
            new_ids.add(post_id)

    with open(NEWS_PATH, "w", encoding="utf-8") as news_file:
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

    save_seen_ids(seen_ids.union(new_ids))
    update_sitemap()
    print("✅ news.html обновлён")
    print("📦 Перенесено в архив:", len(archive_blocks))
    print("🌟 Новые ID:", new_ids)

if __name__ == "__main__":
    main()