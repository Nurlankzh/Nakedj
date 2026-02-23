import os
import logging
import sqlite3
import threading
from datetime import datetime
from flask import Flask, request
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# ---------------------------
# CONFIG
# ---------------------------
BOT_TOKEN = "8419149602:AAHvLF3XmreCAQpvJy_8-RRJDH0g_qy9Oto"  # ТВОЙ токен
ADMIN_ID = 6303091468                                         # Админ ID
WEBHOOK_URL = "https://web-production-0cd8e.up.railway.app"  # Публичный URL сервера
VIDEO_DIR = "videos"
DB_FILE = "data.db"
PORT = 10000

# ---------------------------
# Logging
# ---------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)
logger.info("Starting bot module...")

# ---------------------------
# Ensure folders
# ---------------------------
os.makedirs(VIDEO_DIR, exist_ok=True)

# ---------------------------
# Bot + Flask + DB init
# ---------------------------
bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

conn = sqlite3.connect(DB_FILE, check_same_thread=False)
cursor = conn.cursor()
db_lock = threading.Lock()

# ---------------------------
# Create tables
# ---------------------------
with db_lock:
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        balance INTEGER DEFAULT 12,
        progress_video INTEGER DEFAULT 0,
        invited_by INTEGER
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS videos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        file_id TEXT,
        file_path TEXT,
        added_by INTEGER,
        created_at TEXT
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS photos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        file_id TEXT,
        file_path TEXT,
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
        file_path TEXT,
        created_at TEXT
    )
    """)
    conn.commit()

# ---------------------------
# Helpers
# ---------------------------
def get_main_inline(user_id: int):
    kb = InlineKeyboardMarkup()
    kb.row(InlineKeyboardButton("Канал алу", callback_data="buy_channel"),
           InlineKeyboardButton("Арналарымыз", callback_data="channels"))
    kb.row(InlineKeyboardButton("🎥 Видео", callback_data="watch_video"),
           InlineKeyboardButton("➕ Видео/Фото қосу", callback_data="upload_menu"))
    return kb

def save_file_from_fileid(file_id: str, is_video=True) -> str:
    file_info = bot.get_file(file_id)
    b = bot.download_file(file_info.file_path)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
    ext = ".mp4" if is_video else ".jpg"
    fname = f"{ts}_{file_id.replace('/', '_')}{ext}"
    path = os.path.join(VIDEO_DIR, fname)
    with open(path, "wb") as f:
        f.write(b)
    return path

def ensure_user(user_id:int, invited_by=None):
    with db_lock:
        exists = cursor.execute("SELECT 1 FROM users WHERE user_id=?", (user_id,)).fetchone()
        if not exists:
            cursor.execute("INSERT INTO users (user_id, invited_by) VALUES (?, ?)", (user_id, invited_by))
            conn.commit()

# ---------------------------
# /start
# ---------------------------
@bot.message_handler(commands=['start'])
def cmd_start(message):
    user_id = message.from_user.id
    ensure_user(user_id)
    bal = cursor.execute("SELECT balance FROM users WHERE user_id=?", (user_id,)).fetchone()[0]
    text = f"Сәлем 👋\nСізде қазір: {bal}💸\nТөмендегі батырмаларды таңдаңыз:"
    bot.send_message(user_id, text, reply_markup=get_main_inline(user_id))

# ---------------------------
# Admin бонус беру
# ---------------------------
@bot.message_handler(commands=['bonus'])
def give_bonus(message):
    if message.from_user.id != ADMIN_ID:
        bot.reply_to(message, "Тек админ ғана қолдана алады.")
        return
    try:
        parts = message.text.split()
        uid = int(parts[1])
        amount = int(parts[2])
        cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (amount, uid))
        conn.commit()
        bot.send_message(uid, f"🎉 Сізге админнен {amount}💸 бонус берілді!")
        bot.reply_to(message, f"Бонус {amount}💸 {uid} қолданушыға берілді.")
    except Exception:
        bot.reply_to(message, "Қате! /bonus <user_id> <amount> форматында жазу керек.")

# ---------------------------
# Callback handler
# ---------------------------
@bot.callback_query_handler(func=lambda c: True)
def handle_cb(call):
    if call.data == "buy_channel":
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("Басты мәзірге оралу", callback_data="back_main"))
        bot.edit_message_text("Канал сатып алғыңыз келсе жазыңыз @KazHUBKZ",
                              call.message.chat.id, call.message.message_id, reply_markup=kb)
        return
    if call.data == "back_main":
        bal = cursor.execute("SELECT balance FROM users WHERE user_id=?", (call.from_user.id,)).fetchone()[0]
        bot.edit_message_text(f"Сізде қазір: {bal}💸\nТөмендегі батырмаларды таңдаңыз:", call.message.chat.id, call.message.message_id, reply_markup=get_main_inline(call.from_user.id))

# ---------------------------
# Flask webhook
# ---------------------------
@app.route("/", methods=['GET'])
def index():
    return "Bot service is running", 200

@app.route(f"/{BOT_TOKEN}", methods=['POST'])
def webhook():
    try:
        update = telebot.types.Update.de_json(request.get_data().decode('utf-8'))
        bot.process_new_updates([update])
    except Exception:
        logger.exception("Webhook error")
    return "", 200

def setup_webhook():
    bot.remove_webhook()
    full_url = f"{WEBHOOK_URL}/{BOT_TOKEN}"
    bot.set_webhook(full_url)
    logger.info(f"Webhook set -> {full_url}")

setup_webhook()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
