# -*- coding: utf-8 -*-
import os
import re
import json
import hashlib
import pytz
import telebot
import requests
from datetime import datetime, timedelta
import xml.etree.ElementTree as ET

TOKEN = os.getenv("TELEGRAM_TOKEN")
VK_TOKEN = os.getenv("VK_TOKEN")
VK_GROUP_ID = os.getenv("VK_GROUP_ID")
CHANNEL_ID = "@newsSVOih"
SEEN_IDS_FILE = "seen_ids.txt"
VK_POSTED = "vk_posted.txt"

bot = telebot.TeleBot(TOKEN)
moscow = pytz.timezone("Europe/Moscow")

def load_vk():
    if not os.path.exists(VK_POSTED):
        return set()
    with open(VK_POSTED, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f if line.strip())

def save_vk(posted_set):
    with open(VK_POSTED, "w", encoding="utf-8") as f:
        f.write("\n".join(sorted(posted_set)) + "\n")

def hash_post_content(caption, text):
    return hashlib.md5(clean_text(caption + text).encode("utf-8")).hexdigest()

def post_to_vk(caption, text, file_url=None, ctype=None, msg_id=None):
    vk_seen = load_vk()
    vk_key = hash_post_content(caption, text)
    if vk_key in vk_seen:
        print(f"ДУБЛЬ ВК — пропуск")
        return
    if not VK_TOKEN or not VK_GROUP_ID:
        print("VK не настроен")
        return

    message = f"{caption}\n\n{text}".strip() or "Новость"
    attachments = []

    try:
        if file_url and ctype == "photo":
            data = requests.get(file_url).content
            open("temp.jpg", "wb").write(data)
            upload = requests.post(
                requests.get(
                    "https://api.vk.com/method/photos.getWallUploadServer",
                    params={"group_id": VK_GROUP_ID, "access_token": VK_TOKEN, "v": "5.199"}
                ).json()["response"]["upload_url"],
                files={"photo": open("temp.jpg", "rb")}
            ).json()
            photo = requests.post("https://api.vk.com/method/photos.saveWallPhoto", data={
                "group_id": VK_GROUP_ID, "photo": upload["photo"], "server": upload["server"],
                "hash": upload["hash"], "access_token": VK_TOKEN, "v": "5.199"
            }).json()["response"][0]
            attachments.append(f"photo{photo['owner_id']}_{photo['id']}")
            os.remove("temp.jpg")

        elif file_url and ctype == "video":
            size = len(requests.get(file_url, stream=True).content)
            if size > 20_000_000:
                print(f"Видео {size/1e6:.1f}МБ — слишком большое для ВК")
                return  # ПРОПУСК ВК
            else:
                open("temp.mp4", "wb").write(requests.get(file_url).content)
                video = requests.post("https://api.vk.com/method/video.save", data={
                    "group_id": VK_GROUP_ID, "name": caption[:50],
                    "access_token": VK_TOKEN, "v": "5.199"
                }).json()["response"]
                requests.post(video["upload_url"], files={"video_file": open("temp.mp4", "rb")})
                attachments.append(f"video{video['owner_id']}_{video['video_id']}")
                os.remove("temp.mp4")

        requests.post("https://api.vk.com/method/wall.post", data={
            "owner_id": f"-{VK_GROUP_ID}",
            "from_group": 1,
            "message": message[:4095],
            "attachments": ",".join(attachments),
            "access_token": VK_TOKEN,
            "v": "5.199"
        })
        print("Запощено в ВК")
        vk_seen.add(vk_key)
        save_vk(vk_seen)
    except Exception as e:
        print(f"ВК ошибка: {e}")

def clean_text(text):
    if not text:
        return ""
    patterns = [
        r"Подписаться на новости для своих",
        r"https://t\.me/newsSVOih",
        r"🇷🇺"
    ]
    for p in patterns:
        text = re.sub(p, "", text, flags=re.IGNORECASE)
    text = re.sub(r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF]+', '', text)
    return re.sub(r'\s+', ' ', text).strip()

def format_post(message, caption_override=None, group_size=1, is_urgent=False):
    ts = message.date
    fmt_time = datetime.fromtimestamp(ts, moscow).strftime("%d.%m.%Y %H:%M")
    iso_time = datetime.fromtimestamp(ts, moscow).strftime("%Y-%m-%dT%H:%M:%S+03:00")
    caption = clean_text(caption_override or message.caption or "")
    text = clean_text(message.text or "")
    full = re.sub(r'#срочно', '', caption + " " + text, flags=re.IGNORECASE).strip()
    if text and text in full:
        caption = full.split(text)[0].strip()
    else:
        caption = full
        text = ""

    file_url = None
    content_type = None
    tg_link = f"https://t.me/{CHANNEL_ID[1:]}/{message.message_id}"
    html = ""

    if any(w in caption + text for w in ["Россия"]):
        html += "<h2>Россия</h2>\n"
    elif any(w in caption + text for w in ["Космос"]):
        html += "<h2>Космос</h2>\n"
    elif any(w in caption + text for w in ["Израиль", "Газа", "Мексика", "США", "Китай", "Тайвань", "Мир"]):
        html += "<h2>Мир</h2>\n"

    style = " style='border-left:6px solid #d32f2f;background:#ffebee;'" if is_urgent else ""
    html += f"<article class='news-item'{style}>\n"
    if is_urgent:
        html += "<p style='color:#d32f2f;font-weight:bold;margin-top:0;'>СРОЧНО:</p>\n"

    if message.content_type == "photo":
        fi = bot.get_file(message.photo[-1].file_id)
        file_url = f"https://api.telegram.org/file/bot{TOKEN}/{fi.file_path}"
        html += f"<img src='{file_url}' alt='Фото' />\n"
        content_type = "photo"

    elif message.content_type == "video":
        try:
            size = message.video.file_size or 0
            if size > 20_000_000:
                print(f"Видео {size/1e6:.1f}МБ — пропуск (сайт + ВК)")
                return "", None, None, tg_link  # ПОЛНЫЙ ПРОПУСК
            else:
                fi = bot.get_file(message.video.file_id)
                file_url = f"https://api.telegram.org/file/bot{TOKEN}/{fi.file_path}"
                html += f"<video controls src='{file_url}'></video>\n"
                content_type = "video"
        except Exception as e:
            print(f"Видео ошибка: {e}")
            return "", None, None, tg_link  # ПРОПУСК ПРИ ОШИБКЕ

    if caption:
        html += f"<div class='text-block'><p>{caption}</p></div>\n"
    if text and text != caption:
        html += f"<div class='text-block'><p>{text}</p></div>\n"

    html += f"<p class='timestamp' data-ts='{iso_time}'> {fmt_time}</p>\n"
    html += f"<a href='{tg_link}' target='_blank'>Читать в Telegram</a>\n"
    html += "<p class='source'>Источник: Новости для Своих</p>\n"
    if group_size > 1:
        html += f"<p><a href='{tg_link}' target='_blank'>Остальные фото/видео в Telegram</a></p>\n"

    microdata = {
        "@context": "https://schema.org", "@type": "NewsArticle",
        "headline": caption or text or "Новость",
        "datePublished": iso_time,
        "author": {"@type": "Organization", "name": "Новости для Своих"},
        "publisher": {"@type": "Organization", "name": "Новости для Своих",
                      "logo": {"@type": "ImageObject", "url": "https://newsforsvoi.ru/logo.png"}},
        "articleBody": (caption + "\n" + text).strip()
    }
    if file_url:
        microdata["image"] = file_url
    html += f"<script type='application/ld+json'>{json.dumps(microdata, ensure_ascii=False)}</script>\n"
    html += "</article>\n"
    return html, file_url, content_type, tg_link

def extract_timestamp(block):
    m = re.search(r" (\d{2}\.\d{2}\.\d{4} \d{2}:\d{2})", block)
    return datetime.strptime(m.group(1), "%d.%m.%Y %H:%M").replace(tzinfo=moscow) if m else None

def hash_html_block(html):
    return hashlib.md5(html.encode("utf-8")).hexdigest()

def update_sitemap():
    now = datetime.now(moscow).strftime("%Y-%m-%dT%H:%M:%S+03:00")
    sitemap = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://newsforsvoi.ru/index.html</loc><lastmod>{now}</lastmod><changefreq>always</changefreq><priority>1.0</priority></url>
  <url><loc>https://newsforsvoi.ru/news.html</loc><lastmod>{now}</lastmod><changefreq>always</changefreq><priority>0.9</priority></url>
  <url><loc>https://newsforsvoi.ru/archive.html</loc><lastmod>{now}</lastmod><changefreq>weekly</changefreq><priority>0.5</priority></url>
  <url><loc>https://newsforsvoi.ru/history.html</loc><lastmod>{now}</lastmod><changefreq>daily</changefreq><priority>0.8</priority></url>
</urlset>"""
    with open("public/sitemap.xml", "w", encoding="utf-8") as f:
        f.write(sitemap)
    print("sitemap.xml обновлён")

def generate_rss(news_blocks):
    items = ""
    for b in news_blocks[:20]:
        title = re.search(r"<p>(.*?)</p>", b)
        link = re.search(r"<a href='(https://t\.me/[^']+)'", b)
        date = re.search(r"data-ts='([^']+)'", b)
        t = title.group(1) if title else "Новость"
        l = link.group(1) if link else "https://t.me/newsSVOih"
        d = date.group(1) if date else datetime.now(moscow).isoformat()
        items += f"<item><title>{t}</title><link>{l}</link><description>{t}</description><pubDate>{d}</pubDate></item>\n"
    rss = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
<title>Новости для Своих</title>
<link>https://newsforsvoi.ru</link>
<description>Репосты из @newsSVOih</description>
{items}
</channel>
</rss>"""
    with open("public/rss.xml", "w", encoding="utf-8") as f:
        f.write(rss)
    print("rss.xml обновлён")

def load_seen_ids():
    if not os.path.exists(SEEN_IDS_FILE):
        return set()
    with open(SEEN_IDS_FILE, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f if line.strip())

def save_seen_ids(ids_set):
    with open(SEEN_IDS_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(ids_set) + "\n")

def fetch_latest_posts():
    updates = bot.get_updates()
    posts = [u.channel_post for u in updates if u.channel_post and u.channel_post.chat.username == CHANNEL_ID[1:]]
    return list(reversed(posts[-15:])) if posts else []

def main():
    posts = fetch_latest_posts()
    if not posts:
        print("Новых постов нет")
        return

    seen_ids = load_seen_ids()
    new_ids = set()
    seen_hashes = set()
    fresh_news = []
    os.makedirs("public", exist_ok=True)

    if os.path.exists("public/news.html"):
        with open("public/news.html", "r", encoding="utf-8") as f:
            raw = f.read()
            fresh_news = re.findall(r"<article class='news-item.*?>.*?</article>", raw, re.DOTALL)
            seen_hashes.update(hash_html_block(b) for b in fresh_news)

    grouped = {}
    urgent = None
    for p in posts:
        key = getattr(p, "media_group_id", None) or p.message_id
        grouped.setdefault(str(key), []).append(p)

    visible_count = sum(1 for b in fresh_news if "hidden" not in b)
    any_new = False

    for gid, group in grouped.items():
        pid = str(gid)
        first = group[0]
        last = group[-1]
        if pid in seen_ids or pid in new_ids:
            continue

        raw_cap = first.caption or ""
        raw_txt = last.text or ""
        is_urg = "#срочно" in (raw_cap + raw_txt).lower()

        if is_urg:
            urgent = (last, first, len(group), pid)
            continue

        html, url, ct, _ = format_post(last, first.caption, len(group), False)
        if not html:  # ← Если видео > 20 МБ → html = ""
            continue

        if hash_html_block(html) in seen_hashes:
            continue

        post_to_vk(clean_text(first.caption or ""), clean_text(last.text or ""), url, ct, pid)

        if visible_count >= 12:
            html = html.replace("<article class='news-item", "<article class='news-item hidden")
        fresh_news.insert(0, html)
        visible_count += 1
        new_ids.add(pid)
        seen_hashes.add(hash_html_block(html))
        any_new = True

    if urgent:
        html, url, ct, _ = format_post(urgent[0], urgent[1].caption, urgent[2], True)
        if html:  # ← Только если не видео > 20 МБ
            post_to_vk(clean_text(urgent[1].caption or ""), clean_text(urgent[0].text or ""), url, ct, urgent[3])
            fresh_news.insert(0, html)
            new_ids.add(urgent[3])
            any_new = True
            print("СРОЧНО → ВК + сайт")

    if any_new:
        with open("public/news.html", "w", encoding="utf-8") as f:
            for b in fresh_news:
                f.write(b + "\n")
            if any("hidden" in b for b in fresh_news):
                f.write('<button id="show-more" style="padding:10px 20px;background:#0077cc;color:#fff;border:none;border-radius:4px;cursor:pointer">Показать ещё</button>\n')
                f.write('<script>document.getElementById("show-more").onclick=()=>{document.querySelectorAll(".hidden").forEach(e=>e.classList.remove("hidden"));this.style.display="none"};</script>\n')

        save_seen_ids(seen_ids | new_ids)
        update_sitemap()
        generate_rss(fresh_news)
        print(f"ГОТОВО! +{len(new_ids)} новостей | ВК: {len(load_vk())} записей")

if __name__ == "__main__":
    main()