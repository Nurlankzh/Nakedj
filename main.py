import os
import logging
import sqlite3
import threading
from datetime import datetime
from flask import Flask, request
import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton

# ---------------------------
# CONFIG
# ---------------------------
BOT_TOKEN = os.getenv("BOT_TOKEN") or "8419149602:AAHvLF3XmreCAQpvJy_8-RRJDH0g_qy9Oto"
ADMIN_ID = int(os.getenv("ADMIN_ID") or "6303091468")  # Админ айди
CHANNEL_USERNAME = "@kazakcombots"  # Тексерілетін канал
WEBHOOK_URL = os.getenv("WEBHOOK_URL") or "https://web-production-0cd8e.up.railway.app"
VIDEO_DIR = "videos"
DB_FILE = "data.db"
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
# Bot + Flask + DB
# ---------------------------
bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)
conn = sqlite3.connect(DB_FILE, check_same_thread=False)
cursor = conn.cursor()
db_lock = threading.Lock()

# ---------------------------
# DB tables
# ---------------------------
with db_lock:
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        balance INTEGER DEFAULT 3,
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
def ensure_user(user_id, invited_by=None):
    with db_lock:
        exists = cursor.execute("SELECT 1 FROM users WHERE user_id=?", (user_id,)).fetchone()
        if not exists:
            cursor.execute("INSERT INTO users (user_id, balance, invited_by) VALUES (?, ?, ?)",
                           (user_id, 3, invited_by))
            conn.commit()
            # Invite bonus
            if invited_by and invited_by != user_id:
                cursor.execute("UPDATE users SET balance = balance + 6 WHERE user_id=?", (invited_by,))
                conn.commit()
                try:
                    bot.send_message(invited_by, "🎉 Сіз жаңа қолданушы шақырдыңыз! +6💸 берілді.")
                except: pass

def get_main_keyboard(admin=False):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(KeyboardButton("🎥 Видео көру"), KeyboardButton("➕ Видео/Фото жіберу"))
    if admin:
        kb.row(KeyboardButton("💰 Бонус беру"))
    return kb

def save_file(file_id, is_video=True):
    file_info = bot.get_file(file_id)
    b = bot.download_file(file_info.file_path)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
    ext = ".mp4" if is_video else ".jpg"
    fname = f"{ts}_{file_id.replace('/', '_')}{ext}"
    path = os.path.join(VIDEO_DIR, fname)
    with open(path, "wb") as f:
        f.write(b)
    return path

def check_subscription(user_id):
    try:
        member = bot.get_chat_member(CHANNEL_USERNAME, user_id)
        if member.status in ["member", "administrator", "creator"]:
            return True
    except:
        return False
    return False

# ---------------------------
# Handlers
# ---------------------------
@bot.message_handler(commands=['start'])
def cmd_start(msg):
    user_id = msg.from_user.id
    args = msg.text.split()
    ref = None
    if len(args) > 1 and args[1].isdigit():
        ref = int(args[1])
    ensure_user(user_id, invited_by=ref)
    with db_lock:
        bal = cursor.execute("SELECT balance FROM users WHERE user_id=?", (user_id,)).fetchone()[0]
    bot.send_message(user_id,
                     f"Сәлем 👋\nСізде қазір: {bal}💸\nТөмендегі кнопкаларды таңдаңыз:",
                     reply_markup=get_main_keyboard(admin=(user_id==ADMIN_ID)))

# ---------------------------
# Text messages
# ---------------------------
@bot.message_handler(func=lambda m: True)
def handle_text(msg):
    user_id = msg.from_user.id
    text = msg.text
    ensure_user(user_id)
    
    if text == "🎥 Видео көру":
        # Канал тексеру
        if not check_subscription(user_id):
            bot.send_message(user_id, f"📢 Видео көру үшін {CHANNEL_USERNAME} каналына тіркеліңіз!")
            return
        # Видео очереді
        with db_lock:
            u = cursor.execute("SELECT balance, progress_video FROM users WHERE user_id=?", (user_id,)).fetchone()
            balance, progress = u
            rows = cursor.execute("SELECT id, file_id, file_path FROM videos ORDER BY id ASC").fetchall()
            if not rows:
                bot.send_message(user_id, "🎬 Видеолар жоқ.")
                return
            if user_id != ADMIN_ID and balance < 2:
                bot.send_message(user_id, "💸 Видео көру үшін 2 бонус керек.")
                return
            idx = progress if progress < len(rows) else 0
            file_id, file_path = rows[idx][1], rows[idx][2]
            try:
                if file_path and os.path.exists(file_path):
                    with open(file_path, "rb") as f:
                        bot.send_video(user_id, f)
                else:
                    bot.send_video(user_id, file_id)
            except:
                bot.send_message(user_id, "Видео жібергенде қате.")
                return
            if user_id != ADMIN_ID:
                cursor.execute("UPDATE users SET balance=?, progress_video=? WHERE user_id=?",
                               (max(balance-2,0), idx+1, user_id))
            else:
                cursor.execute("UPDATE users SET progress_video=? WHERE user_id=?", (idx+1, user_id))
            conn.commit()
    
    elif text == "➕ Видео/Фото жіберу":
        bot.send_message(user_id, "Файл жіберіңіз (админ мақұлдайды).")
    
    elif text == "💰 Бонус беру" and user_id==ADMIN_ID:
        bot.send_message(user_id, "Формат: <user_id> <сома>")
    
    else:
        if user_id==ADMIN_ID and text.startswith(tuple("0123456789")):
            try:
                parts = text.split()
                target_id = int(parts[0])
                amount = int(parts[1])
                cursor.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (amount, target_id))
                conn.commit()
                bot.send_message(user_id, f"{amount}💸 {target_id}-қа берілді.")
                bot.send_message(target_id, f"🎉 Сізге {amount}💸 берілді!")
            except:
                bot.send_message(user_id, "Қате формат!")
        else:
            bot.send_message(user_id, "Түсінбедім 😅", reply_markup=get_main_keyboard(admin=(user_id==ADMIN_ID)))

# ---------------------------
# Media messages
# ---------------------------
@bot.message_handler(content_types=['video','photo','document'])
def handle_media(msg):
    user_id = msg.from_user.id
    is_video = msg.content_type in ['video','document']
    try:
        if msg.content_type=='video':
            file_id = msg.video.file_id
        elif msg.content_type=='photo':
            file_id = msg.photo[-1].file_id
        elif msg.content_type=='document':
            file_id = msg.document.file_id
        path = save_file(file_id, is_video)
    except:
        bot.send_message(user_id, "Файл сақталмады!")
        return
    
    if user_id==ADMIN_ID:
        with db_lock:
            if is_video:
                cursor.execute("INSERT INTO videos (file_id, file_path, added_by, created_at) VALUES (?, ?, ?, ?)",
                               (file_id, path, user_id, datetime.utcnow().isoformat()))
            else:
                cursor.execute("INSERT INTO photos (file_id, file_path, added_by, created_at) VALUES (?, ?, ?, ?)",
                               (file_id, path, user_id, datetime.utcnow().isoformat()))
            conn.commit()
        bot.send_message(user_id, "✅ Файл сақталды (Admin).")
        return
    
    # Pending
    with db_lock:
        cursor.execute("INSERT INTO pending (uploader_id, content_type, file_id, file_path, created_at) VALUES (?, ?, ?, ?, ?)",
                       (user_id, 'video' if is_video else 'photo', file_id, path, datetime.utcnow().isoformat()))
        pid = cursor.lastrowid
        conn.commit()
    bot.send_message(user_id, "✅ Файл модерацияға жіберілді. Админ мақұлдағаннан кейін бонус беріледі.")

# ---------------------------
# Webhook + Flask
# ---------------------------
@app.route("/", methods=['GET'])
def index():
    return "Bot running", 200

@app.route(f"/{BOT_TOKEN}", methods=['POST'])
def webhook():
    try:
        json_str = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_str)
        bot.process_new_updates([update])
    except:
        logger.exception("Webhook error")
    return "", 200

def setup_webhook():
    bot.remove_webhook()
    bot.set_webhook(url=f"{WEBHOOK_URL}/{BOT_TOKEN}")

setup_webhook()

if __name__=="__main__":
    logger.info(f"Running Flask on port {PORT}")
    app.run(host="0.0.0.0", port=PORT)
