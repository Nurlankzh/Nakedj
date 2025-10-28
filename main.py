                       (max(bonus - 1, 0), progress + 1, user_import os
import time
import logging
import sqlite3
import threading
from datetime import datetime
from flask import Flask, request
import telebot

# ---------------- Config ----------------
BOT_TOKEN = "8419149602:AAHvLF3XmreCAQpvJy_8-RRJDH0g_qy9Oto"
ADMIN_ID = 6927494520
WEBHOOK_URL = "https://nakedj-5.onrender.com"

VIDEO_DIR = os.environ.get("VIDEO_DIR", "videos_files")
os.makedirs(VIDEO_DIR, exist_ok=True)

DB_FILE = os.environ.get("DB_FILE", "data.db")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

bot = telebot.TeleBot(BOT_TOKEN, parse_mode=None)
app = Flask(__name__)

# ---------------- Database ----------------
conn = sqlite3.connect(DB_FILE, check_same_thread=False)
cursor = conn.cursor()
db_lock = threading.Lock()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    bonus INTEGER DEFAULT 5,
    progress INTEGER DEFAULT 0
)
""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS videos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id TEXT,
    file_path TEXT,
    created_at TEXT
)
""")
conn.commit()

# ---------------- Helpers ----------------
def get_main_markup(user_id):
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(telebot.types.KeyboardButton("🎥 Видео"))
    if user_id == ADMIN_ID:
        markup.add(telebot.types.KeyboardButton("🗑 Видеоларды өшіру"))
    return markup

def save_video_file(message):
    file_id = message.video.file_id
    try:
        file_info = bot.get_file(file_id)
        downloaded = bot.download_file(file_info.file_path)
    except Exception as e:
        logger.exception(f"Error downloading file_id {file_id}: {e}")
        raise

    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
    safe_name = f"{ts}_{file_id}.mp4"
    file_path = os.path.join(VIDEO_DIR, safe_name)

    with open(file_path, "wb") as f:
        f.write(downloaded)

    return file_id, file_path

# ---------------- Start / Register ----------------
@bot.message_handler(commands=['start'])
def handle_start(message):
    user_id = message.from_user.id
    with db_lock:
        exists = cursor.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,)).fetchone()
        if not exists:
            cursor.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
            conn.commit()
    bot.send_message(user_id, "Қош келдіңіз!", reply_markup=get_main_markup(user_id))

# ---------------- Video Watch ----------------
@bot.message_handler(func=lambda m: m.text == "🎥 Видео")
def handle_watch(message):
    user_id = message.from_user.id
    with db_lock:
        cursor.execute("SELECT progress FROM users WHERE user_id = ?", (user_id,))
        res = cursor.fetchone()
        progress = res[0] if res else 0
        cursor.execute("SELECT id, file_id, file_path FROM videos ORDER BY id ASC")
        videos = cursor.fetchall()

    if not videos:
        bot.send_message(user_id, "🎬 Қазір видеолар жоқ. Админге хабарласыңыз.")
        return

    if progress >= len(videos):
        progress = 0  # reset

    video = videos[progress]
    file_id = video[1]
    file_path = video[2]

    try:
        if file_path and os.path.exists(file_path):
            with open(file_path, "rb") as vf:
                bot.send_video(user_id, vf)
        else:
            bot.send_video(user_id, file_id)
    except Exception as e:
        logger.exception(f"Error sending video to {user_id}: {e}")
        bot.send_message(user_id, "❌ Видео жіберілгенде қате болды.")
        return

    with db_lock:
        cursor.execute("UPDATE users SET progress = ? WHERE user_id = ?", (progress + 1, user_id))
        conn.commit()

# ---------------- Admin: Video Upload ----------------
@bot.message_handler(content_types=['video'])
def handle_incoming_video(message):
    if message.from_user.id != ADMIN_ID:
        bot.send_message(message.chat.id, "Рұқсат жоқ.")
        return

    try:
        file_id, file_path = save_video_file(message)
    except Exception as e:
        logger.exception("Failed to save incoming video")
        bot.send_message(message.chat.id, f"❌ Видео сақталмады: {e}")
        return

    with db_lock:
        cursor.execute("INSERT INTO videos (file_id, file_path, created_at) VALUES (?, ?, ?)",
                       (file_id, file_path, datetime.utcnow().isoformat()))
        conn.commit()
        total = cursor.execute("SELECT COUNT(*) FROM videos").fetchone()[0]

    bot.send_message(message.chat.id, f"✅ Видео сақталды! Барлығы: {total} 🎥")

# ---------------- Admin: Delete All Videos ----------------
@bot.message_handler(func=lambda m: m.text == "🗑 Видеоларды өшіру" and m.from_user.id == ADMIN_ID)
def delete_all_videos(message):
    with db_lock:
        rows = cursor.execute("SELECT file_path FROM videos").fetchall()
        for r in rows:
            if r[0] and os.path.exists(r[0]):
                os.remove(r[0])
        cursor.execute("DELETE FROM videos")
        cursor.execute("UPDATE users SET progress = 0")
        conn.commit()
    bot.send_message(message.chat.id, "✅ Барлық видеолар өшірілді!")

# ---------------- Webhook ----------------
@app.route(f"/{BOT_TOKEN}", methods=['POST'])
def webhook():
    try:
        update = telebot.types.Update.de_json(request.stream.read().decode('utf-8'))
        bot.process_new_updates([update])
    except Exception as e:
        logger.exception(f"Webhook processing error: {e}")
    return "ok", 200

@app.route("/")
def index():
    try:
        bot.remove_webhook()
        bot.set_webhook(url=f"{WEBHOOK_URL}/{BOT_TOKEN}")
        return "Bot is live ✅", 200
    except Exception as e:
        logger.exception("Failed to set webhook")
        return f"Webhook error: {e}", 500

if __name__ == "__main__":
    logger.info("Starting Flask server for webhook...")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
