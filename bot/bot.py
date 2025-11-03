import os
import re
import json
import hashlib
import pytz
import telebot
import requests  # ← НОВОЕ
from datetime import datetime, timedelta
import xml.etree.ElementTree as ET

# ── ТОКЕНЫ ──
TOKEN = os.getenv("TELEGRAM_TOKEN")
VK_TOKEN = os.getenv("VK_TOKEN")
VK_GROUP_ID = os.getenv("VK_GROUP_ID")

CHANNEL_ID = "@newsSVOih"
SEEN_IDS_FILE = "seen_ids.txt"
VK_POSTED = "vk_posted.txt"  # ← АНТИ-ДУБЛЬ

bot = telebot.TeleBot(TOKEN)
moscow = pytz.timezone("Europe/Moscow")

# ── АНТИ-ДУБЛЬ ВК ──
def load_vk(): 
    return set(open(VK_POSTED).read().splitlines()) if os.path.exists(VK_POSTED) else set()
def save_vk(s): 
    open(VK_POSTED,"w").write("\n".join(s))

vk_seen = load_vk()

# ── ВК-ПОСТЕР (БЕЗ ССЫЛКИ) ──
def post_to_vk(caption, text, file_url=None, ctype=None, msg_id=None):
    if msg_id in vk_seen:
        print(f"ДУБЛЬ ВК {msg_id} — пропуск")
        return
    if not VK_TOKEN or not VK_GROUP_ID:
        print("VK не настроен")
        return

    full_text = f"{caption}\n\n{text}".strip()
    if not full_text: full_text = "Новость"

    attachments = []
    try:
        if file_url and ctype == "photo":
            open("t.jpg","wb").write(requests.get(file_url).content)
            up = requests.post(requests.get(
                "https://api.vk.com/method/photos.getWallUploadServer",
                params={"group_id":VK_GROUP_ID,"access_token":VK_TOKEN,"v":"5.199"}
            ).json()["response"]["upload_url"], files={"photo":open("t.jpg","rb")}).json()
            photo = requests.post("https://api.vk.com/method/photos.saveWallPhoto", data={
                "group_id":VK_GROUP_ID, "photo":up["photo"], "server":up["server"],
                "hash":up["hash"], "access_token":VK_TOKEN, "v":"5.199"}
            ).json()["response"][0]
            attachments.append(f"photo{photo['owner_id']}_{photo['id']}")
            os.remove("t.jpg")

        elif file_url and ctype == "video":
            size = len(requests.get(file_url, stream=True).content)
            if size > 50_000_000:
                print(f"Видео {size/1e6:.1f}МБ — пропуск в ВК")
            else:
                open("t.mp4","wb").write(requests.get(file_url).content)
                video = requests.post("https://api.vk.com/method/video.save", data={
                    "group_id":VK_GROUP_ID, "name":caption[:50], "access_token":VK_TOKEN, "v":"5.199"}
                ).json()["response"]
                requests.post(video["upload_url"], files={"video_file":open("t.mp4","rb")})
                attachments.append(f"video{video['owner_id']}_{video['video_id']}")
                os.remove("t.mp4")

        requests.post("https://api.vk.com/method/wall.post", data={
            "owner_id":f"-{VK_GROUP_ID}", "from_group":1, "message":full_text[:4095],
            "attachments":",".join(attachments), "access_token":VK_TOKEN, "v":"5.199"}
        )
        print("Запощено в ВК ✅")
        vk_seen.add(msg_id)
        save_vk(vk_seen)
    except Exception as e: 
        print(f"ВК ошибка: {e}")

# ── ТВОЙ ЧИСТЫЙ ТЕКСТ (БЕЗ ИЗМЕНЕНИЙ) ──
def clean_text(text):
    if not text: return ""
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
    return re.sub(r'\s+', ' ', text).strip()

# ── ФОРМАТ КАРТОЧКИ (ДОБАВИЛ file_url, ctype, tg_link) ──
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
    content_type = None
    tg_link = f"https://t.me/{CHANNEL_ID[1:]}/{message.message_id}"
    html = ""

    if "Россия" in caption or "Россия" in text:
        html += "<h2>Россия</h2>\n"
    elif "Космос" in caption or "Космос" in text:
        html += "<h2>Космос</h2>\n"
    elif any(w in caption+text for w in ["Израиль","Газа","Мексика","США","Китай","Тайвань","Мир"]):
        html += "<h2>Мир</h2>\n"

    if is_urgent:
        html += "<article class='news-item' style='border-left: 6px solid #d32f2f; background: #ffebee;'>\n"
        html += "<p style='color: #d32f2f; font-weight: bold; margin-top: 0;'>СРОЧНО:</p>\n"
    else:
        html += "<article class='news-item'>\n"

    if message.content_type == "photo":
        photos = message.photo
        fi = bot.get_file(photos[-1].file_id)
        file_url = f"https://api.telegram.org/file/bot{TOKEN}/{fi.file_path}"
        html += f"<img src='{file_url}' alt='Фото' />\n"
        content_type = "photo"

    elif message.content_type == "video":
        try:
            size = getattr(message.video, "file_size", 0)
            if size > 50_000_000:
                print(f"Видео {size/1e6:.1f}МБ — слишком большое")
                html += "<p style='color:#d32f2f'>Видео слишком большое для загрузки</p>"
            else:
                fi = bot.get_file(message.video.file_id)
                file_url = f"https://api.telegram.org/file/bot{TOKEN}/{fi.file_path}"
                html += f"<video controls src='{file_url}'></video>\n"
                content_type = "video"
        except Exception as e:
            print(f"Видео ошибка: {e}")

    if caption:
        html += f"<div class='text-block'><p>{caption}</p></div>\n"
    if text and text != caption:
        html += f"<div class='text-block'><p>{text}</p></div>\n"

    html += f"<p class='timestamp' data-ts='{iso_time}'> {formatted_time}</p>\n"
    html += f"<a href='{tg_link}' target='_blank'>Читать в Telegram</a>\n"
    html += f"<p class='source'>Источник: Новости для Своих</p>\n"
    if group_size > 1:
        html += f"<p><a href='{tg_link}' target='_blank'>Смотреть остальные фото/видео в Telegram</a></p>\n"

    microdata = {
        "@context": "https://schema.org", "@type": "NewsArticle",
        "headline": caption or text or "Новость", "datePublished": iso_time,
        "author": {"@type": "Organization", "name": "Новости для Своих"},
        "publisher": {
            "@type": "Organization", "name": "Новости для Своих",
            "logo": {"@type": "ImageObject", "url": "https://newsforsvoi.ru/logo.png"}
        },
        "articleBody": (caption + "\n" + text).strip()
    }
    if file_url: microdata["image"] = file_url
    html += f"<script type='application/ld+json'>{json.dumps(microdata, ensure_ascii=False)}</script>\n"
    html += "</article>\n"
    return html, file_url, content_type, tg_link

# ── ВСЁ НИЖЕ — ТВОЙ ОРИГИНАЛ БЕЗ ИЗМЕНЕНИЙ ──
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
            except ValueError as e:
                print(f"Ошибка при парсинге даты {date_str}: {e}")
                continue
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

    if os.path.exists("public/archive.html"):
        with open("public/archive.html", "r", encoding="utf-8") as f:
            for block in re.findall(r"<article class='news-preview.*?>.*?</article>", f.read(), re.DOTALL):
                seen_html_hashes.add(hash_html_block(block))

    # ── АРХИВАЦИЯ (ТВОЯ ЛОГИКА 100%) ──
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
                print(f"Дубль архивной карточки пропущен: {full_text[:30]}...")
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
                print(f"АРХИВ: {full_text[:30]}... ({date_str})")

            media_paths = re.findall(r"src=['\"](.*?)['\"]", block)
            for path in media_paths:
                local_path = os.path.join("public", os.path.basename(path))
                if os.path.exists(local_path):
                    try:
                        os.remove(local_path)
                        print(f"Удалён медиафайл: {local_path}")
                    except Exception as e:
                        print(f"Ошибка удаления {local_path}: {e}")
        else:
            retained_news.append(block)

    fresh_news = retained_news

    all_archive_cards = existing_archive_cards + new_archive_cards
    def get_date(card):
        match = re.search(r"data-timestamp=['\"]([^'\"]+)['\"]", card)
        if match:
            try:
                return datetime.strptime(match.group(1), "%Y-%m-%d")
            except:
                pass
        return datetime.min
    all_archive_cards.sort(key=get_date, reverse=True)

    archive_html = f"""<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <title>Архив новостей</title>
  <link rel="stylesheet" href="style.css">
  <style>
    body {{ margin: 0; font-family: system-ui, sans-serif; background: #1c1c1c; color: #e0e0e0; }}
    .news-item {{ background: #2a2a2a; margin: 1rem auto; padding: 1rem; border-radius: 8px; max-width: 800px; box-shadow: 0 2px 6px rgba(0,0,0,0.3); }}
    .news-item img, .news-item video {{ max-width: 100%; border-radius: 6px; }}
    .timestamp, .source {{ font-size: 0.9rem; color: #aaa; }}
    .button {{ display: inline-block; margin-top: 1rem; padding: 0.5rem 1rem; background: #2F4F4F; color: #fff; text-decoration: none; border-radius: 4px; }}
    .flag-icon {{ width: 48px; margin-bottom: 1rem; }}
    header h1, header h2 {{ margin: 0.2rem 0; }}
    input[type="search"] {{ margin-top: 1rem; padding: 0.5rem; width: 80%; max-width: 400px; border-radius: 4px; border: none; }}
    .news-preview {{ background: #2a2a2a; margin: 1.5rem auto; padding: 1.2rem; border-radius: 8px; max-width: 800px; box-shadow: 0 2px 8px rgba(0,0,0,0.3); border-left: 4px solid #2F4F4F; }}
    .news-preview img {{ max-width: 200px; border-radius: 6px; float: left; margin-right: 1rem; }}
    .preview-text {{ margin: 0.5rem 0; color: #ddd; }}
    .telegram-hint {{ color: #4CAF50; font-weight: bold; }}
    .telegram-link {{ color: #4CAF50; text-decoration: none; font-weight: bold; }}
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
{''.join(all_archive_cards)}
</main>
</body>
</html>"""
    with open("public/archive.html", "w", encoding="utf-8") as f:
        f.write(archive_html)
    print(f"archive.html обновлён: +{archived_count} новых, всего {len(all_archive_cards)}")

    # ── НОВЫЕ ПОСТЫ + ВК ──
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

        html, file_url, ctype, tg_link = format_post(last, caption_override=first.caption, group_size=len(group_posts), is_urgent=False)
        if not html:
            continue

        html_hash = hash_html_block(html)
        if html_hash in seen_html_hashes:
            continue

        # ← ВК ЗДЕСЬ
        post_to_vk(clean_text(first.caption or ""), clean_text(last.text or ""), file_url, ctype, post_id)

        if visible_count >= visible_limit:
            html = html.replace("<article class='news-item", "<article class='news-item hidden")

        fresh_news.insert(0, html)
        visible_count += 1
        new_ids.add(post_id)
        seen_html_hashes.add(html_hash)
        any_new = True

    if urgent_post:
        last, first, gsize, pid = urgent_post
        html, file_url, ctype, tg_link = format_post(last, first.caption, gsize, True)
        if html:
            post_to_vk(clean_text(first.caption or ""), clean_text(last.text or ""), file_url, ctype, pid)
            fresh_news.insert(0, html)
            new_ids.add(pid)
            any_new = True
            print("СРОЧНО → ВК + сайт")

    if not any_new and not archived_count:
        print("Новых или архивированных карточек нет")
        return

    with open("public/news.html", "w", encoding="utf-8") as f:
        f.write("<style>body{font-family:sans-serif;line-height:1.6;padding:10px;background:#f9f9f9;}.news-item{margin-bottom:30px;padding:15px;background:#fff;border-radius:8px;box-shadow:0 0 5px rgba(0,0,0,0.05);border-left:4px solid #0077cc;}.news-item img,.news-item video{max-width:100%;margin:10px 0;border-radius:4px;}.timestamp{font-size:0.9em;color:#666;margin-top:10px;}.source{font-size:0.85em;color:#999;}h2{margin-top:40px;font-size:22px;border-bottom:2px solid #ccc;padding-bottom:5px;}.text-block p{margin-bottom:10px;}</style>\n")
        for b in fresh_news: f.write(b + "\n")
        if any("hidden" in b for b in fresh_news):
            f.write('<button id="show-more">Показать ещё</button><script>document.getElementById("show-more").onclick=()=>{document.querySelectorAll(".news-item.hidden").forEach(el=>el.classList.remove("hidden"));document.getElementById("show-more").style.display="none";};</script>\n')

    save_seen_ids(seen_ids.union(new_ids))
    update_sitemap()
    generate_rss(fresh_news)
    print(f"ГОТОВО! +{len(new_ids)} новостей | ВК: {len([i for i in new_ids if i in vk_seen])}")

if __name__ == "__main__":
    main()