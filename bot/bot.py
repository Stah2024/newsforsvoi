import os
import re
import json
import hashlib
import pytz
import telebot
import torch
from datetime import datetime, timedelta
import xml.etree.ElementTree as ET

# === ПЕРЕФРАЗИРОВКА: модель из ../models/rut5-base ===
from transformers import T5Tokenizer, T5ForConditionalGeneration

MODEL_PATH = "../models/rut5-base"
try:
    tokenizer = T5Tokenizer.from_pretrained(MODEL_PATH)
    model = T5ForConditionalGeneration.from_pretrained(MODEL_PATH)
    model.eval()
    print("[OK] Модель rut5-base загружена")
except Exception as e:
    print(f"[ОШИБКА] Не найдена модель: {e}")
    tokenizer = None
    model = None

def paraphrase(text):
    if not text or len(text.strip()) < 10 or tokenizer is None:
        return text
    try:
        input_text = f"перефразировать: {text.strip()}"
        inputs = tokenizer(input_text, return_tensors="pt", max_length=256, truncation=True)
        with torch.no_grad():
            outputs = model.generate(
                **inputs,
                max_length=256,
                num_beams=5,
                temperature=0.8,
                early_stopping=True
            )
        result = tokenizer.decode(outputs[0], skip_special_tokens=True).strip()
        result = re.sub(r'[\U0001F1E6-\U0001F1FF\U0001F3F4\U0001F3F3\U0001F4AA\U0001F525\U0001F31F\U0001F91D\U0001F4AA\U0001F4A5]', '', result)
        result = re.sub(r'[🇷🇺🇺🇸🇮🇱🇵🇸💪🔥⭐✊]', '', result)
        result = re.sub(r'\s+', ' ', result)
        result = re.sub(r'^[.,!?;:-]+|[.,!?;:-]+$', '', result)
        return result.strip() if result else text
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

    # === ОПРЕДЕЛЕНИЕ РАЗМЕРА КАРТОЧКИ ===
    has_video = message.content_type == "video"
    has_photo = message.content_type == "photo"
    text_len = len(caption) + len(text)
    is_long = text_len > 200
    is_medium = text_len > 100 or has_photo

    size_class = "small"
    grid_row_span = 1
    grid_col_span = 1

    if has_video or (has_photo and is_long):
        size_class = "large"
        grid_row_span = 2
        grid_col_span = 2
    elif is_medium:
        size_class = "medium"
        grid_row_span = 2
        grid_col_span = 1

    html += f"<article class='news-item size-{size_class}' style='grid-row: span {grid_row_span}; grid-column: span {grid_col_span};'>\n"

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
            print(f"Ошибка при обработке видео: {e}")
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
    match = re.search(r" (\d{2}\.\d{2}\.\d{4} \d{2}:\d{2})", html_block)
    if match:
        try:
            return datetime.strptime(match.group(1), "%d.%m.%Y %H:%M").replace(tzinfo=moscow)
        except:
            return None
    return None

def hash_html_block(html):
    return hashlib.md5(html.encode("utf-8")).hexdigest()

def update_sitemap():
    now = datetime.now(moscow).strftime("%Y-%m-%dT%H:%M:%S+03:00")
    history_lastmod = now
    sitemap_file = "public/sitemap.xml"

    if os.path.exists(sitemap_file):
        try:
            tree = ET.parse(sitemap_file)
            root = tree.getroot()
            for url in root.findall("{http://www.sitemaps.org/schemas/sitemap/0.9}url"):
                loc = url.find("{http://www.sitemaps.org/schemas/sitemap/0.9}loc")
                if loc.text == "https://newsforsvoi.ru/history.html":
                    lastmod = url.find("{http://www.sitemaps.org/schemas/sitemap/0.9}lastmod")
                    if lastmod is not None:
                        history_lastmod = lastmod.text
                    break
        except Exception as e:
            print(f"Ошибка при чтении sitemap.xml: {e}")

    sitemap = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://newsforsvoi.ru/index.html</loc><lastmod>{now}</lastmod><changefreq>always</changefreq><priority>1.0</priority></url>
  <url><loc>https://newsforsvoi.ru/news.html</loc><lastmod>{now}</lastmod><changefreq>always</changefreq><priority>0.9</priority></url>
  <url><loc>https://newsforsvoi.ru/archive.html</loc><lastmod>{now}</lastmod><changefreq>weekly</changefreq><priority>0.5</priority></url>
  <url><loc>https://newsforsvoi.ru/history.html</loc><lastmod>{history_lastmod}</lastmod><changefreq>daily</changefreq><priority>0.8</priority></url>
</urlset>
"""
    with open(sitemap_file, "w", encoding="utf-8") as f:
        f.write(sitemap)
    print("sitemap.xml обновлён")

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
            date_str = date_match.group(1)
            try:
                if len(date_str) == 19:
                    dt = datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%S")
                else:
                    dt = datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%S+03:00")
                pub_date = dt.replace(tzinfo=moscow).strftime("%a, %d %b %Y %H:%M:%S +0300")
            except ValueError:
                pass

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
    return list(reversed(posts[-20:])) if posts else []  # Берём больше, чтобы был запас

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

    fresh_news = []
    if os.path.exists("public/news.html"):
        with open("public/news.html", "r", encoding="utf-8") as f:
            raw = f.read()
            container = re.search(r'<div class="news-container">(.*?)</div>', raw, re.DOTALL)
            if container:
                fresh_news = re.findall(r"<article class='news-item.*?>.*?</article>", container.group(1), re.DOTALL)
            for block in fresh_news:
                seen_html_hashes.add(hash_html_block(block))

    if os.path.exists("public/archive.html"):
        with open("public/archive.html", "r", encoding="utf-8") as f:
            for block in re.findall(r"<article class='news-preview.*?>.*?</article>", f.read(), re.DOTALL):
                seen_html_hashes.add(hash_html_block(block))

    # === АРХИВАЦИЯ ===
    retained_news = []
    archived_count = 0
    new_archive_cards = []

    existing_archive_cards = []
    if os.path.exists("public/archive.html"):
        with open("public/archive.html", "r", encoding="utf-8") as f:
            content = f.read()
            existing_archive_cards = re.findall(r"<article class='news-preview.*?>.*?</article>", content, re.DOTALL)

    for block in fresh_news:
        ts = extract_timestamp(block)
        if ts and is_older_than_two_days(ts.timestamp()):
            # (архивируем — как было)
            link_match = re.search(r"<a href='(https://t\.me/[^']+)'", block)
            text_matches = re.findall(r"<div class='text-block'><p>(.*?)</p></div>", block, re.DOTALL)
            category_match = re.search(r"<h2>(.*?)</h2>", block)
            img_match = re.search(r"<img src='(.*?)'", block)
            video_match = re.search(r"<video .*?src='(.*?)'", block)

            link = link_match.group(1) if link_match else f"https://t.me/{CHANNEL_ID[1:]}"
            category = category_match.group(1) if category_match else "Новости"
            preview_img = img_match.group(1) if img_match else (video_match.group(1) if video_match else "https://newsforsvoi.ru/preview.jpg")
            full_text = " ".join(re.sub(r'<[^>]+>', '', t).strip() for t in text_matches)
            full_text = full_text[:200] + "..." if len(full_text) > 200 else full_text
            date_str = ts.strftime("%d.%m.%Y %H:%M")
            timestamp_iso = ts.strftime("%Y-%m-%d")

            card_hash = hashlib.md5(f"{link}{date_str}".encode()).hexdigest()
            if any(card_hash in card for card in existing_archive_cards):
                pass
            else:
                archive_card = f"""
<article class='news-preview' data-timestamp='{timestamp_iso}' data-post-id='{link.split("/")[-1]}'>
    <img src='{preview_img}' alt='Превью' style='max-width:200px;border-radius:8px;margin-bottom:10px;' />
    <p><strong> {date_str} | <span style='color:#0077cc'>{category}</span></strong></p>
    <p class='preview-text'>{full_text}</p>
    <p class='telegram-hint'>Смотри в Telegram</p>
    <a href='{link}' target='_blank' class='telegram-link'>Открыть полный пост</a>
</article>
"""
                new_archive_cards.append(archive_card)
                archived_count += 1
        else:
            retained_news.append(block)

    fresh_news = retained_news

    # === ОБНОВЛЕНИЕ archive.html ===
    all_archive_cards = existing_archive_cards + new_archive_cards
    def get_date(card):
        match = re.search(r"data-timestamp=['\"]([^'\"]+)['\"]", card)
        return datetime.strptime(match.group(1), "%Y-%m-%d") if match else datetime.min
    all_archive_cards.sort(key=get_date, reverse=True)

    # (archive.html — как было, без изменений)

    # === НОВЫЕ ПОСТЫ ===
    grouped = {}
    for post in posts:
        key = getattr(post, "media_group_id", None) or post.message_id
        grouped.setdefault(str(key), []).append(post)

    base_limit = 12
    visible_count = sum(1 for block in fresh_news if "hidden" not in block)
    any_new = False

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
        if html_hash in seen_html_hashes or html in fresh_news:
            continue

        fresh_news.insert(0, html)
        new_ids.add(post_id)
        seen_html_hashes.add(html_hash)
        any_new = True

    # === ДИНАМИЧЕСКИЙ ЛИМИТ: показываем 12+, если влезает ===
    visible_count = 0
    final_news = []
    for block in fresh_news:
        if "hidden" not in block and visible_count < 20:  # запас
            final_news.append(block)
            visible_count += 1
        else:
            final_news.append(block.replace("<article", "<article class='hidden'"))

    # === ЗАПИСЬ news.html С MASONRY ===
    with open("public/news.html", "w", encoding="utf-8") as f:
        f.write(f"""<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <title>Новости для Своих</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: system-ui, sans-serif; background: #1a1a1a; color: #e0e0e0; }}
    .news-container {{
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      grid-auto-rows: 10px;
      gap: 16px;
      padding: 16px;
      max-width: 1400px;
      margin: 0 auto;
      grid-auto-flow: dense;
    }}
    .news-item {{
      background: #2a2a2a;
      padding: 16px;
      border-radius: 8px;
      box-shadow: 0 2px 8px rgba(0,0,0,0.3);
      border-left: 4px solid #0077cc;
      display: flex;
      flex-direction: column;
    }}
    .news-item img, .news-item video {{ width: 100%; height: auto; border-radius: 6px; margin: 8px 0; }}
    .size-small {{ grid-row: span 20; }}
    .size-medium {{ grid-row: span 30; }}
    .size-large {{ grid-row: span 42; grid-column: span 2; }}
    .timestamp {{ font-size: 0.9em; color: #aaa; margin-top: auto; }}
    .source {{ font-size: 0.85em; color: #999; }}
    h2 {{ grid-column: 1 / -1; margin: 32px 0 8px; font-size: 22px; border-bottom: 2px solid #444; padding-bottom: 8px; }}
    .text-block p {{ margin: 8px 0; }}
    a {{ color: #4CAF50; text-decoration: none; }}
    .hidden {{ display: none; }}
    #show-more {{ display: block; margin: 32px auto; padding: 12px 24px; background: #0077cc; color: white; border: none; border-radius: 6px; cursor: pointer; }}
    @media (max-width: 900px) {{
      .news-container {{ grid-template-columns: repeat(2, 1fr); }}
      .size-large {{ grid-column: span 2; grid-row: span 35; }}
    }}
    @media (max-width: 600px) {{
      .news-container {{ grid-template-columns: 1fr; }}
      .news-item {{ grid-row: auto !important; grid-column: auto !important; }}
    }}
  </style>
</head>
<body>
  <div class="news-container">
    {''.join(final_news)}
  </div>
  <button id="show-more" style="display:none;">Показать ещё</button>
  <script>
    const hidden = document.querySelectorAll('.news-item.hidden');
    if (hidden.length > 0) {{
      document.getElementById('show-more').style.display = 'block';
    }}
    document.getElementById('show-more').onclick = () => {{
      hidden.forEach(el => el.classList.remove('hidden'));
      document.getElementById('show-more').style.display = 'none';
    }};
  </script>
</body>
</html>""")

    save_seen_ids(seen_ids.union(new_ids))
    print(f"news.html обновлён: {len(new_ids)} новых")
    update_sitemap()
    generate_rss(final_news)
    print("Готово!")

if __name__ == "__main__":
    main()