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
    kb.row(InlineKeyboardButton("Канал алу", callback_data="buy_channel"),
           InlineKeyboardButton("Арналарымыз", callback_data="channels"))
    kb.row(InlineKeyboardButton("🎥 Видео", callback_data="watch_video"),
           InlineKeyboardButton("➕ Видео/Фото қосу", callback_data="upload_menu"))
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
# Handlers: /start
# ---------------------------
@bot.message_handler(commands=['start'])
def cmd_start(message):
    try:
        user_id = message.from_user.id
        username = message.from_user.username or message.from_user.first_name or str(user_id)
        args = message.text.split()
        ref = None
        if len(args) > 1:
            a = args[1]
            if a.isdigit():
                ref = int(a)
            elif a.startswith("start=") and a[6:].isdigit():
                ref = int(a[6:])
        ensure_user(user_id, invited_by=ref)
        # give inviter bonus once
        if ref and ref != user_id:
            with db_lock:
                inv = cursor.execute("SELECT 1 FROM users WHERE user_id=?", (ref,)).fetchone()
                if inv:
                    cursor.execute("UPDATE users SET balance = balance + 12 WHERE user_id=?", (ref,))
                    conn.commit()
                    try:
                        bot.send_message(ref, f"🎉 Сіз жаңа қолданушы шақырдыңыз! +12💸 берілді.")
                    except Exception:
                        logger.exception("Couldn't notify inviter")
        with db_lock:
            bal = cursor.execute("SELECT balance FROM users WHERE user_id=?", (user_id,)).fetchone()[0]
        text = f"Сәлем 👋\nСізде қазір: {bal}💸\nТөмендегі батырмаларды таңдаңыз:"
        bot.send_message(user_id, text, reply_markup=get_main_inline(user_id))
        logger.info(f"/start from {user_id} ({username}) — balance {bal}")
    except Exception:
        logger.exception("cmd_start error")

# ---------------------------
# Text messages
# ---------------------------
@bot.message_handler(content_types=['text'])
def handle_text(message):
    user_id = message.from_user.id
    if message.text.lower().startswith("/admin") and user_id == ADMIN_ID:
        with db_lock:
            users_count = cursor.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            videos_count = cursor.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
            pending_count = cursor.execute("SELECT COUNT(*) FROM pending").fetchone()[0]
        bot.send_message(ADMIN_ID, f"📊 Admin stats:\nUsers: {users_count}\nVideos: {videos_count}\nPending: {pending_count}")
        return
    ensure_user(user_id)
    with db_lock:
        bal = cursor.execute("SELECT balance FROM users WHERE user_id=?", (user_id,)).fetchone()[0]
    bot.send_message(user_id, f"Сіз жаздыңыз: {message.text}\nСізде: {bal}💸", reply_markup=get_main_inline(user_id))

# ---------------------------
# Media messages
# ---------------------------
@bot.message_handler(content_types=['video','photo','document'])
def handle_media(message):
    user_id = message.from_user.id
    is_video = (message.content_type == 'video') or (message.content_type == 'document' and (message.document.mime_type and "video" in message.document.mime_type))
    file_id = None
    try:
        if message.content_type == 'video':
            file_id = message.video.file_id
        elif message.content_type == 'photo':
            file_id = message.photo[-1].file_id
        elif message.content_type == 'document':
            file_id = message.document.file_id
        if not file_id:
            bot.send_message(user_id, "Файл табылмады.")
            return
        path = save_file_from_fileid(file_id, is_video=is_video)
    except Exception as e:
        bot.send_message(user_id, f"Файл сақталмады: {e}")
        logger.exception("handle_media error saving file")
        return

    if user_id == ADMIN_ID:
        with db_lock:
            if is_video:
                cursor.execute("INSERT INTO videos (file_id, file_path, added_by, created_at) VALUES (?, ?, ?, ?)",
                               (file_id, path, user_id, datetime.utcnow().isoformat()))
            else:
                cursor.execute("INSERT INTO photos (file_id, file_path, added_by, created_at) VALUES (?, ?, ?, ?)",
                               (file_id, path, user_id, datetime.utcnow().isoformat()))
            conn.commit()
        bot.send_message(user_id, "✅ Файл қабылданды (admin).")
        return

    # regular user -> pending
    with db_lock:
        cursor.execute("INSERT INTO pending (uploader_id, content_type, file_id, file_path, created_at) VALUES (?, ?, ?, ?, ?)",
                       (user_id, 'video' if is_video else 'photo', file_id, path, datetime.utcnow().isoformat()))
        pid = cursor.lastrowid
        conn.commit()
    bot.send_message(user_id, "✅ Файл модерацияға жіберілді. Админ мақұлдағаннан кейін хабарланады.")

    # Notify admin
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("Approve (+40/+30)", callback_data=f"approve_{pid}"))
    kb.add(InlineKeyboardButton("Reject", callback_data=f"reject_{pid}"))
    try:
        if is_video:
            with open(path, "rb") as f:
                bot.send_video(ADMIN_ID, f, caption=f"New pending video #{pid} from {user_id}", reply_markup=kb)
        else:
            with open(path, "rb") as f:
                bot.send_photo(ADMIN_ID, f, caption=f"New pending photo #{pid} from {user_id}", reply_markup=kb)
    except Exception:
        bot.send_message(ADMIN_ID, f"New pending ({'video' if is_video else 'photo'}) #{pid} from {user_id}. Approve/Reject in chat.", reply_markup=kb)

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
                bot.answer_callback_query(call.id, "Видео көру үшін 3💸 керек.")
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
        bot.edit_message_text("Видео немесе фото жүктегіңіз келсе соны таңдаңыз. (Файлты осы чатқа жүктеңіз)", call.message.chat.id, call.message.message_id, reply_markup=kb)
        return

    if data.startswith("approve_") or data.startswith("reject_"):
        if user_id != ADMIN_ID:
            bot.answer_callback_query(call.id, "Тек админ ғана.")
            return
        parts = data.split("_")
        action = parts[0]
        pid = int(parts[1])
        with db_lock:
            p = cursor.execute("SELECT uploader_id, content_type, file_id, file_path FROM pending WHERE id=?", (pid,)).fetchone()
            if not p:
                bot.answer_callback_query(call.id, "Pending табылмады.")
                return
            uploader_id, ctype, file_id, file_path = p
            if action == "approve":
                if ctype == "video":
                    cursor.execute("INSERT INTO videos (file_id, file_path, added_by, created_at) VALUES (?, ?, ?, ?)",
                                   (file_id, file_path, user_id, datetime.utcnow().isoformat()))
                    cursor.execute("UPDATE users SET balance = balance + 40 WHERE user_id=?", (uploader_id,))
                else:
                    cursor.execute("INSERT INTO photos (file_id, file_path, added_by, created_at) VALUES (?, ?, ?, ?)",
                                   (file_id, file_path, user_id, datetime.utcnow().isoformat()))
                    cursor.execute("UPDATE users SET balance = balance + 30 WHERE user_id=?", (uploader_id,))
                cursor.execute("DELETE FROM pending WHERE id=?", (pid,))
                conn.commit()
                bot.send_message(uploader_id, f"🎉 Сіздің {ctype} мақұлданды! Рақмет!")
                bot.answer_callback_query(call.id, "Мақұлданды.")
            else:
                cursor.execute("DELETE FROM pending WHERE id=?", (pid,))
                conn.commit()
                bot.send_message(uploader_id, f"❌ Сіздің файл модерацияда қабылданбады.")
                bot.answer_callback_query(call.id, "Тасталды.")
        return

    if data == "back_main":
        with db_lock:
            ensure_user(user_id)
            bal = cursor.execute("SELECT balance FROM users WHERE user_id=?", (user_id,)).fetchone()[0]
        bot.edit_message_text(f"Сізде қазір: {bal}💸\nТөмендегі батырмаларды таңдаңыз:", call.message.chat.id, call.message.message_id, reply_markup=get_main_inline(user_id))
        return

# ---------------------------
# Flask endpoints
# ---------------------------
@app.route("/", methods=['GET'])
def index():
    return "Bot service is running", 200

@app.route(f"/{BOT_TOKEN}", methods=['POST'])
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
        full_url = f"{WEBHOOK_URL.rstrip('/')}/{BOT_TOKEN}"
        result = bot.set_webhook(url=full_url)
        logger.info(f"Webhook set -> {full_url} | result: {result}")
    except Exception:
        logger.exception("Failed to set webhook")

setup_webhook()

# ---------------------------
# Run Flask
# ---------------------------
if __name__ == "__main__":
    logger.info(f"Running Flask on port {PORT}")
    app.run(host="0.0.0.0", port=PORT)
