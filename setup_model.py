import os
import subprocess
from transformers import T5Tokenizer, T5ForConditionalGeneration

MODEL_NAME = "cointegrated/rut5-base-paraphraser"
MODEL_DIR = "models/rut5-base"

print("Установка Git LFS...", flush=True)
try:
    subprocess.run(["git", "lfs", "install"], check=True, capture_output=True)
except:
    pass

print(f"Создаю папку {MODEL_DIR}...", flush=True)
os.makedirs(MODEL_DIR, exist_ok=True)

print(f"Скачиваю модель {MODEL_NAME}...", flush=True)
tokenizer = T5Tokenizer.from_pretrained(MODEL_NAME)
model = T5ForConditionalGeneration.from_pretrained(MODEL_NAME)

print(f"Сохраняю в {MODEL_DIR}...", flush=True)
model.save_pretrained(MODEL_DIR)
tokenizer.save_pretrained(MODEL_DIR)

# LFS
lfs_lines = [
    f"{MODEL_DIR}/*.bin filter=lfs diff=lfs merge=lfs -text",
    f"{MODEL_DIR}/*.json filter=lfs diff=lfs merge=lfs -text",
    f"{MODEL_DIR}/*.txt filter=lfs diff=lfs merge=lfs -text"
]

try:
    with open(".gitattributes", "r", encoding="utf-8") as f:
        existing = f.read()
except FileNotFoundError:
    existing = ""

with open(".gitattributes", "a", encoding="utf-8") as f:
    for line in lfs_lines:
        if line not in existing:
            f.write(line + "\n")

print("Добавляю в Git...", flush=True)
subprocess.run(["git", "add", MODEL_DIR], check=True)
subprocess.run(["git", "add", ".gitattributes"], check=True)

try:
    subprocess.run(["git", "commit", "-m", "feat: add rut5-base model (LFS)"], check=True, capture_output=True)
    print("Коммит создан", flush=True)
except:
    print("Нечего коммитить", flush=True)

print("Пушу...", flush=True)
push = subprocess.run(["git", "push"], capture_output=True, text=True)
if push.returncode == 0:
    print("УСПЕШНО ЗАПУШЕНО!", flush=True)
else:
    print("Ошибка пуша:", flush=True)
    print(push.stderr, flush=True)

print("\nГотово! Запускай: python bot/bot.py", flush=True)