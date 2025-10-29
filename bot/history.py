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
        # Разделяем по --- (учитываем \n или просто ---)
        raw_posts = [p.strip() for p in re.split(r"\n?---\n?", content) if p.strip()]

        for post_text in raw_posts:
            post = {
                "title": "Историческое событие",
                "text": "",
                "iso_time": datetime.now().strftime("%Y-%m-%dT%H:%M:%S+03:00"),
                "date": datetime.now().strftime("%d.%m.%Y %H:%M"),
                "media_url": "",
                "media_type": ""
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
                    field_lines = []

                elif line.startswith("DATE:"):
                    if current_field:
                        post[current_field] = "\n".join(field_lines).strip()
                    post["date"] = line[6:].strip()
                    current_field = None
                    field_lines = []

                elif line.startswith("MEDIA_URL:"):
                    if current_field:
                        post[current_field] = "\n".join(field_lines).strip()
                    post["media_url"] = line[11:].strip()
                    current_field = None
                    field_lines = []

                elif line.startswith("MEDIA_TYPE:"):
                    if current_field:
                        post[current_field] = "\n".join(field_lines).strip()
                    post["media_type"] = line[12:].strip()
                    current_field = None
                    field_lines = []

                elif current_field:
                    field_lines.append(line)

            if current_field:
                post[current_field] = "\n".join(field_lines).strip()

            if not post["title"] and not post["text"]:
                continue

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
    title = post.get("title", "Историческое событие")
    text = post.get("text", "").replace("\n", "<br>")
    iso_time = post.get("iso_time", datetime.now().strftime("%Y-%m-%dT%H:%M:%S+03:00"))
    formatted_time = post.get("date", datetime.now().strftime("%d.%m.%Y %H:%M"))
    media_url = post.get("media_url", "")
    media_type = post.get("media_type", "")

    html = "<article class='news-item'>\n"
    html += "<span class='category-badge'>История</span>\n"

    if media_url and media_type == "photo":
        html += f"<img src='{media_url}' alt='Фото события' class='news-image' />\n"
    elif media_url and media_type == "video":
        html += f"<video controls src='{media_url}' class='news-image'></video>\n"

    html += f"<p><b class='news-title'>{title}</b></p>\n"
    html += f"<p class='news-text'>{text}</p>\n"
    html += f"<div class='timestamp' data-ts='{iso_time}'>  {formatted_time}</div>\n"
    html += "</article>\n"

    json_ld_article = {
        "@type": "NewsArticle",
        "headline": title[:200],
        "description": post.get("text", "")[:500],
        "datePublished": iso_time,
        "author": {"@type": "Organization", "name": "SVOih History Team"},
        "publisher": {
            "@type": "Organization",
            "name": "Новости для Своих",
            "logo": {"@type": "ImageObject", "url": "https://newsforsvoi.ru/logo.png"}
        },
        "url": "https://newsforsvoi.ru/history.html"
    }

    if media_url and media_type == "photo":
        json_ld_article["image"] = {
            "@type": "ImageObject",
            "url": media_url,
            "width": 800,
            "height": 600
        }
    elif media_url and media_type == "video":
        json_ld_article["video"] = {
            "@type": "VideoObject",
            "contentUrl": media_url,
            "uploadDate": iso_time
        }

    return html, json_ld_article


def update_history_html(html, json_ld_article):
    os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            soup = BeautifulSoup(f, "html.parser")
    except FileNotFoundError:
        logging.error(f"{HISTORY_FILE} не найден!")
        return
    except Exception as e:
        logging.error(f"Ошибка чтения {HISTORY_FILE}: {e}")
        return

    container = soup.find("div", id="history-container")
    if not container:
        logging.error("Контейнер #history-container не найден")
        return

    container.insert(0, BeautifulSoup(html, "html.parser"))

    schema_script = soup.find("script", id="schema-org")
    if schema_script and json_ld_article:
        try:
            schema_data = json.loads(schema_script.string or "{}")
            if "mainEntity" not in schema_data:
                schema_data["mainEntity"] = {"@type": "ItemList", "itemListElement": []}

            items = schema_data["mainEntity"]["itemListElement"]
            for item in items:
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
    except Exception as e:
        logging.error(f"Ошибка записи {HISTORY_FILE}: {e}")


def generate_sitemap():
    lastmod = datetime.now().strftime("%Y-%m-%d")
    sitemap = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://newsforsvoi.ru/history.html</loc>
    <lastmod>{lastmod}</lastmod>
    <changefreq>daily</changefreq>
    <priority>0.8</priority>
  </url>
</urlset>
"""
    os.makedirs(os.path.dirname(SITEMAP_FILE), exist_ok=True)
    with open(SITEMAP_FILE, "w", encoding="utf-8") as f:
        f.write(sitemap)
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
    <title>История для Своих — события прошлых дней</title>
    <link>https://newsforsvoi.ru/history.html</link>
    <description>Исторические события за последние дни — отражение прошлого для настоящего.</description>
    <language>ru</language>
    <lastBuildDate>{last_build}</lastBuildDate>
    <atom:link href="https://newsforsvoi.ru/rss.xml" rel="self" type="application/rss+xml" />
'''

        for item in items:
            title_tag = item.find(class_="news-title")
            title = title_tag.get_text(strip=True) if title_tag else "Историческое событие"
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
      <link>https://newsforsvoi.ru/history.html</link>
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


if __name__ == "__main__":
    logging.info("Запуск обработки постов")
    try:
        main()
    except Exception as e:
        logging.error(f"Критическая ошибка: {e}")