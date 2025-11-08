import os
import re
import logging
from datetime import datetime
from bs4 import BeautifulSoup
import json

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("history.log"),
        logging.StreamHandler()
    ]
)

HISTORY_FILE = "public/history.html"
SITEMAP_FILE = "public/sitemap.xml"
RSS_FILE = "public/rss.xml"
POSTS_FILE = "bot/posts.txt"

# === КОНФИГУРАЦИЯ ===
DEFAULT_THUMBNAIL = "https://newsforsvoi.ru/media/default-history.jpg"
LOGO_URL = "https://newsforsvoi.ru/logo.png"
SITE_URL = "https://newsforsvoi.ru"
PAGE_URL = f"{SITE_URL}/history.html"

THEME_TITLE = "История России и мира"
THEME_DESC = "Что случилось в этот день"


def load_posts():
    if not os.path.exists(POSTS_FILE):
        logging.warning(f"{POSTS_FILE} не найден, создаём пустой")
        with open(POSTS_FILE, "w", encoding="utf-8") as f:
            f.write("")
        return []

    try:
        with open(POSTS_FILE, "r", encoding="utf-8") as f:
            content = f.read()
        if not content.strip():
            return []

        posts = []
        raw_posts = [p.strip() for p in re.split(r"\n?---\n?", content) if p.strip()]

        for post_text in raw_posts:
            post = {
                "title": f"{THEME_DESC}: Историческое событие",
                "text": "",
                "iso_time": datetime.now().strftime("%Y-%m-%dT%H:%M:%S+03:00"),
                "date": datetime.now().strftime("%d.%m.%Y %H:%M"),
                "media_url": "",
                "media_type": "",
                "thumbnail": DEFAULT_THUMBNAIL
            }

            lines = post_text.split("\n")
            current_field = None
            field_lines = []

            for line in lines:
                line = line.rstrip()

                if line.startswith("TITLE:"):
                    if current_field and current_field != "title":
                        post[current_field] = "\n".join(field_lines).strip()
                    current_field = "title"
                    field_lines = [line[7:].strip()]

                elif line.startswith("TEXT:"):
                    if current_field and current_field != "text":
                        post[current_field] = "\n".join(field_lines).strip()
                    current_field = "text"
                    field_lines = [line[6:].strip()]

                elif line.startswith("TIME:"):
                    if current_field:
                        post[current_field] = "\n".join(field_lines).strip()
                    post["iso_time"] = line[6:].strip()
                    current_field = None

                elif line.startswith("DATE:"):
                    if current_field:
                        post[current_field] = "\n".join(field_lines).strip()
                    post["date"] = line[6:].strip()
                    current_field = None

                elif line.startswith("MEDIA_URL:"):
                    if current_field:
                        post[current_field] = "\n".join(field_lines).strip()
                    post["media_url"] = line[11:].strip()
                    current_field = None

                elif line.startswith("MEDIA_TYPE:"):
                    if current_field:
                        post[current_field] = "\n".join(field_lines).strip()
                    post["media_type"] = line[12:].strip().lower()
                    current_field = None

                elif line.startswith("THUMBNAIL:"):
                    if current_field:
                        post[current_field] = "\n".join(field_lines).strip()
                    post["thumbnail"] = line[10:].strip()
                    current_field = None

                elif current_field:
                    field_lines.append(line)

            if current_field:
                post[current_field] = "\n".join(field_lines).strip()

            if not post["title"] and not post["text"]:
                continue

            if post["media_type"] in ["photo", "image"] and post["media_url"]:
                post["thumbnail"] = post["media_url"]

            posts.append(post)

        return posts

    except Exception as e:
        logging.error(f"Ошибка чтения {POSTS_FILE}: {e}")
        return []


def save_posts():
    try:
        with open(POSTS_FILE, "w", encoding="utf-8") as f:
            f.write("")
        logging.info(f"{POSTS_FILE} очищен")
    except Exception as e:
        logging.error(f"Ошибка записи {POSTS_FILE}: {e}")


def format_post(post):
    title = post.get("title", f"{THEME_DESC}: Историческое событие")
    text = post.get("text", "").replace("\n", "<br>")
    iso_time = post.get("iso_time", datetime.now().strftime("%Y-%m-%dT%H:%M:%S+03:00"))
    formatted_time = post.get("date", datetime.now().strftime("%d.%m.%Y %H:%M"))
    media_url = post.get("media_url", "")
    media_type = post.get("media_type", "")
    thumbnail = post.get("thumbnail", DEFAULT_THUMBNAIL)

    # === ГЕНЕРАЦИЯ КАРТОЧКИ С <h3> ===
    html = "<article class='news-item'>\n"
    html += f"<span class='category-badge'>{THEME_TITLE}</span>\n"

    if media_url and media_type in ["photo", "image"]:
        html += f"<img src='{media_url}' alt='Фото события' class='news-image' style='display:block; max-width:100%; height:auto; margin:10px 0; border-radius:8px;'>\n"
    elif media_url and media_type == "video":
        poster = thumbnail if thumbnail != DEFAULT_THUMBNAIL else ""
        poster_attr = f" poster='{poster}'" if poster else ""
        html += f"<video controls src='{media_url}' class='news-image'{poster_attr}></video>\n"

    html += f"<h3>{title}</h3>\n"  # ← КЛЮЧЕВОЕ ИСПРАВЛЕНИЕ
    html += f"<p class='news-text'>{text}</p>\n"
    html += f"<div class='timestamp' data-ts='{iso_time}'>  {formatted_time}</div>\n"
    html += "</article>\n"

    # === JSON-LD ===
    json_ld_article = {
        "@type": "NewsArticle",
        "headline": title[:200],
        "description": f"{THEME_DESC}: {post.get('text', '')[:500]}",
        "datePublished": iso_time,
        "dateModified": iso_time,
        "author": {"@type": "Organization", "name": "История России и мира"},
        "publisher": {
            "@type": "Organization",
            "name": "Новости для Своих",
            "logo": {"@type": "ImageObject", "url": LOGO_URL}
        },
        "mainEntityOfPage": {
            "@type": "WebPage",
            "@id": PAGE_URL
        },
        "url": PAGE_URL
    }

    if media_url and media_type in ["photo", "image"]:
        json_ld_article["image"] = {
            "@type": "ImageObject",
            "url": media_url,
            "width": 1200,
            "height": 675
        }
        json_ld_article["thumbnailUrl"] = media_url

    if media_url and media_type == "video":
        json_ld_article["video"] = {
            "@type": "VideoObject",
            "name": title,
            "description": f"{THEME_DESC}: {post.get('text', '')[:500]}",
            "thumbnailUrl": thumbnail if thumbnail != DEFAULT_THUMBNAIL else "",
            "contentUrl": media_url,
            "embedUrl": media_url,
            "uploadDate": iso_time,
            "duration": "PT1M",
            "width": 1280,
            "height": 720,
            "publisher": {
                "@type": "NewsMediaOrganization",
                "name": "Новости для Своих"
            }
        }

    return html, json_ld_article


def update_history_html(html, json_ld_article):
    os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)

    if not os.path.exists(HISTORY_FILE):
        logging.error(f"{HISTORY_FILE} НЕ НАЙДЕН! Создай его вручную с <div id=\"history-container\">")
        return

    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            soup = BeautifulSoup(f, "html.parser")
    except Exception as e:
        logging.error(f"Ошибка чтения {HISTORY_FILE}: {e}")
        return

    container = soup.find("div", id="history-container")
    if not container:
        logging.error("Контейнер #history-container не найден в history.html")
        return

    # === ОЧИСТКА void-тегов от /> ===
    for tag in soup.find_all(['meta', 'link', 'img', 'input', 'br', 'hr']):
        if tag.string is None and str(tag).endswith('/>'):
            tag.name = tag.name
            tag.append('')

    container.insert(0, BeautifulSoup(html, "html.parser"))

    # === JSON-LD ===
    schema_script = soup.find("script", id="schema-org")
    if not schema_script:
        schema_script = soup.new_tag("script", type="application/ld+json", id="schema-org")
        soup.head.append(schema_script)

    try:
        schema_data = json.loads(schema_script.string or "{}") if schema_script.string else {
            "@context": "https://schema.org",
            "@type": "WebPage",
            "name": "История для Своих — события прошлых дней",
            "description": "Исторические события за последние дни — отражение прошлого для настоящего.",
            "url": PAGE_URL,
            "publisher": {
                "@type": "Organization",
                "name": "Новости для Своих",
                "logo": {"@type": "ImageObject", "url": "https://newsforsvoi.ru/pushkin-portrait.jpg", "width": 1200, "height": 630}
            },
            "mainEntity": {"@type": "ItemList", "itemListElement": []}
        }

        items = schema_data["mainEntity"]["itemListElement"]
        for item in items:
            if "position" in item:
                item["position"] += 1

        items.insert(0, {
            "@type": "ListItem",
            "position": 1,
            "item": json_ld_article
        })

        schema_script.string = json.dumps(schema_data, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.error(f"Ошибка JSON-LD: {e}")

    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            f.write(str(soup))
        logging.info("history.html обновлён")
    except Exception as e:
        logging.error(f"Ошибка записи {HISTORY_FILE}: {e}")


def generate_sitemap():
    lastmod = datetime.now().strftime("%Y-%m-%d")
    sitemap = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>{PAGE_URL}</loc>
    <lastmod>{lastmod}</lastmod>
    <changefreq>daily</changefreq>
    <priority>0.8</priority>
  </url>
</urlset>
"""
    os.makedirs(os.path.dirname(SITEMAP_FILE), exist_ok=True)
    with open(SITEMAP_FILE, "w", encoding="utf-8") as f:
        f.write(sitemap.strip())
    logging.info(f"Sitemap обновлён: {SITEMAP_FILE}")


def generate_rss():
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            soup = BeautifulSoup(f, "html.parser")

        items = soup.find_all("article", class_="news-item")[:20]
        last_build = datetime.now().strftime("%a, %d %b %Y %H:%M:%S +0300")

        rss = f'''<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>{THEME_TITLE} — {THEME_DESC}</title>
    <link>{PAGE_URL}</link>
    <description>Исторические события России и мира: что случилось в этот день.</description>
    <language>ru</language>
    <lastBuildDate>{last_build}</lastBuildDate>
    <atom:link href="{SITE_URL}/rss.xml" rel="self" type="application/rss+xml" />
'''

        for item in items:
            title_tag = item.find("h3") or item.find(class_="news-title")
            title = title_tag.get_text(strip=True) if title_tag else f"{THEME_DESC}: Историческое событие"
            desc_tag = item.find(class_="news-text")
            description = desc_tag.get_text(separator=" ", strip=True)[:500] if desc_tag else ""
            timestamp = item.find(class_="timestamp")
            pub_date = timestamp["data-ts"] if timestamp and "data-ts" in timestamp.attrs else datetime.now().isoformat()
            pub_date_rss = datetime.fromisoformat(pub_date.replace("Z", "+00:00")).astimezone().strftime("%a, %d %b %Y %H:%M:%S %z")

            media_tag = item.find("img") or item.find("video")
            enclosure = ""
            if media_tag:
                src = media_tag["src"]
                if src.endswith(('.jpg', '.jpeg', '.png', '.gif')):
                    enclosure = f'<enclosure url="{src}" length="0" type="image/jpeg" />'
                elif src.endswith(('.mp4', '.webm')):
                    enclosure = f'<enclosure url="{src}" length="0" type="video/mp4" />'

            rss += f'''
    <item>
      <title>{title}</title>
      <link>{PAGE_URL}</link>
      <description><![CDATA[{description}]]></description>
      <pubDate>{pub_date_rss}</pubDate>
      <guid isPermaLink="false">history-{pub_date}</guid>
      {enclosure}
    </item>'''

        rss += '''
  </channel>
</rss>'''

        os.makedirs(os.path.dirname(RSS_FILE), exist_ok=True)
        with open(RSS_FILE, "w", encoding="utf-8") as f:
            f.write(rss)
        logging.info(f"RSS обновлён: {RSS_FILE}")

    except Exception as e:
        logging.error(f"Ошибка генерации RSS: {e}")


def main():
    posts = load_posts()
    if not posts:
        logging.info("Новых постов нет")
        generate_sitemap()
        generate_rss()
        return

    for post in posts:
        html, json_ld = format_post(post)
        if html and json_ld:
            update_history_html(html, json_ld)
            logging.info(f"Добавлен пост: {post['title']}")

    save_posts()
    generate_sitemap()
    generate_rss()


# === ТОЛЬКО РУЧНОЙ ЗАПУСК ===
if __name__ == "__main__":
    logging.info("Запуск обработки постов (ручной режим)")
    try:
        main()
    except Exception as e:
        logging.error(f"Критическая ошибка: {e}")