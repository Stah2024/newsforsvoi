import os
import re
import json
import hashlib
import pytz
import telebot
import requests
from datetime import datetime, timedelta
import xml.etree.ElementTree as ET
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
VK_TOKEN = os.getenv("VK_TOKEN")
VK_GROUP_ID = os.getenv("VK_GROUP_ID")

CHANNEL_ID = "@newsSVOih"
SEEN_IDS_FILE = "seen_ids.txt"
bot = telebot.TeleBot(TELEGRAM_TOKEN)
moscow = pytz.timezone("Europe/Moscow")

# ====================== ЧИСТКА ТЕКСТА ======================
def clean_text(text):
    if not text: return ""
    patterns = [
        r"💪\s*Подписаться на новости для своих\s*🇷🇺",
        r"Подписаться на новости для своих",
        r"https://t\.me/newsSVOih",
        r"@[\w\d_]+"
    ]
    for p in patterns:
        text = re.sub(p, "", text, flags=re.IGNORECASE)
    text = re.sub(r'[\U0001F600-\U0001F9FF]+', '', text)
    return re.sub(r'\s+', ' ', text).strip()

# ====================== КАРТОЧКА ======================
def format_post(message, caption_override=None, group_size=1, is_urgent=False):
    ts = message.date
    time_str = datetime.fromtimestamp(ts, moscow).strftime("%d.%m.%Y %H:%M")
    iso = datetime.fromtimestamp(ts, moscow).strftime("%Y-%m-%dT%H:%M:%S+03:00")
    caption = clean_text(caption_override or message.caption or "")
    text = clean_text(message.text or "")
    full = re.sub(r'#срочно', '', f"{caption} {text}", flags=re.IGNORECASE).strip()

    file_url = None
    html = ""

    if "Россия" in full: html += "<h2>Россия</h2>\n"
    elif "Космос" in full: html += "<h2>Космос</h2>\n"
    elif any(x in full for x in ["Израиль","Газа","Мексика","США","Китай","Тайвань","Мир"]):
        html += "<h2>Мир</h2>\n"

    if is_urgent:
        html += "<article class='news-item' style='border-left:6px solid #d32f2f;background:#ffebee;'>\n"
        html += "<p style='color:#d32f2f;font-weight:bold;margin:0;'>СРОЧНО:</p>\n"
    else:
        html += "<article class='news-item'>\n"

    if message.content_type == "photo":
        fi = bot.get_file(message.photo[-1].file_id)
        file_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{fi.file_path}"
        html += f"<img src='{file_url}' alt='Фото'/>\n"

    elif message.content_type == "video":
        try:
            if getattr(message.video, "file_size", 0) > 20_000_000:
                return "", None
            fi = bot.get_file(message.video.file_id)
            file_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{fi.file_path}"
            html += f"<video controls src='{file_url}'></video>\n"
        except: return "", None

    if caption: html += f"<div class='text-block'><p>{caption}</p></div>\n"
    if text and text != caption: html += f"<div class='text-block'><p>{text}</p></div>\n"

    html += f"<p class='timestamp' data-ts='{iso}'> {time_str}</p>\n"
    html += f"<a href='https://t.me/{CHANNEL_ID[1:]}/{message.message_id}' target='_blank'>Читать в Telegram</a>\n"
    html += f"<p class='source'>Источник: Новости для Своих</p>\n"
    if group_size > 1:
        html += f"<p><a href='https://t.me/{CHANNEL_ID[1:]}/{message.message_id}' target='_blank'>Смотреть все в Telegram</a></p>\n"
    html += "</article>\n"
    return html, file_url

# ====================== ВК ======================
def post_to_vk(caption, text, file_url=None, ctype=None):
    try:
        msg = f"{caption}\n\n{text}\n\nИсточник: Новости для Своих".strip()
        att = []
        if file_url and ctype == "photo":
            data = requests.get(file_url).content
            with open("temp.jpg","wb") as f: f.write(data)
            up = requests.post("https://api.vk.com/method/photos.getWallUploadServer",
                params={"group_id":VK_GROUP_ID,"access_token":VK_TOKEN,"v":"5.199"}).json()["response"]["upload_url"]
            upload = requests.post(up, files={"photo":open("temp.jpg","rb")}).json()
            photo = requests.post("https://api.vk.com/method/photos.saveWallPhoto", data={
                "group_id":VK_GROUP_ID, "photo":upload["photo"], "server":upload["server"],
                "hash":upload["hash"], "access_token":VK_TOKEN, "v":"5.199"
            }).json()["response"][0]
            att.append(f"photo{photo['owner_id']}_{photo['id']}")
            os.remove("temp.jpg")
        requests.post("https://api.vk.com/method/wall.post", data={
            "owner_id":f"-{VK_GROUP_ID}", "from_group":1, "message":msg,
            "attachments":",".join(att), "access_token":VK_TOKEN, "v":"5.199"
        })
        print("ВК: запостили")
    except Exception as e: print(f"ВК ошибка: {e}")

# ====================== УТИЛИТЫ ======================
def hash_html_block(h): return hashlib.md5(h.encode()).hexdigest()

def load_seen_ids():
    if not os.path.exists(SEEN_IDS_FILE): return set()
    with open(SEEN_IDS_FILE,"r",encoding="utf-8") as f:
        return set(line.strip() for line in f)

def save_seen_ids(ids):
    with open(SEEN_IDS_FILE,"w",encoding="utf-8") as f:
        for i in ids: f.write(f"{i}\n")

# ←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←
# ВОТ ОНА — СТРОЧКА, КОТОРУЮ Я ЗАБЫЛ!
def fetch_latest_posts():
    updates = bot.get_updates()
    posts = [u.channel_post for u in updates
             if u.channel_post and u.channel_post.chat.username == CHANNEL_ID[1:]]
    return list(reversed(posts[-12:])) if posts else []
# ←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←

def update_sitemap():
    now = datetime.now(moscow).strftime("%Y-%m-%dT%H:%M:%S+03:00")
    s = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://newsforsvoi.ru/index.html</loc><lastmod>{now}</lastmod></url>
  <url><loc>https://newsforsvoi.ru/news.html</loc><lastmod>{now}</lastmod></url>
</urlset>"""
    with open("public/sitemap.xml","w",encoding="utf-8") as f: f.write(s)

def generate_rss(news):
    items = "".join(f"<item><title>{re.search(r'<p>(.*?)</p>',b).group(1) if re.search(r'<p>(.*?)</p>',b) else 'Новость'}</title><link>https://t.me/newsSVOih</link></item>" for b in news[:10])
    rss = f"""<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>Новости для Своих</title><link>https://newsforsvoi.ru</link>{items}</channel></rss>"""
    with open("public/rss.xml","w",encoding="utf-8") as f: f.write(rss)

# ====================== MAIN ======================
def main():
    posts = fetch_latest_posts()
    if not posts:
        print("Новых постов нет")
        return

    os.makedirs("public", exist_ok=True)
    seen = load_seen_ids()
    new = set()
    hashes = set()
    fresh = []

    if os.path.exists("public/news.html"):
        with open("public/news.html","r",encoding="utf-8") as f:
            raw = f.read()
            fresh = re.findall(r"<article class='news-item.*?>.*?</article>", raw, re.DOTALL)
            hashes = {hash_html_block(b) for b in fresh}

    grouped = {}
    urgent = None
    for p in posts:
        key = getattr(p, "media_group_id", None) or p.message_id
        grouped.setdefault(str(key), []).append(p)

    for gid, gp in grouped.items():
        pid = str(gid)
        if pid in seen or pid in new: continue
        first, last = gp[0], gp[-1]
        is_urg = "#срочно" in (first.caption or "" + last.text or "").lower()

        html, url = format_post(last, first.caption, len(gp), is_urg)
        if not html: continue
        if hash_html_block(html) in hashes: continue

        if not is_urg:
            post_to_vk(clean_text(first.caption or ""), clean_text(last.text or ""), url, last.content_type)

        if is_urg:
            urgent = (html, pid)
            continue

        fresh.insert(0, html)
        new.add(pid)
        hashes.add(hash_html_block(html))

    if urgent:
        fresh.insert(0, urgent[0])
        new.add(urgent[1])
        print("СРОЧНО вверху!")

    with open("public/news.html","w",encoding="utf-8") as f:
        f.write("<style>body{font-family:sans-serif;line-height:1.6;padding:10px;background:#f9f9f9;}.news-item{margin-bottom:30px;padding:15px;background:#fff;border-radius:8px;box-shadow:0 0 5px rgba(0,0,0,0.05);border-left:4px solid #0077cc;}img,video{max-width:100%;margin:10px 0;border-radius:4px;}.timestamp{font-size:0.9em;color:#666;}.source{font-size:0.85em;color:#999;}h2{margin-top:40px;font-size:22px;border-bottom:2px solid #ccc;padding-bottom:5px;}</style>")
        for b in fresh: f.write(b+"\n")

    save_seen_ids(seen | new)
    update_sitemap()
    generate_rss(fresh)
    print(f"ГОТОВО! +{len(new)} новостей → сайт + ВК")

if __name__ == "__main__":
    main()