import os
import re
import json
import hashlib
import pytz
import telebot
from datetime import datetime, timedelta

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
    iso_time = datetime.fromtimestamp(timestamp, moscow).strftime("%Y-%m-%dT%H:%M:%S+03:00")  # Исправлен формат времени
    caption = clean_text(caption_override or message.caption or "")
    text = clean_text(message.text or "")
    file_url = None
    html = ""

    if "Россия" in caption or "Россия" in text:
        html += "<h2>Россия</h2>\n"
    elif "Космос" in caption or "Космос" in text:
        html += "<h2>Космос</h2>\n"
    elif any(word in caption + text for word in ["Израиль", "Газа", "Мексика", "США", "Китай", "Тайвань", "Мир"]):
        html += "<h2>Мир</h2>\n"

    html += "<article class='news-item'>\n"

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
                print(f"⛔️ Пропущено видео >20MB: {size} байт")
                return ""
        except Exception as e:
            print(f"⚠️ Ошибка при обработке видео: {e}")
            return ""

    if caption:
        html += f"<div class='text-block'><p>{caption}</p></div>\n"
    if text and text != caption:
        html += f"<div class='text-block'><p>{text}</p></div>\n"

    html += f"<p class='timestamp' data-ts='{iso_time}'>🕒 {formatted_time}</p>\n"
    html += f"<a href='https://t.me/{CHANNEL_ID[1:]}/{message.message_id}' target='_blank'>Читать в Telegram</a>\n"
    html += f"<p class='source'>Источник: {message.chat.title}</p>\n"

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
    now = datetime.now(moscow).strftime("%Y-%m-%dT%H:%M:%S+03:00")
    history_lastmod = now  # Значение по умолчанию
    sitemap_file = "public/sitemap.xml"

    # Проверяем существующий sitemap.xml и сохраняем <lastmod> для history.html
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
            print(f"⚠️ Ошибка при чтении sitemap.xml: {e}")

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
    print("🗂 sitemap.xml обновлён")

def generate_rss(fresh_news):
    rss_items = ""
    for block in fresh_news:
        title_match = re.search(r"<p>(.*?)</p>", block)
        link_match = re.search(r"<a href='(https://t\.me/[^']+)'", block)
        date_match = re.search(r"data-ts='([^']+)'", block)

        title = title_match.group(1) if title_match else "Без заголовка"
        link = link_match.group(1) if link_match else "https://t.me/newsSVOih"
        pub_date = (
            datetime.strptime(date_match.group(1), "%Y-%m-%dT%H:%M:%S+03:00").strftime("%a, %d %b %Y %H:%M:%S +0300")
            if date_match
            else ""
        )

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
    print("📰 rss.xml обновлён")

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
    return list(reversed(posts[-12:])) if posts else []

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

    retained_news = []
    archived_count = 0
    archive_content = []
    for block in fresh_news:
        ts = extract_timestamp(block)

        if ts and is_older_than_two_days(ts.timestamp()):
            media_paths = re.findall(r"src=['\"](.*?)['\"]", block)
            for path in media_paths:
                local_path = os.path.join("public", os.path.basename(path))
                if os.path.exists(local_path):
                    try:
                        os.remove(local_path)
                        print(f"🧹 Удалён медиафайл: {local_path}")
                    except Exception as e:
                        print(f"⚠️ Ошибка удаления {local_path}: {e}")

            link_match = re.search(r"<a href='(https://t\.me/[^']+)'", block)
            text_matches = re.findall(r"<div class='text-block'><p>(.*?)</p></div>", block, re.DOTALL)
            category_match = re.search(r"<h2>(.*?)</h2>", block)

            link = link_match.group(1) if link_match else f"https://t.me/{CHANNEL_ID[1:]}"
            category = category_match.group(1) if category_match else "Новости"
            full_text = ""
            for text_match in text_matches:
                clean_text = re.sub(r'<[^>]+>', '', text_match).strip()
                full_text += clean_text + " "
            full_text = full_text.strip()[:200] + "..." if len(full_text) > 200 else full_text
            date_str = ts.strftime("%d.%m.%Y %H:%M")

            archive_card = f"""
<article class='news-preview' data-post-id='{link.split("/")[-1]}'>
    <p><strong>🗓 {date_str} | <span style='color:#0077cc'>{category}</span></strong></p>
    <p class='preview-text'>{full_text}</p>
    <p class='telegram-hint'>👀 Смотри в Telegram</p>
    <a href='{link}' target='_blank' class='telegram-link'>🔗 Открыть полный пост</a>
</article>
"""
            archive_content.append(archive_card)
            archived_count += 1
            print(f"📁 АРХИВ: {full_text[:30]}... ({date_str})")
        else:
            retained_news.append(block)

    archive_html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Архив новостей - Новости для Своих</title>
    <meta charset="UTF-8">
    <style>
        body {{ 
            font-family: sans-serif; 
            padding: 20px; 
            background: #f9f9f9; 
            line-height: 1.6;
        }}
        h1 {{ 
            color: #333; 
            text-align: center; 
            margin-bottom: 30px;
        }}
        .news-preview {{ 
            background: #fff; 
            margin: 20px 0; 
            padding: 20px; 
            border-radius: 8px; 
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            border-left: 4px solid #0077cc;
            cursor: pointer;
            transition: all 0.2s;
        }}
        .news-preview:hover {{ 
            box-shadow: 0 4px 20px rgba(0,0,0,0.15);
            transform: translateY(-2px);
        }}
        .news-preview p {{ 
            margin: 8px 0; 
            color: #333;
        }}
        .telegram-hint {{ 
            color: #0077cc; 
            font-weight: bold;
            margin: 15px 0 10px 0;
            font-size: 1.1em;
        }}
        .telegram-link {{ 
            display: none;
            color: #0077cc; 
            text-decoration: none; 
            font-weight: bold;
            padding: 10px 15px;
            background: #f0f8ff;
            border-radius: 6px;
            border: 2px solid #0077cc;
            display: inline-block;
            margin-top: 5px;
        }}
        .telegram-link:hover {{ 
            background: #e6f3ff; 
        }}
        .preview-text {{
            font-size: 1.05em;
            line-height: 1.5;
            color: #222;
        }}
    </style>
</head>
<body>
    <h1>🗂 Архив новостей</h1>
    {''.join(archive_content)}
    <script>
    document.querySelectorAll('.news-preview').forEach(card => {{
        card.addEventListener('click', function(e) {{
            if (!e.target.closest('a')) {{
                const link = this.querySelector('.telegram-link');
                if (link) {{
                    link.style.display = 'inline-block';
                    link.scrollIntoView({{behavior: 'smooth'}});
                    setTimeout(() => {{
                        link.click();
                    }}, 500);
                }}
            }}
        }});
    }});
    </script>
</body>
</html>"""

    with open("public/archive.html", "w", encoding="utf-8") as archive_file:
        archive_file.write(archive_html)

    print(f"📁 В архив перемещено: {archived_count} карточек (только текст)")

    fresh_news = retained_news

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

    with open("public/news.html", "w", encoding="utf-8") as news_file:
        news_file.write("""
<style>
  body {
    font-family: sans-serif;
    line-height: 1.6;
    padding: 10px;
    background: #f9f9f9;
  }
  .news-item {
    margin-bottom: 30px;
    padding: 15px;
    background: #fff;
    border-radius: 8px;
    box-shadow: 0 0 5px rgba(0,0,0,0.05);
    border-left: 4px solid #0077cc;
  }
  .news-item img, .news-item video {
    max-width: 100%;
    margin: 10px 0;
    border-radius: 4px;
  }
  .timestamp {
    font-size: 0.9em;
    color: #666;
    margin-top: 10px;
  }
  .source {
    font-size: 0.85em;
    color: #999;
  }
  h2 {
    margin-top: 40px;
    font-size: 22px;
    border-bottom: 2px solid #ccc;
    padding-bottom: 5px;
  }
  .text-block p {
    margin-bottom: 10px;
  }
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
    print(f"✅ news.html обновлен, добавлено новых карточек: {len(new_ids)}")
    update_sitemap()
    print("🗂 sitemap.xml обновлён")
    generate_rss(fresh_news)
    print("📰 RSS-файл создан")

if __name__ == "__main__":
    main()