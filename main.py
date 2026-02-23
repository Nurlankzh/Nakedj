import os
import logging
import sqlite3
from datetime import datetime
from flask import Flask, request
import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton

# ---------------------------
# CONFIG
# ---------------------------
BOT_TOKEN = "8419149602:AAHvLF3XmreCAQpvJy_8-RRJDH0g_qy9Oto"
ADMIN_ID = 6303091468  # @Nureken0_0
WEBHOOK_URL = "https://web-production-0cd8e.up.railway.app"
DB_FILE = "data.db"
CHANNEL_CHECK = "@kazakcombots"
PORT = int(os.getenv("PORT") or 10000)

# ---------------------------
# Logging
# ---------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------
# Init
# ---------------------------
bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)
conn = sqlite3.connect(DB_FILE, check_same_thread=False)
cursor = conn.cursor()

# ---------------------------
# DB Tables
# ---------------------------
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    balance INTEGER DEFAULT 3,
    progress_video INTEGER DEFAULT 0,
    invited_by INTEGER
)
""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS videos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id TEXT,
    added_by INTEGER,
    created_at TEXT
)
""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS pending (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uploader_id INTEGER,
    content_type TEXT,
    file_id TEXT,
    created_at TEXT
)
""")
conn.commit()

# ---------------------------
# Helpers
# ---------------------------
def ensure_user(user_id, invited_by=None):
    exists = cursor.execute("SELECT 1 FROM users WHERE user_id=?", (user_id,)).fetchone()
    if not exists:
        cursor.execute("INSERT INTO users (user_id, balance, invited_by) VALUES (?, ?, ?)", (user_id, 3, invited_by))
        conn.commit()
        if invited_by and invited_by != user_id:
            cursor.execute("UPDATE users SET balance = balance + 6 WHERE user_id=?", (invited_by,))
            conn.commit()
            try:
                bot.send_message(invited_by, "🎉 Сіз жаңа қолданушы шақырдыңыз! +6💸 берілді.")
            except:
                pass

def get_main_keyboard():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("🎥 Видео"), KeyboardButton("➕ Видео/Фото қосу"))
    kb.add(KeyboardButton("Каналға тіркелу"))
    return kb

# ---------------------------
# Start
# ---------------------------
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    args = message.text.split()
    ref = int(args[1]) if len(args) > 1 and args[1].isdigit() else None
    ensure_user(user_id, invited_by=ref)
    user_bal = cursor.execute("SELECT balance FROM users WHERE user_id=?", (user_id,)).fetchone()[0]
    bot.send_message(user_id, f"Сәлем 👋\nСізде: {user_bal}💸\nТөмендегі батырманы таңдаңыз:", reply_markup=get_main_keyboard())

# ---------------------------
# Text messages
# ---------------------------
@bot.message_handler(content_types=['text'])
def handle_text(message):
    user_id = message.from_user.id
    text = message.text

    # Админ бонус беру
    if user_id == ADMIN_ID and text.startswith("/bonus"):
        parts = text.split()
        if len(parts) == 3 and parts[1].isdigit() and parts[2].isdigit():
            uid = int(parts[1])
            amount = int(parts[2])
            cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (amount, uid))
            conn.commit()
            bot.send_message(user_id, f"✅ {uid} қолданушыға {amount} бонус қосылды.")
        else:
            bot.send_message(user_id, "Қате! /bonus <user_id> <amount>")
        return

    # Видео көру
    if text == "🎥 Видео":
        row = cursor.execute("SELECT balance, progress_video FROM users WHERE user_id=?", (user_id,)).fetchone()
        if not row:
            bot.send_message(user_id, "Алдымен /start басыңыз.")
            return
        balance, progress = row
        videos = cursor.execute("SELECT id, file_id FROM videos ORDER BY id ASC").fetchall()
        if not videos:
            bot.send_message(user_id, "🎬 Видеолар жоқ.")
            return
        if user_id != ADMIN_ID and balance < 2:
            bot.send_message(user_id, "Видео көру үшін 2💸 керек.")
            return
        idx = progress if progress < len(videos) else 0
        file_id = videos[idx][1]
        try:
            bot.send_video(user_id, file_id)
        except:
            bot.send_message(user_id, "Видео жібергенде қате.")
            return
        if user_id != ADMIN_ID:
            cursor.execute("UPDATE users SET balance = balance - 2, progress_video=? WHERE user_id=?", (idx+1, user_id))
        else:
            cursor.execute("UPDATE users SET progress_video=? WHERE user_id=?", (idx+1, user_id))
        conn.commit()
        return

    # Видео/Фото қосу
    if text == "➕ Видео/Фото қосу":
        bot.send_message(user_id, "Файлты осы чатқа жіберіңіз. Админ мақұлдайды.")
        return

    # Канал тексеру
    if text == "Каналға тіркелу":
        bot.send_message(user_id, f"Тексеру үшін каналға кіріңіз: {CHANNEL_CHECK}")
        return

# ---------------------------
# Media messages
# ---------------------------
@bot.message_handler(content_types=['video','photo'])
def handle_media(message):
    user_id = message.from_user.id
    file_id = message.video.file_id if message.content_type == 'video' else message.photo[-1].file_id
    ctype = 'video' if message.content_type == 'video' else 'photo'

    if user_id == ADMIN_ID:
        cursor.execute("INSERT INTO videos (file_id, added_by, created_at) VALUES (?, ?, ?)", 
                       (file_id, user_id, datetime.utcnow().isoformat()))
        conn.commit()
        bot.send_message(user_id, f"✅ {ctype} қосылды.")
        return

    # Regular users -> pending
    cursor.execute("INSERT INTO pending (uploader_id, content_type, file_id, created_at) VALUES (?, ?, ?, ?)",
                   (user_id, ctype, file_id, datetime.utcnow().isoformat()))
    pid = cursor.lastrowid
    conn.commit()

    bot.send_message(ADMIN_ID, f"Пайдаланушы {user_id} жіберді: {ctype}\n✅ Растау / ❌ Тастау\napprove_{pid} / reject_{pid}")
    bot.send_message(user_id, "✅ Файл модерацияға жіберілді.")

# ---------------------------
# Admin approve
# ---------------------------
@bot.message_handler(func=lambda m: True)
def admin_approve(msg):
    if msg.from_user.id != ADMIN_ID:
        return
    if msg.text.startswith("approve_") or msg.text.startswith("reject_"):
        parts = msg.text.split("_")
        action = parts[0]
        pid = int(parts[1])
        row = cursor.execute("SELECT uploader_id, content_type, file_id FROM pending WHERE id=?", (pid,)).fetchone()
        if not row:
            bot.send_message(ADMIN_ID, "Pending табылмады.")
            return
        uid, ctype, file_id = row
        if action == "approve":
            if ctype == "video":
                cursor.execute("INSERT INTO videos (file_id, added_by, created_at) VALUES (?, ?, ?)",
                               (file_id, ADMIN_ID, datetime.utcnow().isoformat()))
            else:
                cursor.execute("INSERT INTO photos (file_id, added_by, created_at) VALUES (?, ?, ?)",
                               (file_id, ADMIN_ID, datetime.utcnow().isoformat()))
            cursor.execute("UPDATE users SET balance = balance + 12 WHERE user_id=?", (uid,))
            cursor.execute("DELETE FROM pending WHERE id=?", (pid,))
            conn.commit()
            bot.send_message(uid, f"🎉 Сіздің {ctype} мақұлданды! +12💸 берілді.")
            bot.send_message(ADMIN_ID, f"{ctype} мақұлданды.")
        else:
            cursor.execute("DELETE FROM pending WHERE id=?", (pid,))
            conn.commit()
            bot.send_message(uid, f"❌ Сіздің файл модерацияда қабылданбады.")
            bot.send_message(ADMIN_ID, f"{ctype} тасталды.")

# ---------------------------
# Flask endpoints
# ---------------------------
@app.route("/", methods=['GET'])
def index():
    return "Bot service is running", 200

@app.route(f"/{BOT_TOKEN}", methods=['POST'])
def webhook():
    try:
        update = telebot.types.Update.de_json(request.get_data().decode('utf-8'))
        bot.process_new_updates([update])
    except Exception as e:
        logger.exception("Webhook processing error")
    return "", 200

# ---------------------------
# Setup webhook
# ---------------------------
def setup_webhook():
    bot.remove_webhook()
    bot.set_webhook(url=f"{WEBHOOK_URL.rstrip('/')}/{BOT_TOKEN}")
    logger.info(f"Webhook set -> {WEBHOOK_URL}/{BOT_TOKEN}")

setup_webhook()

# ---------------------------
# Run Flask
# ---------------------------
if __name__ == "__main__":
    logger.info(f"Running Flask on port {PORT}")
    app.run(host="0.0.0.0", port=PORT)
