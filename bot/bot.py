import os
import re
import json
import hashlib
import pytz
import telebot
from datetime import datetime, timedelta
import xml.etree.ElementTree as ET

# === ПЕРЕФРАЗИРОВКА (из моего) ===
from transformers import T5Tokenizer, T5ForConditionalGeneration
MODEL_PATH = "../models/rut5-base"
try:
    tokenizer = T5Tokenizer.from_pretrained(MODEL_PATH)
    model = T5ForConditionalGeneration.from_pretrained(MODEL_PATH)
    model.eval()
    print("[OK] Модель rut5-base загружена")
except Exception as e:
    print(f"[ОШИБКА] Модель: {e}")
    tokenizer = None
    model = None

def paraphrase(text):
    if not text or len(text.strip()) < 10 or tokenizer is None:
        return text
    try:
        input_text = f"перефразировать: {text.strip()}"
        inputs = tokenizer(input_text, return_tensors="pt", max_length=256, truncation=True)
        with torch.no_grad():
            outputs = model.generate(**inputs, max_length=256, num_beams=5, temperature=0.8, early_stopping=True)
        result = tokenizer.decode(outputs[0], skip_special_tokens=True).strip()
        result = re.sub(r'[\U0001F1E6-\U0001F1FF🇷🇺🇺🇸💪🔥⭐✊]', '', result)
        result = re.sub(r'\s+', ' ', result).strip()
        return result if result else text
    except Exception as e:
        print(f"[ПЕРЕФРАЗИРОВКА] Ошибка: {e}")
        return text

# =========================================

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHANNEL_ID = "@newsSVOih"
SEEN_IDS_FILE = "seen_ids.txt"

bot = telebot.TeleBot(TOKEN)
moscow = pytz.timezone("Europe/Moscow")

def clean_text(text):
    unwanted = [
        "💪Подписаться на новости для своих🇷🇺",
        "Подписаться на новости для своих",
        "https://t.me/newsSVOih",
    ]
    for phrase in unwanted:
        text = text.replace(phrase, "")
    return text.strip()

def format_post(message, caption_override=None, group_size=1):
    timestamp = message.date
    formatted_time = datetime.fromtimestamp(timestamp, moscow).strftime("%d.%m.%Y %H:%M")
    iso_time = datetime.fromtimestamp(timestamp, moscow).strftime("%Y-%m-%dT%H:%M:%S+03:00")

    caption = clean_text(caption_override or message.caption or "")
    text = clean_text(message.text or "")

    caption = paraphrase(caption)
    text = paraphrase(text)

    file_url = None
    html = ""

    if "Россия" in caption or "Россия" in text:
        html += "<h2>Россия</h2>\n"
    elif "Космос" in caption or "Космос" in text:
        html += "<h2>Космос</h2>\n"
    elif any(word in caption + text for word in ["Израиль", "Газа", "Мексика", "США", "Китай", "Тайвань", "Мир"]):
        html += "<h2>Мир</h2>\n"

    # === MASONRY РАЗМЕРЫ (из моего) ===
    has_video = message.content_type == "video"
    has_photo = message.content_type == "photo"
    text_len = len(caption) + len(text)
    is_long = text_len > 200
    is_medium = text_len > 100 or has_photo

    size_class = "small"
    if has_video or (has_photo and is_long):
        size_class = "large"
    elif is_medium:
        size_class = "medium"

    html += f"<article class='news-item size-{size_class}'>\n"

    if message.content_type == "photo":
        photos = message.photo
        file_info = bot.get_file(photos[-1].file_id)
        file_url = f"https://api.telegram.org/file/bot{TOKEN}/{file_info.file_path}"
        html += f"<img src='{file_url}' alt='Фото' />\n"
    elif message.content_type == "video":
        try:
            size = getattr(message.video, "file_size", 0)
            if size == 0 or size <= 20_000_000:
                file_info = bot.get_file(message.video.file_id)
                file_url = f"https://api.telegram.org/file/bot{TOKEN}/{file_info.file_path}"
                html += f"<video controls src='{file_url}'></video>\n"
            else:
                print(f"Пропущено видео >20MB: {size} байт")
                return ""
        except Exception as e:
            print(f"Ошибка видео: {e}")
            return ""

    if caption:
        html += f"<div class='text-block'><p>{caption}</p></div>\n"
    if text and text != caption:
        html += f"<div class='text-block'><p>{text}</p></div>\n"

    html += f"<p class='timestamp' data-ts='{iso_time}'> {formatted_time}</p>\n"
    html += f"<a href='https://t.me/{CHANNEL_ID[1:]}/{message.message_id}' target='_blank'>Читать в Telegram</a>\n"
    html += f"<p class='source'>Источник: {message.chat.title}</p>\n"

    if group_size > 1:
        html += f"<p><a href='https://t.me/{CHANNEL_ID[1:]}/{message.message_id}' target='_blank'>Смотреть остальные фото/видео в Telegram</a></p>\n"

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

    html += f"<script type='application/ld+json'>\n{json.dumps(microdata, ensure_ascii=False)}\n</script>\n"
    html += "</article>\n"
    return html

def extract_timestamp(html_block):
    match = re.search(r"data-ts='([^']+)'", html_block)
    if match:
        try:
            return datetime.strptime(match.group(1), "%Y-%m-%dT%H:%M:%S+03:00")
        except:
            return None
    return None

def hash_html_block(html):
    return hashlib.md5(html.encode("utf-8")).hexdigest()

def update_sitemap():
    now = datetime.now(moscow).strftime("%Y-%m-%dT%H:%M:%S+03:00")
    sitemap = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://newsforsvoi.ru/index.html</loc><lastmod>{now}</lastmod><changefreq>always</changefreq><priority>1.0</priority></url>
  <url><loc>https://newsforsvoi.ru/news.html</loc><lastmod>{now}</lastmod><changefreq>always</changefreq><priority>0.9</priority></url>
  <url><loc>https://newsforsvoi.ru/archive.html</loc><lastmod>{now}</lastmod><changefreq>weekly</changefreq><priority>0.5</priority></url>
</urlset>
"""
    with open("public/sitemap.xml", "w", encoding="utf-8") as f:
        f.write(sitemap)

def generate_rss(fresh_news):
    rss_items = ""
    for block in fresh_news:
        title_match = re.search(r"<p>(.*?)</p>", block)
        link_match = re.search(r"<a href='(https://t\.me/[^']+)'", block)
        date_match = re.search(r"data-ts='([^']+)'", block)
        title = title_match.group(1) if title_match else "Без заголовка"
        link = link_match.group(1) if link_match else "https://t.me/newsSVOih"
        pub_date = datetime.now(moscow).strftime("%a, %d %b %Y %H:%M:%S +0300")
        if date_match:
            try:
                dt = datetime.strptime(date_match.group(1), "%Y-%m-%dT%H:%M:%S+03:00")
                pub_date = dt.strftime("%a, %d %b %Y %H:%M:%S +0300")
            except: pass
        rss_items += f"""
<item>
  <title>{title}</title>
  <link>{link}</link>
  <description>{title}</description>
  <pubDate>{pub_date}</pubDate>
</item>
"""
    rss = f"""<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0">
  <channel>
    <title>Новости для Своих</title>
    <link>https://newsforsvoi.ru</link>
    <description>Лента Telegram-новостей</description>
    {rss_items}
  </channel>
</rss>
"""
    with open("public/rss.xml", "w", encoding="utf-8") as f:
        f.write(rss)
    print("rss.xml обновлён")

def load_seen_ids():
    if not os.path.exists(SEEN_IDS_FILE): return set()
    with open(SEEN_IDS_FILE, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f)

def save_seen_ids(seen_ids):
    with open(SEEN_IDS_FILE, "w", encoding="utf-8") as f:
        for post_id in seen_ids: f.write(f"{post_id}\n")

def fetch_latest_posts():
    updates = bot.get_updates()
    posts = [u.channel_post for u in updates if u.channel_post and u.channel_post.chat.username == CHANNEL_ID[1:]]
    return list(reversed(posts[-50:])) if posts else []

def is_older_than_two_days(timestamp):
    post_time = datetime.fromtimestamp(timestamp, moscow)
    now = datetime.now(moscow)
    return now - post_time >= timedelta(days=2)

def main():
    posts = fetch_latest_posts()
    seen_ids = load_seen_ids()
    new_ids = set()
    seen_html_hashes = set()

    if not posts:
        print("Новых постов нет — выходим")
        return

    os.makedirs("public", exist_ok=True)

    # === ЧИТАЕМ СТАРЫЕ НОВОСТИ ===
    fresh_news = []
    if os.path.exists("public/news.html"):
        with open("public/news.html", "r", encoding="utf-8") as f:
            old_content = f.read()
            old_cards = re.findall(r"<article class='news-item.*?>.*?</article>", old_content, re.DOTALL)
            for card in old_cards:
                card_hash = hash_html_block(card)
                if card_hash not in seen_html_hashes:
                    fresh_news.append(card)
                    seen_html_hashes.add(card_hash)

    # === АРХИВАЦИЯ (твой код) ===
    with open("public/archive.html", "w", encoding="utf-8") as archive_file:
        archive_file.write("""<!DOCTYPE html><html><head><title>Архив</title><meta charset="UTF-8"><style>/* твои стили */</style></head><body><h1>Архив</h1>""")
        retained_news = []
        for block in fresh_news:
            ts = extract_timestamp(block)
            if ts and is_older_than_two_days(ts.timestamp()):
                # Архивируем
                link = re.search(r"<a href='(https://t\.me/[^']+)'", block)
                text = re.search(r"<div class='text-block'><p>(.*?)</p></div>", block, re.DOTALL)
                preview = (text.group(1)[:100] + "..." if text else "Новость")
                date = ts.strftime("%d.%m.%Y %H:%M")
                archive_file.write(f"<article class='news-preview'><p><strong>{date}</strong></p><p>{preview}</p><a href='{link.group(1) if link else ''}' target='_blank'>Читать в Telegram</a></article>\n")
            else:
                retained_news.append(block)
        archive_file.write("</body></html>")
    fresh_news = retained_news

    # === НОВЫЕ ПОСТЫ ===
    grouped = {}
    for post in posts:
        key = getattr(post, "media_group_id", None) or post.message_id
        grouped.setdefault(str(key), []).append(post)

    for group_id, group_posts in grouped.items():
        post_id = str(group_id)
        if post_id in seen_ids or post_id in new_ids: continue
        first, last = group_posts[0], group_posts[-1]
        html = format_post(last, caption_override=first.caption, group_size=len(group_posts))
        if not html: continue
        html_hash = hash_html_block(html)
        if html_hash in seen_html_hashes: continue
        fresh_news.insert(0, html)
        new_ids.add(post_id)
        seen_html_hashes.add(html_hash)

    # === ЗАПИСЬ news.html (ТОЛЬКО КАРТОЧКИ) ===
    with open("public/news.html", "w", encoding="utf-8") as f:
        f.write("".join(fresh_news))

    save_seen_ids(seen_ids.union(new_ids))
    print(f"news.html обновлён: {len(new_ids)} новых, всего: {len(fresh_news)}")
    update_sitemap()
    generate_rss(fresh_news[:20])
    print("Готово!")

if __name__ == "__main__":
    main()