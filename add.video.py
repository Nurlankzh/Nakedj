import os
import sqlite3
from telebot import TeleBot

# 🔑 Бот мәліметтері
BOT_TOKEN = "8419149602:AAHvLF3XmreCAQpvJy_8-RRJDH0g_qy9Oto"
ADMIN_ID = 6927494520

# 🔹 Ботты қосу
bot = TeleBot(BOT_TOKEN)

# 📦 Деректер базасына қосылу
conn = sqlite3.connect("data.db", check_same_thread=False)
cursor = conn.cursor()

# 📂 videos_files қалтасын жасау
VIDEO_DIR = os.path.join(os.getcwd(), "videos_files")
os.makedirs(VIDEO_DIR, exist_ok=True)

# 🎥 Админ видео қосу функциясы
def add_video(message):
    if message.from_user.id != ADMIN_ID:
        return  # Тек админ ғана видео жібере алады

    # Видео файлын жүктеу
    file_info = bot.get_file(message.video.file_id)
    downloaded_file = bot.download_file(file_info.file_path)
    file_name = os.path.join(VIDEO_DIR, f"{message.video.file_id}.mp4")

    with open(file_name, 'wb') as f:
        f.write(downloaded_file)

    # Деректер базасына сақтау
    cursor.execute("INSERT INTO videos (file_id, file_name) VALUES (?, ?)",
                   (message.video.file_id, file_name))
    conn.commit()

    # Қолданушыға хабар беру
    total = cursor.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
    bot.send_message(message.chat.id, f"✅ Видео сақталды! Барлығы: {total} 🎥")

# 🔹 Деректер базасындағы видеоларды тексеру (тест)
def list_videos():
    videos = cursor.execute("SELECT file_id FROM videos").fetchall()
    print("Videos in DB:", videos)
