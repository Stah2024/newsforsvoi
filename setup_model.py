# setup_model.py
# Запусти из корня репо: python setup_model.py
# Работает с bot/bot.py

import os
import subprocess
from transformers import T5Tokenizer, T5ForConditionalGeneration

MODEL_NAME = "cointegrated/rut5-base-paraphraser"
MODEL_DIR = "models/rut5-base"  # в корне репо

print("Установка Git LFS...")
try:
    subprocess.run(["git", "lfs", "install"], check=True, capture_output=True)
except:
    pass

print(f"Создаю папку {MODEL_DIR}...")
os.makedirs(MODEL_DIR, exist_ok=True)

print(f"Скачиваю модель {MODEL_NAME}...")
tokenizer = T5Tokenizer.from_pretrained(MODEL_NAME)
model = T5ForConditionalGeneration.from_pretrained(MODEL_NAME)

print(f"Сохраняю в {MODEL_DIR}...")
model.save_pretrained(MODEL_DIR)
tokenizer.save_pretrained(MODEL_DIR)

# LFS
lfs_lines = [
    f"{MODEL_DIR}/*.bin filter=lfs diff=lfs merge=lfs -text",
    f"{MODEL_DIR}/*.json filter=lfs diff=lfs merge=lfs -text",
    f"{MODEL_DIR}/*.txt filter=lfs diff=lfs merge=lfs -text"
]

with open(".gitattributes", "a", encoding="utf-8") as f:
    existing = f.read()
    for line in lfs_lines:
        if line not in existing:
            f.write(line + "\n")

# Git
print("Добавляю в Git...")
subprocess.run(["git", "add", MODEL_DIR], check=True)
subprocess.run(["git", "add", ".gitattributes"], check=True)

try:
    subprocess.run(["git", "commit", "-m", "feat: add rut5-base model (LFS)"], check=True, capture_output=True)
    print("Коммит создан")
except:
    print("Нечего коммитить")

print("Пушу...")
push = subprocess.run(["git", "push"], capture_output=True, text=True)
if push.returncode == 0:
    print("УСПЕШНО ЗАПУШЕНО!")
else:
    print("Ошибка пуша:")
    print(push.stderr)

print("\nГотово! Запускай: python bot/bot.py")