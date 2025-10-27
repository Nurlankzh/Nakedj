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
# Use your Render service URL here (no trailing slash)
WEBHOOK_URL = "https://nakedj-5.onrender.com"

# Persistent dir: if Render attached disk path set as env, use it; else use local folder
VIDEO_DIR = os.environ.get("VIDEO_DIR", "videos_files")
os.makedirs(VIDEO_DIR, exist_ok=True)

# DB file
DB_FILE = os.environ.get("DB_FILE", "data.db")

# ---------------- Logging ----------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ---------------- Bot & Flask ----------------
bot = telebot.TeleBot(BOT_TOKEN, parse_mode=None)
app = Flask(__name__)

# ---------------- Database ----------------
# Allow connections from multiple threads
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

# ---------------- Daily bonus thread ----------------
def daily_bonus():
    while True:
        try:
            with db_lock:
                cursor.execute("UPDATE users SET bonus = bonus + 5")
                conn.commit()
                users = [u[0] for u in cursor.execute("SELECT user_id FROM users").fetchall()]
            for uid in users:
                try:
                    bot.send_message(uid, "🎁 Күнделікті +5 бонус сізге берілді!")
                except Exception as e:
                    logger.debug(f"Failed to send daily bonus msg to {uid}: {e}")
        except Exception as e:
            logger.exception(f"daily_bonus error: {e}")
        time.sleep(86400)  # 24h

threading.Thread(target=daily_bonus, daemon=True).start()

# ---------------- Helpers ----------------
def get_main_markup(user_id):
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(telebot.types.KeyboardButton("🎥 Видео"))
    markup.add(telebot.types.KeyboardButton("👥 Реферал алу"))
    markup.add(telebot.types.KeyboardButton("📢 Каналымызға қосылу"),
               telebot.types.KeyboardButton("🛍 Канал алу"))
    if user_id == ADMIN_ID:
        markup.add(telebot.types.KeyboardButton("📊 Статистика"),
                   telebot.types.KeyboardButton("🗑 Видеоларды өшіру"),
                   telebot.types.KeyboardButton("📩 Рассылка"))
    return markup

def save_video_file_from_message(message):
    """Download video bytes and save to VIDEO_DIR; return (file_id, file_path)."""
    file_id = message.video.file_id
    try:
        file_info = bot.get_file(file_id)
        downloaded = bot.download_file(file_info.file_path)
    except Exception as e:
        logger.exception(f"Error downloading file_id {file_id}: {e}")
        raise

    # unique filename: timestamp + file_id (safe)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
    safe_name = f"{ts}_{file_id}.mp4"
    file_path = os.path.join(VIDEO_DIR, safe_name)

    try:
        with open(file_path, "wb") as f:
            f.write(downloaded)
    except Exception as e:
        logger.exception(f"Error writing video to {file_path}: {e}")
        raise

    return file_id, file_path

# ---------------- Command handlers ----------------
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
            # give initial 5 bonus
            bot.send_message(user_id, "🎉 Қош келдіңіз! Сізге бастапқы +5 бонус берілді.", reply_markup=get_main_markup(user_id))
            # referral handling
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

# ---------------- Video watch handler ----------------
@bot.message_handler(func=lambda m: m.text and "Видео" in m.text)
def handle_watch(message):
    user_id = message.from_user.id
    with db_lock:
        user = cursor.execute("SELECT bonus, progress FROM users WHERE user_id = ?", (user_id,)).fetchone()
    if not user:
        handle_start(message)
        return

    bonus, progress = user
    with db_lock:
        videos = cursor.execute("SELECT id, file_id, file_path FROM videos ORDER BY id ASC").fetchall()

    if not videos:
        bot.send_message(user_id, "🎬 Қазір видеолар жоқ. Админге хабарласыңыз.")
        return

    if bonus <= 0:
        bot.send_message(user_id, "❌ Сіздің бонусыңыз жоқ. Дос шақырыңыз немесе күтіңіз.")
        return

    # reset if reached end
    if progress >= len(videos):
        progress = 0

    video_row = videos[progress]  # (id, file_id, file_path)
    file_id = video_row[1]
    file_path = video_row[2]

    # Prefer sending from local file if exists, fallback to file_id
    try:
        if file_path and os.path.exists(file_path):
            with open(file_path, "rb") as vf:
                bot.send_video(user_id, vf)
        else:
            bot.send_video(user_id, file_id)
    except Exception as e:
        logger.exception(f"Error sending video to {user_id}: {e}")
        bot.send_message(user_id, "❌ Видео жіберілгенде қате болды. Админге хабарлаңыз.")
        return

    # decrement bonus and increment progress
    with db_lock:
        cursor.execute("UPDATE users SET bonus = ?, progress = ? WHERE user_id = ?",
                       (max(bonus - 1, 0), progress + 1, user_id))
        conn.commit()
    bot.send_message(user_id, f"✅ Видео көрсетілді! Қалған бонус: {max(bonus - 1, 0)}")

# ---------------- Referral view ----------------
@bot.message_handler(func=lambda m: m.text and "Реферал" in m.text)
def handle_referral(message):
    user_id = message.from_user.id
    ref_link = f"https://t.me/{bot.get_me().username}?start={user_id}"
    bot.send_message(user_id, f"🔗 Сіздің сілтемеңіз:\n{ref_link}\n\nӘр шақырған адам үшін +5 бонус 🎁")

# ---------------- Channel buttons ----------------
@bot.message_handler(func=lambda m: m.text and "Каналымызға қосылу" in m.text)
def handle_join_channel(message):
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(telebot.types.KeyboardButton("🔙 Басты мәзірге оралу"))
    bot.send_message(message.chat.id,
                     "Каналдарға қосылыңыз:\n\nhttps://t.me/Qazhuboyndar\nhttps://t.me/+XRoxE_8bUM1mMmIy",
                     reply_markup=markup)

@bot.message_handler(func=lambda m: m.text and "Басты мәзірге оралу" in m.text)
def handle_back_main(message):
    bot.send_message(message.chat.id, "Басты мәзірге оралу", reply_markup=get_main_markup(message.from_user.id))

@bot.message_handler(func=lambda m: m.text and "Канал алу" in m.text)
def handle_get_channel(message):
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(telebot.types.KeyboardButton("🔙 Артқа"))
    bot.send_message(message.chat.id, "Канал алғыңыз келсе жазыңыз ❤️\n@KazHubALU ✨️", reply_markup=markup)

# ---------------- Admin: stats, delete, broadcast ----------------
@bot.message_handler(func=lambda m: m.text and "Статистика" in m.text and m.from_user.id == ADMIN_ID)
def handle_stats(message):
    with db_lock:
        total = cursor.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        total_videos = cursor.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
    bot.send_message(message.chat.id, f"👥 Қолданушылар: {total}\n🎥 Видеолар саны: {total_videos}")

@bot.message_handler(func=lambda m: m.text and "Видеоларды өшіру" in m.text and m.from_user.id == ADMIN_ID)
def confirm_delete(message):
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(telebot.types.KeyboardButton("✅ Иә, өшір"), telebot.types.KeyboardButton("❎ Жоқ"))
    bot.send_message(message.chat.id, "Барлық видеоларды өшіресіз бе?", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text and "Иә, өшір" in m.text and m.from_user.id == ADMIN_ID)
def do_delete(message):
    # delete files and DB entries
    with db_lock:
        rows = cursor.execute("SELECT file_path FROM videos").fetchall()
        for r in rows:
            try:
                if r[0] and os.path.exists(r[0]):
                    os.remove(r[0])
            except Exception as e:
                logger.debug(f"Error removing file {r[0]}: {e}")
        cursor.execute("DELETE FROM videos")
        cursor.execute("UPDATE users SET progress = 0")
        conn.commit()
    bot.send_message(message.chat.id, "✅ Барлық видеолар өшірілді!")
    bot.send_message(message.chat.id, "Басты мәзірге ораласыз.", reply_markup=get_main_markup(message.from_user.id))

@bot.message_handler(func=lambda m: m.text and "Жоқ" in m.text and m.from_user.id == ADMIN_ID)
def cancel_delete(message):
    bot.send_message(message.chat.id, "❎ Операция тоқтатылды.", reply_markup=get_main_markup(message.from_user.id))

# Broadcast flow
admin_broadcast = {}
@bot.message_handler(func=lambda m: m.text and "Рассылка" in m.text and m.from_user.id == ADMIN_ID)
def start_broadcast(message):
    bot.send_message(message.chat.id, "✏️ Қандай хабарлама жібергіңіз келеді?")
    admin_broadcast[message.chat.id] = "WAITING_TEXT"

@bot.message_handler(func=lambda m: admin_broadcast.get(m.chat.id) == "WAITING_TEXT")
def receive_broadcast_text(message):
    admin_broadcast[message.chat.id] = message.text
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(telebot.types.KeyboardButton("✅ Ия"), telebot.types.KeyboardButton("❎ Жоқ"))
    bot.send_message(message.chat.id, f"Хабарламаны жіберейін бе?\n\n{message.text}", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text and m.text in ["✅ Ия", "❎ Жоқ"] and m.from_user.id == ADMIN_ID)
def send_or_cancel_broadcast(message):
    if message.text == "✅ Ия":
        text = admin_broadcast.get(message.chat.id)
        with db_lock:
            users = [u[0] for u in cursor.execute("SELECT user_id FROM users").fetchall()]
        for u in users:
            try:
                bot.send_message(u, text)
            except Exception as e:
                logger.debug(f"Broadcast send failed to {u}: {e}")
        bot.send_message(message.chat.id, "✅ Хабарлама барлық қолданушыларға жіберілді!")
    else:
        bot.send_message(message.chat.id, "❎ Рассылка тоқтатылды.")
    admin_broadcast.pop(message.chat.id, None)
    bot.send_message(message.chat.id, "Басты мәзірге оралыңыз.", reply_markup=get_main_markup(message.from_user.id))

# ---------------- Admin: receive video and save ----------------
@bot.message_handler(content_types=['video'])
def handle_incoming_video(message):
    # Only allow admin to upload videos via bot (change if you want multiple uploaders)
    if message.from_user.id != ADMIN_ID:
        bot.send_message(message.chat.id, "Рұқсат жоқ.")
        return

    try:
        file_id, file_path = save_video_file_from_message(message)
    except Exception as e:
        logger.exception("Failed to save incoming video")
        bot.send_message(message.chat.id, f"❌ Видео сақталмады: {e}")
        return

    # Save record to DB
    with db_lock:
        cursor.execute("INSERT INTO videos (file_id, file_path, created_at) VALUES (?, ?, ?)",
                       (file_id, file_path, datetime.utcnow().isoformat()))
        conn.commit()
        total = cursor.execute("SELECT COUNT(*) FROM videos").fetchone()[0]

    bot.send_message(message.chat.id, f"✅ Видео сақталды! Барлығы: {total} 🎥")

# ---------------- Webhook endpoints for Flask ----------------
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
    # set webhook (idempotent)
    try:
        bot.remove_webhook()
        bot.set_webhook(url=f"{WEBHOOK_URL}/{BOT_TOKEN}")
        return "Bot is live ✅", 200
    except Exception as e:
        logger.exception("Failed to set webhook")
        return f"Webhook error: {e}", 500

# ---------------- Start Flask app ----------------
if __name__ == "__main__":
    # Note: Render will run Flask; ensure your service start command is: python main.py
    logger.info("Starting Flask server for webhook...")
    # Use host 0.0.0.0 and port 10000 (as you had). In Render service, ensure Port matches.
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
