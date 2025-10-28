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
# Create tables if not exist
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
    try:
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
    except Exception as e:
        logger.exception("save_file_from_fileid error")
        raise

def ensure_user(user_id:int, invited_by=None):
    with db_lock:
        exists = cursor.execute("SELECT 1 FROM users WHERE user_id=?", (user_id,)).fetchone()
        if not exists:
            cursor.execute("INSERT INTO users (user_id, balance, invited_by) VALUES (?, ?, ?)",
                           (user_id, 12, invited_by))
            conn.commit()

# ---------------------------
# Handlers
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
        text = f"Сәлем 👋\nСізде қазір: {bal}💸\nТөмендегі батырмаларды таңдаңыз:"
        bot.send_message(user_id, text, reply_markup=get_main_inline(user_id))
    except Exception:
        logger.exception("cmd_start error")

# ---------------------------
# Callback handler
# ---------------------------
@bot.callback_query_handler(func=lambda c: True)
def handle_cb(call):
    data = call.data
    user_id = call.from_user.id

    if data == "buy_channel":
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("Басты мәзірге оралу", callback_data="back_main"))
        bot.edit_message_text("Канал сатып алғыңыз келсе жазыңыз @KazHubALU",
                              call.message.chat.id, call.message.message_id, reply_markup=kb)
        return

    if data == "channels":
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("Басты мәзірге оралу", callback_data="back_main"))
        text = "Тіркеліңіз — барлық жаңалықтар осында:\n1) https://t.me/+XRoxE_8bUM1mMmIy\n2) https://t.me/bokseklub"
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=kb)
        return

    if data == "watch_video":
        with db_lock:
            u = cursor.execute("SELECT balance, progress_video FROM users WHERE user_id=?", (user_id,)).fetchone()
            if not u:
                bot.answer_callback_query(call.id, "Алдымен /start басыңыз.")
                return
            balance, progress = u
            rows = cursor.execute("SELECT id, file_id, file_path FROM videos ORDER BY id ASC").fetchall()
            if not rows:
                bot.answer_callback_query(call.id, "🎬 Видеолар жоқ. Админге хабарласыңыз.")
                return
            if user_id != ADMIN_ID and balance < 3:
                bot.answer_callback_query(call.id, "Сіздің балансыңыз жетпейді. Дос шақырыңыз: " + f"https://t.me/{bot.get_me().username}?start={user_id}")
                return
            idx = progress if progress < len(rows) else 0
            row = rows[idx]
            file_id, file_path = row[1], row[2]
            try:
                if file_path and os.path.exists(file_path):
                    with open(file_path, "rb") as f: bot.send_video(user_id, f)
                else:
                    bot.send_video(user_id, file_id)
            except Exception:
                bot.answer_callback_query(call.id, "Видео жібергенде қате.")
                return
            if user_id != ADMIN_ID:
                cursor.execute("UPDATE users SET balance=?, progress_video=? WHERE user_id=?", (max(balance-3,0), idx+1, user_id))
            else:
                cursor.execute("UPDATE users SET progress_video=? WHERE user_id=?", (idx+1, user_id))
            conn.commit()
            bot.answer_callback_query(call.id, "Видео алынды.")
        return

    if data == "upload_menu":
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("Видео жіберу (админға жіберіледі)", callback_data="upload_video_hint"))
        kb.add(InlineKeyboardButton("Фото жіберу (админға жіберіледі)", callback_data="upload_photo_hint"))
        kb.add(InlineKeyboardButton("Басты мәзірге оралу", callback_data="back_main"))
        bot.edit_message_text("Видео немесе фото жүктегіңіз келсе соны таңдаңыз.", call.message.chat.id, call.message.message_id, reply_markup=kb)
        return

    if data == "back_main":
        with db_lock:
            ensure_user(user_id)
            bal = cursor.execute("SELECT balance FROM users WHERE user_id=?", (user_id,)).fetchone()[0]
        bot.edit_message_text(f"Сізде қазір: {bal}💸\nТөмендегі батырмаларды таңдаңыз:", call.message.chat.id, call.message.message_id, reply_markup=get_main_inline(user_id))
        return

# ---------------------------
# Flask webhook endpoint
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
