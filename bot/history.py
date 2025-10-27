import os
import logging
from datetime import datetime

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("history.log"),
        logging.StreamHandler()
    ]
)

SITEMAP_FILE = "public/sitemap.xml"

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

if __name__ == "__main__":
    logging.info("Запуск обновления sitemap.xml для history.html")
    try:
        generate_sitemap()
    except Exception as e:
        logging.error(f"Ошибка при обновлении sitemap.xml: {e}")