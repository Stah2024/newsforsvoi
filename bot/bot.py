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
moscow = pytz.timezone('Europe/Moscow')

# ... [все функции: clean_text, load_seen_ids, format_post и т.д.]

def generate_rss(fresh_news):
    rss_items = ""
    for block in fresh_news:
        title_match = re.search(r"<p>(.*?)</p>", block)
        link_match = re.search(r"<a href='(https://t\.me/[^']+)'", block)
        date_match = re.search(r"data-ts='([^']+)'", block)

        title = title_match.group(1) if title_match else "Без заголовка"
        link = link_match.group(1) if link_match else "https://t.me/newsSVOih"
        pub_date = datetime.strptime(date_match.group(1), "%Y-%m-%dT%H:%M:%S").strftime("%a, %d %b %Y %H:%M:%S +0300") if date_match else ""

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
    grouped = {}
    for post in posts:
        key = getattr(post, "media_group_id", None) or post.message_id
        grouped.setdefault(str(key), []).append(post)

    visible_limit = 12
    visible_count = sum(1 for block in fresh_news if "hidden" not in block)
    any_new = False

    archive_file = open("public/archive.html", "a", encoding="utf-8")
    retained_news = []
    for block in fresh_news:
        ts = extract_timestamp(block)
        block_hash = hash_html_block(block)
        if ts and is_older_than_two_days(ts.timestamp()):
            if block_hash not in seen_html_hashes:
                media_paths = re.findall(r"src=['\"](.*?)['\"]", block)
                for path in media_paths:
                    local_path = os.path.join("public", os.path.basename(path))
                    if os.path.exists(local_path):
                        try:
                            os.remove(local_path)
                            print(f"🧹 Удалён медиафайл: {local_path}")
                        except Exception as e:
                            print(f"⚠️ Не удалось удалить {local_path}: {e}")

                link_match = re.search(r"<a href='(https://t\.me/[^']+)'", block)
                caption_match = re.search(r"<p>(.*?)</p>", block)
                date_str = ts.strftime("%d.%m.%Y")
                caption = caption_match.group(1) if caption_match else "Без описания"

                if link_match:
                    link = link_match.group(1)
                    preview_html = f"""
<article class='news-preview'>
  <p>🗓 {date_str}</p>
  <p>📎 {caption}</p>
  <a href='{link}' target='_blank'>Смотреть в Telegram</a>
</article>
"""
                    archive_file.write(preview_html + "\n")
                    seen_html_hashes.add(block_hash)
        else:
            retained_news.append(block)
    archive_file.close()
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
        if html_hash in seen_html_hashes:
            continue
        if html in fresh_news:
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
