import os
import telebot
from datetime import datetime, timedelta
import pytz
import re
import hashlib

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
    html = "<article class='news-item'>\n"
    timestamp = message.date
    formatted_time = datetime.fromtimestamp(timestamp, moscow).strftime("%d.%m.%Y %H:%M")
    iso_time = datetime.fromtimestamp(timestamp, moscow).strftime("%Y-%m-%dT%H:%M:%S")

    caption = clean_text(caption_override or message.caption or "")
    text = clean_text(message.text or "")

    if message.content_type == 'photo':
        photos = message.photo
        file_info = bot.get_file(photos[-1].file_id)
        file_url = f"https://api.telegram.org/file/bot{TOKEN}/{file_info.file_path}"
        html += f"<img src='{file_url}' alt='Фото' />\n"

    elif message.content_type == 'video':
        try:
            size = getattr(message.video, 'file_size', 0)
            if size == 0 or size <= 20_000_000:
                file_info = bot.get_file(message.video.file_id)
                file_url = f"https://api.telegram.org/file/bot{TOKEN}/{file_info.file_path}"
                html += f"<video controls src='{file_url}'></video>\n"
            else:
                print(f"⛔️ Пропущено видео >20MB: {size} байт")
                return ""
        except Exception as e:
            print(f"⚠️ Ошибка при обработке видео: {e}")
            return ""

    if caption:
        html += f"<p>{caption}</p>\n"
    if text and text != caption:
        html += f"<p>{text}</p>\n"

    html += f"<p class='timestamp' data-ts='{iso_time}'>🕒 {formatted_time}</p>\n"
    html += f"<a href='https://t.me/{CHANNEL_ID[1:]}/{message.message_id}' target='_blank'>Читать в Telegram</a>\n"
    html += f"<p class='source'>Источник: {message.chat.title}</p>\n"

    if group_size > 1:
        html += (
            f"<p><a href='https://t.me/{CHANNEL_ID[1:]}/{message.message_id}' "
            f"target='_blank'>📷 Смотреть остальные фото/видео в Telegram</a></p>\n"
        )

    html += "</article>\n"
    return html


def extract_timestamp(html_block):
    match = re.search(r"🕒 (\d{2}\.\d{2}\.\d{4} \d{2}:\d{2})", html_block)
    if match:
        try:
            return datetime.strptime(match.group(1), "%d.%m.%Y %H:%M").replace(tzinfo=moscow)
        except Exception:
            return None
    return None


def hash_html_block(html):
    return hashlib.md5(html.encode("utf-8")).hexdigest()


def update_sitemap():
    now = datetime.now(moscow).strftime("%Y-%m-%dT%H:%M:%S%z")
    sitemap = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://newsforsvoi.ru/index.html</loc>
    <lastmod>{now}</lastmod>
    <changefreq>always</changefreq>
    <priority>1.0</priority>
  </url>
  <url>
    <loc>https://newsforsvoi.ru/news.html</loc>
    <lastmod>{now}</lastmod>
    <changefreq>always</changefreq>
    <priority>0.9</priority>
  </url>
  <url>
    <loc>https://newsforsvoi.ru/archive.html</loc>
    <lastmod>{now}</lastmod>
    <changefreq>weekly</changefreq>
    <priority>0.5</priority>
  </url>
</urlset>
"""
    with open("public/sitemap.xml", "w", encoding="utf-8") as f:
        f.write(sitemap)


def main():
    posts = fetch_latest_posts()
    seen_ids = load_seen_ids()
    new_ids = set()
    seen_html_hashes = set()

    if not posts:
        print("⚠️ Новых постов нет — выходим")
        return

    os.makedirs("public", exist_ok=True)

    fresh_news = []
    if os.path.exists("public/news.html"):
        with open("public/news.html", "r", encoding="utf-8") as f:
            raw = f.read()
            fresh_news = re.findall(r"<article class='news-item.*?>.*?</article>", raw, re.DOTALL)
            for block in fresh_news:
                seen_html_hashes.add(hash_html_block(block))

    if os.path.exists("public/archive.html"):
        with open("public/archive.html", "r", encoding="utf-8") as f:
            for block in re.findall(r"<article class='news-item.*?>.*?</article>", f.read(), re.DOTALL):
                seen_html_hashes.add(hash_html_block(block))

    grouped = {}
    for post in posts:
        key = getattr(post, "media_group_id", None) or post.message_id
        grouped.setdefault(str(key), []).append(post)

    visible_limit = 12
    visible_count = sum(1 for block in fresh_news if "hidden" not in block)
    any_new = False

    archive_file = open("public/archive.html", "a", encoding="utf-8")
    retained_news = []

    # Переносим старые новости в архив с удалением медиа и созданием превью
    for block in fresh_news:
        ts = extract_timestamp(block)
        block_hash = hash_html_block(block)
        if ts and is_older_than_two_days(ts.timestamp()):
            if block_hash not in seen_html_hashes:
                media_paths = re.findall(r"src=['\"](.*?)['\"]", block)
                for path in media_paths:
                    local_path = os.path.join("public", os.path.basename(path))
                    if os.path.exists(local_path):
                        try:
                            os.remove(local_path)
                            print(f"🧹 Удалён медиафайл: {local_path}")
                        except Exception as e:
                            print(f"⚠️ Не удалось удалить {local_path}: {e}")

                link_match = re.search(r"<a href='(https://t\.me/[^']+)'", block)
                caption_match = re.search(r"<p>(.*?)</p>", block)
                date_str = ts.strftime("%d.%m.%Y")
                caption = caption_match.group(1) if caption_match else "Без описания"

                if link_match:
                    link = link_match.group(1)
                    preview_html = f"""
<article class='news-preview'>
  <p>🗓 {date_str}</p>
  <p>📎 {caption}</p>
  <a href='{link}' target='_blank'>Смотреть в Telegram</a>
</article>
"""
                    archive_file.write(preview_html + "\n")

                seen_html_hashes.add(block_hash)
        else:
            retained_news.append(block)
    archive_file.close()
    fresh_news = retained_news

    # Добавляем новые посты
    for group_id, group_posts in grouped.items():
        post_id = str(group_id)
        first = group_posts[0]
        last = group_posts[-1]

        if post_id in seen_ids or post_id in new_ids:
            continue

        html = format_post(last, caption_override=first.caption, group_size=len(group_posts))
        if not html:
            continue

        html_hash = hash_html_block(html)
        if html_hash in seen_html_hashes:
            continue
        if html in fresh_news:
            continue

        if visible_count >= visible_limit:
            html = html.replace("<article class='news-item'>", "<article class='news-item hidden'>")
        fresh_news.insert(0, html)
        visible_count += 1

        new_ids.add(post_id)
        seen_html_hashes.add(html_hash)
        any_new = True

    if not any_new:
        print("⚠️ Новых карточек нет — news.html не изменен")
        return

    # Записываем обновленный news.html
    with open("public/news.html", "w", encoding="utf-8") as news_file:
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
    print(f"✅ news.html обновлен, добавлено новых карточек: {len(new_ids)}")
    update_sitemap()
    print("🗂 sitemap.xml обновлён")


if __name__ == "__main__":
    main()