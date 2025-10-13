import os
import telebot
from datetime import datetime

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHANNEL_ID = "@newsSVOih"

bot = telebot.TeleBot(TOKEN)

def clean_text(text):
    return text.replace("https://t.me/newsSVOih", "").strip()

def fetch_latest_posts():
    updates = bot.get_updates()
    posts = [
        u.channel_post
        for u in updates
        if u.channel_post and u.channel_post.chat.username == CHANNEL_ID[1:]
    ]
    return posts[-5:] if posts else []

def format_post(message):
    html = "<article class='news-item'>\n"
    if message.content_type == 'text':
        html += f"<p>{clean_text(message.text)}</p>\n"
    elif message.content_type == 'photo':
        file_info = bot.get_file(message.photo[-1].file_id)
        file_url = f"https://api.telegram.org/file/bot{TOKEN}/{file_info.file_path}"
        caption = clean_text(message.caption or "")
        html += f"<img src='{file_url}' alt='Фото' />\n"
        html += f"<p>{caption}</p>\n"
    html += f"<a href='https://t.me/newsSVOih/{message.message_id}' target='_blank'>Читать в Telegram</a>\n"
    html += f"<p class='source'>Источник: {message.chat.title}</p>\n"
    html += "</article>\n"
    return html

def main():
    posts = fetch_latest_posts()
    os.makedirs("public", exist_ok=True)
    with open("public/news.html", "w", encoding="utf-8") as f:
        if not posts:
            f.write(f"<p>Нет новых постов — {datetime.now()}</p>")
        else:
            for post in posts:
                f.write(format_post(post))

# ✅ ВАЖНО: правильная форма запуска
if __name__ == "__main__":
    main()
