import os
import logging
import sqlite3
import threading
from datetime import datetime
from flask import Flask, request
import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

# ---------------------------
# CONFIG
# ---------------------------
BOT_TOKEN = "8419149602:AAHvLF3XmreCAQpvJy_8-RRJDH0g_qy9Oto"  # Токен
ADMIN_ID = 6303091468                                         # Админ ID
WEBHOOK_URL = "https://web-production-0cd8e.up.railway.app"  # Сіздің публичный URL
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
# Tables
# ---------------------------
with db_lock:
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        balance INTEGER DEFAULT 0,
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
def get_main_keyboard():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("Канал алу"))
    kb.add(KeyboardButton("🎥 Видео"))
    kb.add(KeyboardButton("➕ Видео/Фото қосу"))
    kb.add(KeyboardButton("Бонус беру (Админ)"))
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
            cursor.execute("INSERT INTO users (user_id, balance, invited_by) VALUES (?, ?, ?)", (user_id, 3, invited_by))
            conn.commit()

def is_subscribed(user_id:int):
    try:
        member = bot.get_chat_member("@kazakcombots", user_id)
        return member.status != 'left'
    except:
        return False

# ---------------------------
# /start
# ---------------------------
@bot.message_handler(commands=['start'])
def cmd_start(message):
    user_id = message.from_user.id
    args = message.text.split()
    ref = None
    if len(args) > 1 and args[1].isdigit():
        ref = int(args[1])
    ensure_user(user_id, invited_by=ref)
    
    # Реферал бонус
    if ref and ref != user_id:
        with db_lock:
            cursor.execute("UPDATE users SET balance = balance + 6 WHERE user_id=?", (ref,))
            conn.commit()
            try:
                bot.send_message(ref, f"🎉 Сіз жаңа қолданушы шақырдыңыз! +6💸 берілді.")
            except:
                pass
    
    bal = cursor.execute("SELECT balance FROM users WHERE user_id=?", (user_id,)).fetchone()[0]
    ref_link = f"https://t.me/Sallemkz_bot?start={user_id}"
    bot.send_message(user_id, f"Сәлем 👋\nСізде қазір: {bal}💸\nРеферал сілтеме: {ref_link}", reply_markup=get_main_keyboard())

# ---------------------------
# Handle text buttons
# ---------------------------
@bot.message_handler(func=lambda m: True)
def handle_text(message):
    user_id = message.from_user.id
    if not is_subscribed(user_id):
        bot.send_message(user_id, "❌ Алдымен каналға тіркеліңіз: https://t.me/kazakcombots")
        return

    text = message.text
    if text == "Канал алу":
        bot.send_message(user_id, "Канал сатып алғыңыз келсе жазыңыз @KazHUBKZ")
    elif text == "🎥 Видео":
        watch_video(user_id)
    elif text == "➕ Видео/Фото қосу":
        bot.send_message(user_id, "Файлты осы чатқа жүктеңіз (админға жіберіледі)")
    elif text == "Бонус беру (Админ)" and user_id == ADMIN_ID:
        bot.send_message(user_id, "Бонус беру үшін: /give <user_id> <сома>")
    else:
        bot.send_message(user_id, f"Сіз жаздыңыз: {text}")

# ---------------------------
# Watch video
# ---------------------------
def watch_video(user_id):
    with db_lock:
        u = cursor.execute("SELECT balance, progress_video FROM users WHERE user_id=?", (user_id,)).fetchone()
        if not u:
            bot.send_message(user_id, "Алдымен /start басыңыз.")
            return
        balance, progress = u
        rows = cursor.execute("SELECT id, file_id, file_path FROM videos ORDER BY id ASC").fetchall()
        if not rows:
            bot.send_message(user_id, "🎬 Видеолар жоқ.")
            return
        if user_id != ADMIN_ID and balance < 2:
            bot.send_message(user_id, "Видео көру үшін 2💸 керек.")
            return
        idx = progress if progress < len(rows) else 0
        row = rows[idx]
        file_id, file_path = row[1], row[2]
        try:
            if file_path and os.path.exists(file_path):
                with open(file_path, "rb") as f:
                    bot.send_video(chat_id=user_id, data=f, protect_content=True)
            else:
                bot.send_video(chat_id=user_id, video=file_id, protect_content=True)
        except:
            bot.send_message(user_id, "Видео жібергенде қате.")
            return
        if user_id != ADMIN_ID:
            cursor.execute("UPDATE users SET balance=?, progress_video=? WHERE user_id=?", (balance-2, idx+1, user_id))
        else:
            cursor.execute("UPDATE users SET progress_video=? WHERE user_id=?", (idx+1, user_id))
        conn.commit()

# ---------------------------
# Media messages (pending)
# ---------------------------
@bot.message_handler(content_types=['video','photo','document'])
def handle_media(message):
    user_id = message.from_user.id
    is_video = message.content_type in ['video','document']
    file_id = message.video.file_id if message.content_type=='video' else (message.document.file_id if message.content_type=='document' else message.photo[-1].file_id)
    path = save_file_from_fileid(file_id, is_video=is_video)

    if user_id == ADMIN_ID:
        with db_lock:
            if is_video:
                cursor.execute("INSERT INTO videos (file_id, file_path, added_by, created_at) VALUES (?, ?, ?, ?)", (file_id, path, user_id, datetime.utcnow().isoformat()))
            else:
                cursor.execute("INSERT INTO photos (file_id, file_path, added_by, created_at) VALUES (?, ?, ?, ?)", (file_id, path, user_id, datetime.utcnow().isoformat()))
            conn.commit()
        bot.send_message(user_id, "✅ Файл қабылданды (admin).")
        return

    # Regular user -> pending
    with db_lock:
        cursor.execute("INSERT INTO pending (uploader_id, content_type, file_id, file_path, created_at) VALUES (?, ?, ?, ?, ?)", (user_id, 'video' if is_video else 'photo', file_id, path, datetime.utcnow().isoformat()))
        pid = cursor.lastrowid
        conn.commit()
    bot.send_message(user_id, "✅ Файл модерацияға жіберілді. Админ мақұлдағаннан кейін бонус беріледі.")
    
    # Notify admin
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("Растау (+12 бонус)", callback_data=f"approve_{pid}"))
    kb.add(InlineKeyboardButton("Тастау", callback_data=f"reject_{pid}"))
    try:
        if is_video:
            with open(path, "rb") as f:
                bot.send_video(ADMIN_ID, f, caption=f"Pending video #{pid} from {user_id}", reply_markup=kb)
        else:
            with open(path, "rb") as f:
                bot.send_photo(ADMIN_ID, f, caption=f"Pending photo #{pid} from {user_id}", reply_markup=kb)
    except:
        bot.send_message(ADMIN_ID, f"Pending {'video' if is_video else 'photo'} #{pid} from {user_id}", reply_markup=kb)

# ---------------------------
# Callback (approve/reject)
# ---------------------------
@bot.callback_query_handler(func=lambda c: True)
def handle_cb(call):
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "Тек админ ғана.")
        return
    data = call.data
    parts = data.split("_")
    action, pid = parts[0], int(parts[1])
    with db_lock:
        p = cursor.execute("SELECT uploader_id, content_type, file_id, file_path FROM pending WHERE id=?", (pid,)).fetchone()
        if not p:
            bot.answer_callback_query(call.id, "Pending табылмады.")
            return
        uploader_id, ctype, file_id, file_path = p
        if action == "approve":
            if ctype=='video':
                cursor.execute("INSERT INTO videos (file_id, file_path, added_by, created_at) VALUES (?, ?, ?, ?)", (file_id, file_path, ADMIN_ID, datetime.utcnow().isoformat()))
            else:
                cursor.execute("INSERT INTO photos (file_id, file_path, added_by, created_at) VALUES (?, ?, ?, ?)", (file_id, file_path, ADMIN_ID, datetime.utcnow().isoformat()))
            cursor.execute("UPDATE users SET balance=balance+12 WHERE user_id=?", (uploader_id,))
            cursor.execute("DELETE FROM pending WHERE id=?", (pid,))
            conn.commit()
            bot.send_message(uploader_id, f"🎉 Сіздің {ctype} мақұлданды! +12 бонус берілді.")
            bot.answer_callback_query(call.id, "Мақұлданды.")
        else:
            cursor.execute("DELETE FROM pending WHERE id=?", (pid,))
            conn.commit()
            bot.send_message(uploader_id, f"❌ Сіздің файл модерацияда қабылданбады.")
            bot.answer_callback_query(call.id, "Тасталды.")

# ---------------------------
# Admin give bonus command
# ---------------------------
@bot.message_handler(commands=['give'])
def give_bonus(message):
    if message.from_user.id != ADMIN_ID:
        return
    args = message.text.split()
    if len(args)!=3: 
        bot.send_message(ADMIN_ID, "Қолдану: /give <user_id> <сома>")
        return
    uid, amount = int(args[1]), int(args[2])
    with db_lock:
        cursor.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (amount, uid))
        conn.commit()
    bot.send_message(ADMIN_ID, f"✅ {amount} бонус {uid} қолданушыға берілді.")
    bot.send_message(uid, f"🎁 Сізге {amount} бонус берілді!")

# ---------------------------
# Flask
# ---------------------------
@app.route("/", methods=['GET'])
def index():
    return "Bot service running", 200

@app.route(f"/{BOT_TOKEN}", methods=['POST'])
def webhook():
    json_str = request.get_data().decode('utf-8')
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return "", 200

def setup_webhook():
    bot.remove_webhook()
    full_url = f"{WEBHOOK_URL.rstrip('/')}/{BOT_TOKEN}"
    bot.set_webhook(url=full_url)
    logger.info(f"Webhook set -> {full_url}")

setup_webhook()

if __name__ == "__main__":
    bot.infinity_polling(timeout=10)
