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
    return list(reversed(posts[-100:])) if posts else []

def is_older_than_two_days(timestamp):
    post_time = datetime.fromtimestamp(timestamp, moscow)
    now = datetime.now(moscow)
    return now - post_time >= timedelta(days=2)

def format_post(message):
    # Пропускаем видео без caption — это дубликаты из одного поста
    if message.content_type == 'video' and not message.caption:
        return ""

    html = "<article class='news-item'>\n"

    timestamp = message.date
    formatted_time = datetime.fromtimestamp(timestamp, moscow).strftime("%d.%m.%Y %H:%M")

    if message.content_type == 'text':
        html += f"<p>{clean_text(message.text)}</p>\n"

    elif message.content_type == 'photo':
        photos = message.photo
        file_info = bot.get_file(photos[-1].file_id)
        file_url = f"https://api.telegram.org/file/bot{TOKEN}/{file_info.file_path}"
        caption = clean_text(message.caption or "")
        html += f"<img src='{file_url}' alt='Фото' />\n"
        if caption:
            html += f"<p>{caption}</p>\n"
        if len(photos) > 1:
            html += f"<a class='telegram-video-link' href='https://t.me/newsSVOih/{message.message_id}' target='_blank'>🖼 Смотреть остальные фото в Telegram</a>\n"

    elif message.content_type == 'video':
        file_info = bot.get_file(message.video.file_id)
        file_url = f"https://api.telegram.org/file/bot{TOKEN}/{file_info.file_path}"
        caption = clean_text(message.caption or "")
        html += f"<video controls src='{file_url}'></video>\n"
        if caption:
            html += f"<p>{caption}</p>\n"
        html += f"<a class='telegram-video-link' href='https://t.me/newsSVOih/{message.message_id}' target='_blank'>📹 Смотреть остальные видео в Telegram</a>\n"

    html += f"<p class='timestamp'>🕒 {formatted_time}</p>\n"
    html += f"<a href='https://t.me/newsSVOih/{message.message_id}' target='_blank'>Читать в Telegram</a>\n"
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

    os.makedirs("public", exist_ok=True)

    # Загружаем старый news.html
    old_news = []
    if os.path.exists("public/news.html"):
        with open("public/news.html", "r", encoding="utf-8") as f:
            raw = f.read()
            old_news = re.findall(r"<article class='news-item'>.*?</article>", raw, re.DOTALL)

    # Переносим устаревшие карточки в архив
    fresh_news = []
    with open("public/archive.html", "a", encoding="utf-8") as archive_file:
        for block in old_news:
            ts = extract_timestamp(block)
            if ts and is_older_than_two_days(ts.timestamp()):
                archive_file.write(block + "\n")
            else:
                fresh_news.append(block)

    # Добавляем новые карточки
    visible_limit = 12
    visible_count = 0
    for post in posts:
        post_id = str(post.message_id)
        if post_id in seen_ids:
            continue

        html = format_post(post)
        if not html:
            continue

        if visible_count >= visible_limit:
            html = html.replace("<article", "<article class='news-item hidden'")
        fresh_news.append(html)
        visible_count += 1
        new_ids.add(post_id)

    # Записываем обновлённый news.html
    with open("public/news.html", "w", encoding="utf-8") as news_file:
        for block in fresh_news:
            news_file.write(block + "\n")

        if any("hidden" in block for block in fresh_news):
            news_file.write("""
<button id="show-more">Показать ещё</button>
<script>
let batchSize = 10;
document.addEventListener('DOMContentLoaded', () => {
  const showMoreBtn = document.getElementById('show-more');
  if (!showMoreBtn) return;
  showMoreBtn.addEventListener('click', () => {
    const hiddenCards = document.querySelectorAll('.news-item.hidden');
    for (let i = 0; i < batchSize && i < hiddenCards.length; i++) {
      hiddenCards[i].classList.remove('hidden');
    }
    if (document.querySelectorAll('.news-item.hidden').length === 0) {
      showMoreBtn.style.display = 'none';
    }
  });
});
</script>
""")

    save_seen_ids(seen_ids.union(new_ids))

if __name__ == "__main__":
    main()