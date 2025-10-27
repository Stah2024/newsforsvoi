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
POSTS_FILE = "bot/posts.txt"

def load_posts():
    if not os.path.exists(POSTS_FILE):
        logging.warning(f"{POSTS_FILE} не найден, создаём пустой")
        with open(POSTS_FILE, "w", encoding="utf-8") as f:
            f.write("")
        return []
    try:
        with open(POSTS_FILE, "r", encoding="utf-8") as f:
            content = f.read().strip()
        if not content:
            return []
        posts = []
        for post_text in content.split("---\n"):
            post_text = post_text.strip()
            if not post_text:
                continue
            post = {}
            title_match = re.search(r"TITLE: (.*?)(?=\nTEXT:|\n---|$)", post_text, re.DOTALL)
            text_match = re.search(r"TEXT: (.*?)(?=\nTIME:|\n---|$)", post_text, re.DOTALL)
            time_match = re.search(r"TIME: (.*?)(?=\nDATE:|\n---|$)", post_text, re.DOTALL)
            date_match = re.search(r"DATE: (.*?)(?=\nMEDIA_URL:|\n---|$)", post_text, re.DOTALL)
            media_url_match = re.search(r"MEDIA_URL: (.*?)(?=\nMEDIA_TYPE:|\n---|$)", post_text, re.DOTALL)
            media_type_match = re.search(r"MEDIA_TYPE: (.*?)(?=\n---|$)", post_text, re.DOTALL)
            post["title"] = title_match.group(1).strip() if title_match else "Историческое событие"
            post["text"] = text_match.group(1).strip() if text_match else ""
            post["iso_time"] = time_match.group(1).strip() if time_match else datetime.now().strftime("%Y-%m-%dT%H:%M:%S+03:00")
            post["date"] = date_match.group(1).strip() if date_match else datetime.now().strftime("%d.%m.%Y %H:%M")
            post["media_url"] = media_url_match.group(1).strip() if media_url_match and media_url_match.group(1).strip() else ""
            post["media_type"] = media_type_match.group(1).strip() if media_type_match and media_type_match.group(1).strip() else ""
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
    html += f"<div class='timestamp' data-ts='{iso_time}'>🕒 {formatted_time}</div>\n"
    html += "</article>\n"

    json_ld_article = {
        "@type": "NewsArticle",
        "headline": title[:200],
        "description": text[:500],
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
    except Exception as e:
        logging.error(f"Ошибка чтения {HISTORY_FILE}: {e}")
        return

    container = soup.find("div", id="history-container")
    if container:
        container.insert(0, BeautifulSoup(html, "html.parser"))
    else:
        logging.error("Контейнер #history-container не найден")
        return

    schema_script = soup.find("script", id="schema-org")
    if schema_script and json_ld_article:
        try:
            schema_data = json.loads(schema_script.string)
            current_positions = {item["position"]: item for item in schema_data["mainEntity"]["itemListElement"]}
            new_positions = []
            new_positions.append({
                "@type": "ListItem",
                "position": 1,
                "item": json_ld_article
            })
            for pos in sorted(current_positions.keys()):
                item = current_positions[pos]
                item["position"] = pos + 1
                new_positions.append(item)
            schema_data["mainEntity"]["itemListElement"] = new_positions
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

def main():
    posts = load_posts()
    if not posts:
        logging.info("Новых постов нет")
        generate_sitemap()
        return

    for post in posts:
        html, json_ld = format_post(post)
        if html and json_ld:
            update_history_html(html, json_ld)
            logging.info(f"Добавлен пост: {post['title']}")

    save_posts()
    generate_sitemap()

if __name__ == "__main__":
    logging.info("Запуск обработки постов")
    try:
        main()
    except Exception as e:
        logging.error(f"Критическая ошибка: {e}")