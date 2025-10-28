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
BOT_TOKEN = os.getenv("BOT_TOKEN") or "8419149602:AAHvLF3XmreCAQpvJy_8-RRJDH0g_qy9Oto"
ADMIN_ID = int(os.getenv("ADMIN_ID") or "6927494520")
WEBHOOK_URL = os.getenv("WEBHOOK_URL") or "https://nakedj-7-g6vy.onrender.com"
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
# Database tables
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
def get_user_inline(user_id: int):
    kb = InlineKeyboardMarkup()
    kb.row(
        InlineKeyboardButton("🎥 Видео", callback_data="watch_video"),
        InlineKeyboardButton("➕ Видео/Фото қосу", callback_data="upload_menu")
    )
    kb.row(
        InlineKeyboardButton("Канал алу", callback_data="buy_channel"),
        InlineKeyboardButton("Арналарымыз", callback_data="channels")
    )
    return kb

def get_admin_inline(pending_id):
    kb = InlineKeyboardMarkup()
    kb.row(
        InlineKeyboardButton("✅ Approve", callback_data=f"approve_{pending_id}"),
        InlineKeyboardButton("❌ Reject", callback_data=f"reject_{pending_id}")
    )
    return kb

def save_file(file_id: str, is_video=True) -> str:
    try:
        file_info = bot.get_file(file_id)
        b = bot.download_file(file_info.file_path)
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
        ext = ".mp4" if is_video else ".jpg"
        fname = f"{ts}_{file_id.replace('/', '_')}{ext}"
        path = os.path.join(VIDEO_DIR, fname)
        with open(path, "wb") as f:
            f.write(b)
        return path
    except Exception:
        logger.exception("save_file error")
        raise

def ensure_user(user_id:int, invited_by=None):
    with db_lock:
        exists = cursor.execute("SELECT 1 FROM users WHERE user_id=?", (user_id,)).fetchone()
        if not exists:
            cursor.execute("INSERT INTO users (user_id, balance, invited_by) VALUES (?, ?, ?)",
                           (user_id, 12, invited_by))
            conn.commit()

# ---------------------------
# Start command
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
                    try: bot.send_message(ref, "🎉 Сіз жаңа қолданушы шақырдыңыз! +12💸 берілді.")
                    except: pass
        with db_lock:
            bal = cursor.execute("SELECT balance FROM users WHERE user_id=?", (user_id,)).fetchone()[0]
        text = f"Сәлем 👋\nСізде қазір: {bal}💸\nТөмендегі батырмаларды таңдаңыз:"
        bot.send_message(user_id, text, reply_markup=get_user_inline(user_id))
    except Exception:
        logger.exception("cmd_start error")

# ---------------------------
# Callback queries
# ---------------------------
@bot.callback_query_handler(func=lambda c: True)
def callbacks(call):
    try:
        user_id = call.from_user.id
        data = call.data
        if data.startswith("approve_") and user_id == ADMIN_ID:
            pending_id = int(data.split("_")[1])
            approve_pending(pending_id)
            bot.answer_callback_query(call.id, "✅ Approved")
        elif data.startswith("reject_") and user_id == ADMIN_ID:
            pending_id = int(data.split("_")[1])
            reject_pending(pending_id)
            bot.answer_callback_query(call.id, "❌ Rejected")
        elif data == "watch_video":
            bot.answer_callback_query(call.id, "🎥 Видео мәзірі ашылады")
        elif data == "upload_menu":
            bot.answer_callback_query(call.id, "➕ Видео/Фото жүктеу")
        elif data == "buy_channel":
            bot.answer_callback_query(call.id, "Канал сатып алу")
        elif data == "channels":
            bot.answer_callback_query(call.id, "Арналарымыз")
    except Exception:
        logger.exception("callback error")

# ---------------------------
# Approve / Reject
# ---------------------------
def approve_pending(pending_id):
    with db_lock:
        item = cursor.execute("SELECT * FROM pending WHERE id=?", (pending_id,)).fetchone()
        if not item: return
        file_id, content_type, uploader_id = item[3], item[2], item[1]
        path = save_file(file_id, is_video=(content_type=="video"))
        table = "videos" if content_type=="video" else "photos"
        cursor.execute(f"INSERT INTO {table} (file_id, file_path, added_by, created_at) VALUES (?, ?, ?, ?)",
                       (file_id, path, uploader_id, datetime.utcnow().isoformat()))
        cursor.execute("DELETE FROM pending WHERE id=?", (pending_id,))
        conn.commit()
        try: bot.send_message(uploader_id, f"✅ Сіздің {content_type} мақалаңыз бекітілді!")
        except: pass

def reject_pending(pending_id):
    with db_lock:
        item = cursor.execute("SELECT * FROM pending WHERE id=?", (pending_id,)).fetchone()
        if not item: return
        uploader_id, content_type = item[1], item[2]
        cursor.execute("DELETE FROM pending WHERE id=?", (pending_id,))
        conn.commit()
        try: bot.send_message(uploader_id, f"❌ Сіздің {content_type} мақалаңыз қабылданбады!")
        except: pass

# ---------------------------
# Webhook endpoints
# ---------------------------
@app.route("/", methods=['GET'])
def index():
    return "Bot service is running", 200

@app.route("/webhook", methods=['POST'])
def webhook():
    try:
        json_str = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_str)
        bot.process_new_updates([update])
    except Exception:
        logger.exception("Webhook processing error")
    return "", 200

# ---------------------------
# Setup webhook
# ---------------------------
def setup_webhook():
    try:
        bot.remove_webhook()
        full_url = WEBHOOK_URL.rstrip("/") + "/webhook"
        bot.set_webhook(url=full_url)
        logger.info(f"Webhook set -> {full_url}")
    except Exception:
        logger.exception("Failed to set webhook")

setup_webhook()

# ---------------------------
# Run Flask
# ---------------------------
if __name__ == "__main__":
    logger.info(f"Running Flask on port {PORT}")
    app.run(host="0.0.0.0", port=PORT)
