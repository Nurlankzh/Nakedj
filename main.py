import os
import sqlite3
import threading
from datetime import datetime
from flask import Flask, request
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# ========================
# CONFIG
# ========================
BOT_TOKEN = os.environ.get("BOT_TOKEN") or "8419149602:AAHvLF3XmreCAQpvJy_8-RRJDH0g_qy9Oto"
ADMIN_ID = int(os.environ.get("ADMIN_ID") or "6927494520")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL") or "https://nakedj-7-g6vy.onrender.com"
VIDEO_DIR = os.environ.get("VIDEO_DIR") or "videos"
DB_FILE = os.environ.get("DB_FILE") or "data.db"

os.makedirs(VIDEO_DIR, exist_ok=True)

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)
lock = threading.Lock()

# ========================
# DATABASE
# ========================
conn = sqlite3.connect(DB_FILE, check_same_thread=False)
cursor = conn.cursor()

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

# ========================
# HELPERS
# ========================
def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}")

def get_main_keyboard(user_id):
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🎥 Видео көру", callback_data="watch_video"))
    kb.add(InlineKeyboardButton("➕ Видео/Фото қосу", callback_data="upload_menu"))
    kb.add(InlineKeyboardButton("Дос шақыру", callback_data="invite"))
    kb.add(InlineKeyboardButton("Баланс", callback_data="check_balance"))
    if user_id == ADMIN_ID:
        kb.add(InlineKeyboardButton("⚙️ Админ панель", callback_data="admin_panel"))
    return kb

def save_file(file_id, is_video=True):
    try:
        file_info = bot.get_file(file_id)
        b = bot.download_file(file_info.file_path)
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
        ext = ".mp4" if is_video else ".jpg"
        fname = f"{ts}_{file_id}{ext}"
        path = os.path.join(VIDEO_DIR, fname)
        with open(path, "wb") as f:
            f.write(b)
        log(f"Saved file {path}")
        return path
    except Exception as e:
        log(f"Error saving file: {e}")
        return None

# ========================
# /start
# ========================
@bot.message_handler(commands=['start'])
def cmd_start(message):
    user_id = message.from_user.id
    args = message.text.split()
    ref = args[1] if len(args) > 1 else None

    log(f"/start received from {user_id}, ref={ref}")

    with lock:
        exists = cursor.execute("SELECT 1 FROM users WHERE user_id=?", (user_id,)).fetchone()
        if not exists:
            invited_by = int(ref) if ref and ref.isdigit() and int(ref) != user_id else None
            cursor.execute("INSERT INTO users (user_id, balance, invited_by) VALUES (?, ?, ?)",
                           (user_id, 12, invited_by))
            conn.commit()
            log(f"New user {user_id} added with referrer {invited_by}")
            if invited_by:
                cursor.execute("UPDATE users SET balance = balance + 12 WHERE user_id=?", (invited_by,))
                conn.commit()
                log(f"Added 12 balance to referrer {invited_by}")
                try: bot.send_message(invited_by, f"🎉 Сіз жаңа қолданушы шақырдыңыз! +12💸 берілді.")
                except: pass

    bal = cursor.execute("SELECT balance FROM users WHERE user_id=?", (user_id,)).fetchone()[0]
    text = f"Сәлем 👋\nСізде қазір: {bal}💸\nТөмендегі батырмаларды таңдаңыз:"
    bot.send_message(user_id, text, reply_markup=get_main_keyboard(user_id))

# ========================
# CALLBACK HANDLERS
# ========================
@bot.callback_query_handler(func=lambda call: True)
def handle_cb(call):
    user_id = call.from_user.id
    data = call.data
    log(f"Callback received: {data} from {user_id}")

    if data == "check_balance":
        with lock:
            bal = cursor.execute("SELECT balance FROM users WHERE user_id=?", (user_id,)).fetchone()[0]
        bot.answer_callback_query(call.id, f"Сіздің балансыңыз: {bal}💸")
        return

    if data == "invite":
        bot.answer_callback_query(call.id, f"Сіздің шақыру сілтемеңіз:\nhttps://t.me/{bot.get_me().username}?start={user_id}")
        return

    if data == "watch_video":
        with lock:
            u = cursor.execute("SELECT balance, progress_video FROM users WHERE user_id=?", (user_id,)).fetchone()
            if not u:
                bot.answer_callback_query(call.id, "Алдымен /start басыңыз.")
                return
            balance, progress = u
            rows = cursor.execute("SELECT id, file_id, file_path FROM videos ORDER BY id ASC").fetchall()
            if not rows:
                bot.answer_callback_query(call.id, "🎬 Видеолар жоқ.")
                return
            if user_id != ADMIN_ID and balance < 3:
                bot.answer_callback_query(call.id, "Баланс жетпейді. Дос шақырыңыз!")
                return
            idx = progress if progress < len(rows) else 0
            file_id = rows[idx][1]
            file_path = rows[idx][2]
            try:
                if file_path and os.path.exists(file_path):
                    with open(file_path, "rb") as f:
                        bot.send_video(user_id, f)
                else:
                    bot.send_video(user_id, file_id)
            except Exception as e:
                log(f"Error sending video: {e}")
                bot.answer_callback_query(call.id, "Видео жібергенде қате.")
                return
            if user_id != ADMIN_ID:
                cursor.execute("UPDATE users SET balance=?, progress_video=? WHERE user_id=?",
                               (max(balance-3,0), idx+1, user_id))
            else:
                cursor.execute("UPDATE users SET progress_video=? WHERE user_id=?", (idx+1, user_id))
            conn.commit()
            bot.answer_callback_query(call.id, "Видео көрсетілді.")
        return

# ========================
# WEBHOOK FOR FLASK
# ========================
@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    try:
        update = telebot.types.Update.de_json(request.stream.read().decode("utf-8"))
        bot.process_new_updates([update])
        log("Processed update via webhook")
    except Exception as e:
        log(f"Webhook error: {e}")
    return "OK"

@app.route("/")
def index():
    return "Bot is running"

# ========================
# START SERVER & WEBHOOK
# ========================
if __name__ == "__main__":
    log("Setting webhook...")
    bot.remove_webhook()
    bot.set_webhook(url=f"{WEBHOOK_URL}/{BOT_TOKEN}")
    log(f"Webhook set to {WEBHOOK_URL}/{BOT_TOKEN}")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
