import os
import logging
import sqlite3
import threading
from datetime import datetime
from flask import Flask, request
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# ---------------------------
# CONFIG / ENV
# ---------------------------
BOT_TOKEN = os.getenv("BOT_TOKEN") or "СЕНІҢ_BOT_TOKEN"
ADMIN_ID = int(os.getenv("ADMIN_ID") or "СЕНІҢ_ADMIN_ID")
WEBHOOK_URL = os.getenv("WEBHOOK_URL") or "https://YOUR_RENDER_URL.onrender.com"
VIDEO_DIR = os.getenv("VIDEO_DIR") or "videos"
DB_FILE = os.getenv("DB_FILE") or "data.db"
PORT = int(os.getenv("PORT") or 10000)

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
    CREATE TABLE IF NOT EXISTS pending (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        uploader_id INTEGER,
        content_type TEXT,
        file_id TEXT,
        file_path TEXT,
        created_at TEXT
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
    conn.commit()

# ---------------------------
# Helpers
# ---------------------------
def get_main_inline(user_id: int):
    kb = InlineKeyboardMarkup()
    kb.row(
        InlineKeyboardButton("Канал алу", callback_data="buy_channel"),
        InlineKeyboardButton("Арналарымыз", callback_data="channels")
    )
    kb.row(
        InlineKeyboardButton("🎥 Видео", callback_data="watch_video"),
        InlineKeyboardButton("➕ Видео/Фото қосу", callback_data="upload_menu")
    )
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
    logger.info(f"Saved file to {path}")
    return path

def ensure_user(user_id:int, invited_by=None):
    with db_lock:
        exists = cursor.execute("SELECT 1 FROM users WHERE user_id=?", (user_id,)).fetchone()
        if not exists:
            cursor.execute("INSERT INTO users (user_id, balance, invited_by) VALUES (?, ?, ?)",
                           (user_id, 12, invited_by))
            conn.commit()

# ---------------------------
# /start handler
# ---------------------------
@bot.message_handler(commands=['start'])
def cmd_start(message):
    try:
        user_id = message.from_user.id
        args = message.text.split()
        ref = None
        if len(args) > 1:
            a = args[1]
            if a.isdigit(): ref = int(a)
            elif a.startswith("start=") and a[6:].isdigit(): ref = int(a[6:])
        ensure_user(user_id, invited_by=ref)
        if ref and ref != user_id:
            with db_lock:
                inv = cursor.execute("SELECT 1 FROM users WHERE user_id=?", (ref,)).fetchone()
                if inv:
                    cursor.execute("UPDATE users SET balance = balance + 12 WHERE user_id=?", (ref,))
                    conn.commit()
                    try: bot.send_message(ref, f"🎉 Сіз жаңа қолданушы шақырдыңыз! +12💸 берілді.")
                    except: pass
        with db_lock:
            bal = cursor.execute("SELECT balance FROM users WHERE user_id=?", (user_id,)).fetchone()[0]
        bot.send_message(user_id, f"Сәлем 👋\nСізде қазір: {bal}💸\nТөмендегі батырмаларды таңдаңыз:", reply_markup=get_main_inline(user_id))
    except Exception:
        logger.exception("cmd_start error")

# ---------------------------
# Media handler
# ---------------------------
@bot.message_handler(content_types=['video','photo','document'])
def handle_media(message):
    user_id = message.from_user.id
    is_video = message.content_type in ['video','document'] and ('video' in getattr(message.document,'mime_type','') if hasattr(message,'document') else True)
    file_id = message.video.file_id if message.content_type=='video' else message.photo[-1].file_id if message.content_type=='photo' else message.document.file_id
    path = save_file_from_fileid(file_id, is_video)
    if user_id == ADMIN_ID:
        with db_lock:
            if is_video:
                cursor.execute("INSERT INTO videos (file_id, file_path, added_by, created_at) VALUES (?, ?, ?, ?)", (file_id, path, user_id, datetime.utcnow().isoformat()))
            else:
                cursor.execute("INSERT INTO photos (file_id, file_path, added_by, created_at) VALUES (?, ?, ?, ?)", (file_id, path, user_id, datetime.utcnow().isoformat()))
            conn.commit()
        bot.send_message(user_id, "✅ Файл қабылданды (admin).")
        return
    with db_lock:
        cursor.execute("INSERT INTO pending (uploader_id, content_type, file_id, file_path, created_at) VALUES (?, ?, ?, ?, ?)", (user_id, 'video' if is_video else 'photo', file_id, path, datetime.utcnow().isoformat()))
        pid = cursor.lastrowid
        conn.commit()
    bot.send_message(user_id, "✅ Файл модерацияға жіберілді.")

# ---------------------------
# Callback handler
# ---------------------------
@bot.callback_query_handler(func=lambda c: True)
def handle_cb(call):
    data = call.data
    user_id = call.from_user.id
    if data=="back_main":
        with db_lock:
            bal = cursor.execute("SELECT balance FROM users WHERE user_id=?", (user_id,)).fetchone()[0]
        bot.edit_message_text(f"Сізде қазір: {bal}💸\nТөмендегі батырмаларды таңдаңыз:", call.message.chat.id, call.message.message_id, reply_markup=get_main_inline(user_id))
        return

# ---------------------------
# Flask webhook
# ---------------------------
app = Flask(__name__)

@app.route("/", methods=['GET'])
def index():
    return "Bot service is running", 200

@app.route("/webhook", methods=['POST'])
def webhook():
    json_str = request.get_data().decode('utf-8')
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return "", 200

# ---------------------------
# Setup webhook
# ---------------------------
def setup_webhook():
    try:
        bot.remove_webhook()
        full_url = WEBHOOK_URL.rstrip("/") + "/webhook"
        result = bot.set_webhook(url=full_url)
        logger.info(f"Webhook set -> {full_url}  result: {result}")
    except Exception:
        logger.exception("Failed to set webhook")

setup_webhook()

# ---------------------------
# Run Flask
# ---------------------------
if __name__ == "__main__":
    logger.info(f"Running Flask on port {PORT}")
    app.run(host="0.0.0.0", port=PORT)
