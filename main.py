import os
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

# ---------------- Logging ----------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ---------------- Bot & Flask ----------------
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
    progress INTEGER DEFAULT 0,
    referrals TEXT DEFAULT ''
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

# ---------------- Daily bonus ----------------
def daily_bonus():
    while True:
        try:
            with db_lock:
                cursor.execute("UPDATE users SET bonus = bonus + 5")
                conn.commit()
                users = [u[0] for u in cursor.execute("SELECT user_id FROM users").fetchall()]
            for uid in users:
                try:
                    bot.send_message(uid, "🎁 Күнделікті +5 бонус берілді!")
                except Exception:
                    pass
        except Exception as e:
            logger.exception(f"daily_bonus error: {e}")
        time.sleep(86400)  # 24 сағат

threading.Thread(target=daily_bonus, daemon=True).start()

# ---------------- Helpers ----------------
def get_main_markup(user_id):
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("🎥 Видео")
    markup.add("👥 Реферал алу")
    markup.add("📢 Каналымызға қосылу", "🛍 Канал алу")
    if user_id == ADMIN_ID:
        markup.add("📊 Статистика", "🗑 Видеоларды өшіру", "📩 Рассылка")
    return markup

def save_video_file_from_message(message):
    file_id = message.video.file_id
    file_info = bot.get_file(file_id)
    downloaded = bot.download_file(file_info.file_path)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
    safe_name = f"{ts}_{file_id}.mp4"
    file_path = os.path.join(VIDEO_DIR, safe_name)
    with open(file_path, "wb") as f:
        f.write(downloaded)
    return file_id, file_path

# ---------------- Handlers ----------------
@bot.message_handler(commands=['start'])
def handle_start(message):
    user_id = message.from_user.id
    args = message.text.split()
    ref = args[1] if len(args) > 1 else None
    with db_lock:
        exists = cursor.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,)).fetchone()
        if not exists:
            cursor.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
            conn.commit()
            bot.send_message(user_id, "🎉 Қош келдіңіз! +5 бонус берілді.", reply_markup=get_main_markup(user_id))
            if ref and ref.isdigit() and int(ref) != user_id:
                ref_exists = cursor.execute("SELECT 1 FROM users WHERE user_id = ?", (int(ref),)).fetchone()
                if ref_exists:
                    cursor.execute("UPDATE users SET bonus = bonus + 5, referrals = referrals || ? || ',' WHERE user_id = ?",
                                   (str(user_id), int(ref)))
                    conn.commit()
                    try:
                        bot.send_message(int(ref), "🎁 Сіз жаңа қолданушы шақырдыңыз! +5 бонус ✅")
                    except:
                        pass
            return
    bot.send_message(user_id, "Қайта қосылдыңыз — басты мәзір.", reply_markup=get_main_markup(user_id))

@bot.message_handler(func=lambda m: m.text and "Видео" in m.text)
def handle_watch(message):
    user_id = message.from_user.id
    with db_lock:
        user = cursor.execute("SELECT bonus, progress FROM users WHERE user_id = ?", (user_id,)).fetchone()
        videos = cursor.execute("SELECT id, file_id, file_path FROM videos ORDER BY id ASC").fetchall()
    if not videos:
        bot.send_message(user_id, "🎬 Қазір видеолар жоқ. Админге хабарласыңыз.")
        return
    bonus, progress = user
    if bonus <= 0:
        bot.send_message(user_id, "❌ Сіздің бонусыңыз жоқ.")
        return
    if progress >= len(videos):
        progress = 0
    video_row = videos[progress]
    file_id, file_path = video_row[1], video_row[2]
    try:
        if file_path and os.path.exists(file_path):
            with open(file_path, "rb") as vf:
                bot.send_video(user_id, vf)
        else:
            bot.send_video(user_id, file_id)
    except Exception as e:
        logger.exception(f"Video send error {user_id}: {e}")
        bot.send_message(user_id, "❌ Видео жіберу қатесі.")
        return
    with db_lock:
        cursor.execute("UPDATE users SET bonus = ?, progress = ? WHERE user_id = ?",
                       (max(bonus - 1, 0), progress + 1, user_id))
        conn.commit()
    bot.send_message(user_id, f"✅ Видео көрсетілді! Қалған бонус: {max(bonus - 1, 0)}")

@bot.message_handler(func=lambda m: m.text and "Реферал" in m.text)
def handle_referral(message):
    user_id = message.from_user.id
    ref_link = f"https://t.me/{bot.get_me().username}?start={user_id}"
    bot.send_message(user_id, f"🔗 Сіздің сілтемеңіз:\n{ref_link}\nӘр шақырған адам үшін +5 бонус 🎁")

@bot.message_handler(func=lambda m: m.text and "Каналымызға қосылу" in m.text)
def handle_join_channel(message):
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("🔙 Басты мәзірге оралу")
    bot.send_message(message.chat.id,
                     "Каналдарға қосылыңыз:\n\nhttps://t.me/Qazhuboyndar\nhttps://t.me/+XRoxE_8bUM1mMmIy",
                     reply_markup=markup)

@bot.message_handler(func=lambda m: m.text and "Басты мәзірге оралу" in m.text)
def handle_back_main(message):
    bot.send_message(message.chat.id, "Басты мәзірге оралу", reply_markup=get_main_markup(message.from_user.id))

# ---------------- Admin: video upload ----------------
@bot.message_handler(content_types=['video'])
def handle_incoming_video(message):
    if message.from_user.id != ADMIN_ID:
        bot.send_message(message.chat.id, "Рұқсат жоқ.")
        return
    try:
        file_id, file_path = save_video_file_from_message(message)
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Видео сақталмады: {e}")
        return
    with db_lock:
        cursor.execute("INSERT INTO videos (file_id, file_path, created_at) VALUES (?, ?, ?)",
                       (file_id, file_path, datetime.utcnow().isoformat()))
        conn.commit()
        total = cursor.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
    bot.send_message(message.chat.id, f"✅ Видео сақталды! Барлығы: {total} 🎥")

# ---------------- Webhook ----------------
@app.route(f"/{BOT_TOKEN}", methods=['POST'])
def webhook():
    try:
        update = telebot.types.Update.de_json(request.stream.read().decode('utf-8'))
        bot.process_new_updates([update])
    except Exception as e:
        logger.exception(f"Webhook error: {e}")
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
    logger.info("Starting Flask server...")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
