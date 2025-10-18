import os
import re
import json
import time
import requests
from datetime import datetime, timedelta

NEWS_DIR = "public/news"
ARCHIVE_FILE = os.path.join(NEWS_DIR, "archive.html")

def extract_timestamp(block):
    match = re.search(r"datetime='([^']+)'", block)
    if match:
        try:
            return datetime.fromisoformat(match.group(1).replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def format_post(caption, text, iso_time, file_url=None):
    html = "<article class='news'>\n"
    html += f"<time datetime='{iso_time}'>{iso_time}</time>\n"

    if caption:
        html += f"<h2>{caption}</h2>\n"
    if text:
        html += f"<p>{text}</p>\n"
    if file_url:
        html += f"<img src='{file_url}' alt='news image'>\n"

    # JSON-LD микроразметка
    microdata = {
        "@context": "https://schema.org",
        "@type": "NewsArticle",
        "headline": caption or text or "Новость",
        "datePublished": iso_time + "+03:00",
        "author": {
            "@type": "Organization",
            "name": "Новости для Своих"
        },
        "publisher": {
            "@type": "Organization",
            "name": "Новости для Своих",
            "logo": {
                "@type": "ImageObject",
                "url": "https://newsforsvoi.ru/logo.png"
            }
        },
        "articleBody": (caption + "\n" + text).strip()
    }

    if file_url:
        microdata["image"] = file_url

    html += f"<script type='application/ld+json'>\n{json.dumps(microdata, ensure_ascii=False)}\n</script>\n"
    html += "</article>\n"

    return html


def clean_old_media():
    """Удаляет медиафайлы старше 2 дней и переносит их в архив в виде ссылок"""
    now = datetime.now()
    cutoff = now - timedelta(days=2)

    if not os.path.exists(NEWS_DIR):
        print("❌ Папка с новостями не найдена.")
        return

    if not os.path.exists(ARCHIVE_FILE):
        with open(ARCHIVE_FILE, "w", encoding="utf-8") as f:
            f.write("<h2>Архив новостей</h2>\n")

    with open(ARCHIVE_FILE, "a", encoding="utf-8") as archive_file:
        for filename in os.listdir(NEWS_DIR):
            file_path = os.path.join(NEWS_DIR, filename)
            if os.path.isfile(file_path) and not filename.endswith(".html"):
                mtime = datetime.fromtimestamp(os.path.getmtime(file_path))
                if mtime < cutoff:
                    try:
                        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                            block = f.read()
                        link_match = re.search(r"<a href='(https://t\.me/[^']+)'", block)
                        caption_match = re.search(r"<p>(.*?)</p>", block)
                        timestamp = extract_timestamp(block)

                        media_paths = re.findall(r"src=['\"](.*?)['\"]", block)
                        for path in media_paths:
                            local_path = os.path.join("public", os.path.basename(path))
                            if os.path.exists(local_path):
                                os.remove(local_path)
                                print(f"🧹 Удалён медиафайл: {local_path}")

                        if link_match and timestamp:
                            link = link_match.group(1)
                            date_str = timestamp.strftime("%d.%m.%Y")
                            caption = caption_match.group(1) if caption_match else "Без описания"
                            preview_html = f"""
<article class='news-preview'>
  <p>🗓 {date_str}</p>
  <p>📎 {caption}</p>
  <a href='{link}' target='_blank'>Смотреть в Telegram</a>
</article>
"""
                            archive_file.write(preview_html + "\n")

                        os.remove(file_path)
                        print(f"✅ Файл {filename} удалён и добавлен в архив.")
                    except Exception as e:
                        print(f"⚠️ Ошибка при обработке {filename}: {e}")


def main():
    print("🚀 Запуск скрипта...")
    clean_old_media()
    print("🧹 Очистка завершена.")


if __name__ == "__main__":
    main()