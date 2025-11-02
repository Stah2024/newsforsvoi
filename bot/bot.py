import os
import re
import hashlib
import pytz
import telebot
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
VK_TOKEN        = os.getenv("VK_TOKEN")
VK_GROUP_ID     = os.getenv("VK_GROUP_ID")

CHANNEL_ID = "@newsSVOih"
SEEN_IDS   = "seen_ids.txt"

bot = telebot.TeleBot(TELEGRAM_TOKEN)
moscow = pytz.timezone("Europe/Moscow")

# ===================== ЧИСТКА =====================
def clean_text(t):
    if not t: return ""
    t = re.sub(r"Подписаться на новости|#срочно|https://t\.me/newsSVOih|@[\w]+", "", t, flags=re.I)
    t = re.sub(r'[\U0001F600-\U0001F9FF]+', "", t)
    return re.sub(r"\s+", " ", t).strip()

# ===================== КАРТОЧКА =====================
def make_card(msg, caption=None, size=1, urgent=False):
    time = datetime.fromtimestamp(msg.date, moscow).strftime("%d.%m.%Y %H:%M")
    iso  = datetime.fromtimestamp(msg.date, moscow).strftime("%Y-%m-%dT%H:%M:%S+03:00")

    cap = clean_text(caption or msg.caption or "")
    txt = clean_text(msg.text or "")

    url = None
    html = "<article class='news-item"
    if urgent:
        html += "' style='border-left:6px solid #d32f2f;background:#ffebee;'>"
        html += "<p style='color:#d32f2f;font-weight:bold;margin:0;'>СРОЧНО:</p>"
    else:
        html += "'>"

    if msg.content_type == "photo":
        fi = bot.get_file(msg.photo[-1].file_id)
        url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{fi.file_path}"
        html += f"<img src='{url}'/>"

    elif msg.content_type == "video":
        if msg.video.file_size > 20_000_000:
            return "", None
        fi = bot.get_file(msg.video.file_id)
        url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{fi.file_path}"
        html += f"<video controls src='{url}'></video>"

    if cap: html += f"<div class='text-block'><p>{cap}</p></div>"
    if txt and txt != cap: html += f"<div class='text-block'><p>{txt}</p></div>"

    html += f"<p class='timestamp' data-ts='{iso}'> {time}</p>"
    html += f"<a href='https://t.me/{CHANNEL_ID[1:]}/{msg.message_id}' target='_blank'>Читать в Telegram</a>"
    html += "<p class='source'>Источник: Новости для Своих</p>"
    if size > 1:
        html += f"<p><a href='https://t.me/{CHANNEL_ID[1:]}/{msg.message_id}' target='_blank'>Смотреть все</a></p>"
    html += "</article>"
    return html, url

# ===================== ВК =====================
def post_to_vk(caption, text, file_url=None):
    try:
        message = f"{caption}\n\n{text}\n\nИсточник: Новости для Своих".strip()
        attach = []

        if file_url:
            data = requests.get(file_url, timeout=15).content
            open("tmp.jpg", "wb").write(data)
            up_url = requests.post(
                "https://api.vk.com/method/photos.getWallUploadServer",
                params={"group_id": VK_GROUP_ID, "access_token": VK_TOKEN, "v": "5.199"}
            ).json()["response"]["upload_url"]

            uploaded = requests.post(up_url, files={"photo": open("tmp.jpg", "rb")}).json()
            photo = requests.post(
                "https://api.vk.com/method/photos.saveWallPhoto",
                data={
                    "group_id": VK_GROUP_ID,
                    "photo": uploaded["photo"],
                    "server": uploaded["server"],
                    "hash": uploaded["hash"],
                    "access_token": VK_TOKEN,
                    "v": "5.199"
                }
            ).json()["response"][0]
            attach = [f"photo{photo['owner_id']}_{photo['id']}"]
            os.remove("tmp.jpg")

        requests.post(
            "https://api.vk.com/method/wall.post",
            data={
                "owner_id": f"-{VK_GROUP_ID}",
                "from_group": 1,
                "message": message,
                "attachments": ",".join(attach),
                "access_token": VK_TOKEN,
                "v": "5.199"
            }
        )
        print("ВК: запостили")
    except Exception as e:
        print("ВК ошибка:", e)

# ===================== ПОЛУЧЕНИЕ ПОСТОВ =====================
def fetch_posts():
    updates = bot.get_updates()
    posts = [u.channel_post for u in updates
             if u.channel_post and u.channel_post.chat.username == "newsSVOih"]
    return list(reversed(posts[-12:])) if posts else []

# ===================== ОСНОВНОЙ ЦИКЛ =====================
def main():
    posts = fetch_posts()
    if not posts:
        print("Новых постов нет")
        return

    os.makedirs("public", exist_ok=True)

    # --- seen_ids ---
    seen = set(open(SEEN_IDS).read().split()) if os.path.exists(SEEN_IDS) else set()

    # --- старые карточки ---
    old_cards = []
    if os.path.exists("public/news.html"):
        raw = open("public/news.html").read()
        old_cards = re.findall(r"<article.*?</article>", raw, re.S)

    fresh = []
    urgent = None
    hashes = {hashlib.md5(c.encode()).hexdigest() for c in old_cards}

    # --- группировка ---
    groups = {}
    for p in posts:
        key = getattr(p, "media_group_id", None) or p.message_id
        groups.setdefault(str(key), []).append(p)

    for gid, group in groups.items():
        pid = str(gid)
        if pid in seen: continue

        first = group[0]
        last  = group[-1]
        is_urg = "#срочно" in (first.caption or "" + last.text or "").lower()

        html, url = make_card(last, first.caption, len(group), is_urg)
        if not html: continue
        if hashlib.md5(html.encode()).hexdigest() in hashes: continue

        # === ВК ===
        if not is_urg:
            post_to_vk(
                clean_text(first.caption or ""),
                clean_text(last.text or ""),
                url
            )

        # === СРОЧНО ===
        if is_urg:
            urgent = (html, pid)
            seen.add(pid)
            continue

        fresh.insert(0, html)
        seen.add(pid)
        hashes.add(hashlib.md5(html.encode()).hexdigest())

    # === КЛАДЁМ СРОЧНО ВВЕРХ ===
    if urgent:
        fresh.insert(0, urgent[0])
        print("СРОЧНО вверху!")

    # === ПИШЕМ news.html ===
    with open("public/news.html", "w", encoding="utf-8") as f:
        f.write("<style>"
                "body{font-family:sans-serif;background:#f9f9f9;padding:10px;line-height:1.6}"
                ".news-item{margin:20px 0;padding:15px;background:#fff;border-radius:8px;box-shadow:0 0 5px #ddd;border-left:4px solid #0077cc}"
                "img,video{max-width:100%;border-radius:8px;margin:10px 0}"
                ".timestamp{font-size:0.9em;color:#666}"
                "</style>")
        f.write("".join(fresh))

    # === seen_ids ===
    open(SEEN_IDS, "w").write("\n".join(seen))

    print(f"ГОТОВО! +{len(fresh)} карточек → сайт + ВК")

if __name__ == "__main__":
    main()