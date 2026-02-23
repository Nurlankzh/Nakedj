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
BOT_TOKEN = os.getenv("BOT_TOKEN") or "8419149602:AAHvLF3XmreCAQpvJy_8-RRJDH0g_qy9Oto"
ADMIN_ID = 6303091468  # админ айди
CHANNEL_USERNAME = "@kazakcombots"  # тексерілетін канал
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
    kb.row(KeyboardButton("💸 Мой бонус"), KeyboardButton("🔗 Реферал сілтеме"))
    kb.row(KeyboardButton("ℹ️ Ақпарат"))
    if admin:
        kb.row(KeyboardButton("💰 Бонус беру"), KeyboardButton("✅ Pending файлдар"), KeyboardButton("📊 Статистика"))
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
    
    # --- Видео көру ---
    if text == "🎥 Видео көру":
        if not check_subscription(user_id):
            bot.send_message(user_id, f"📢 Видео көру үшін {CHANNEL_USERNAME} каналына тіркеліңіз!")
            return
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
        return
    
    # --- Видео/Фото жіберу ---
    elif text == "➕ Видео/Фото жіберу":
        bot.send_message(user_id, "Файл жіберіңіз (админ мақұлдайды).")
        return
    
    # --- Мой бонус ---
    elif text == "💸 Мой бонус":
        with db_lock:
            bal = cursor.execute("SELECT balance FROM users WHERE user_id=?", (user_id,)).fetchone()[0]
        bot.send_message(user_id, f"Сізде қазір: {bal}💸")
        return
    
    # --- Реферал сілтеме ---
    elif text == "🔗 Реферал сілтеме":
        # Міне реферал толық дұрыс
        bot.send_message(user_id, f"Сіздің реферал сілтеме: https://t.me/Sallemkz_bot?start={user_id}")
        return
    
    # --- Ақпарат ---
    elif text == "ℹ️ Ақпарат":
        bot.send_message(user_id, f"Бот қалай жұмыс істейді:\n- Видео көру үшін бонус қажет\n- Видео/Фото жібере аласыз\n- Админ мақұлдайды\n- Реферал арқылы бонус аласыз")
        return
    
    # --- Админ --- Бонус беру
    elif text == "💰 Бонус беру" and user_id==ADMIN_ID:
        bot.send_message(user_id, "Формат: <user_id> <сома>")
        return
    
    # --- Админ --- Pending файлы
    elif text == "✅ Pending файлдар" and user_id==ADMIN_ID:
        with db_lock:
            pendings = cursor.execute("SELECT id, uploader_id, content_type, file_id, file_path FROM pending ORDER BY id ASC").fetchall()
        if not pendings:
            bot.send_message(user_id, "Pending файлдар жоқ.")
            return

        for pid, uploader, ctype, file_id, file_path in pendings:
            kb = InlineKeyboardMarkup()
            kb.add(InlineKeyboardButton("Мақұлдау", callback_data=f"approve_{pid}"))
            kb.add(InlineKeyboardButton("Растамау", callback_data=f"reject_{pid}"))

            if ctype == "video":
                if file_path and os.path.exists(file_path):
                    with open(file_path, "rb") as f:
                        bot.send_video(ADMIN_ID, f, caption=f"#{pid} {ctype} жіберген: {uploader}", reply_markup=kb)
                else:
                    bot.send_video(ADMIN_ID, file_id, caption=f"#{pid} {ctype} жіберген: {uploader}", reply_markup=kb)
            else:  # photo
                if file_path and os.path.exists(file_path):
                    with open(file_path, "rb") as f:
                        bot.send_photo(ADMIN_ID, f, caption=f"#{pid} {ctype} жіберген: {uploader}", reply_markup=kb)
                else:
                    bot.send_photo(ADMIN_ID, file_id, caption=f"#{pid} {ctype} жіберген: {uploader}", reply_markup=kb)

        return
    
    # --- Админ --- Статистика
    elif text == "📊 Статистика" and user_id==ADMIN_ID:
        with db_lock:
            users_count = cursor.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            videos_count = cursor.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
            pending_count = cursor.execute("SELECT COUNT(*) FROM pending").fetchone()[0]
        bot.send_message(user_id, f"📊 Статистика:\nҚолданушылар: {users_count}\nВидео: {videos_count}\nPending: {pending_count}")
        return
    
    # --- Админ Бонус беру командасы ---
    elif user_id==ADMIN_ID:
        try:
            parts = text.split()
            target_id = int(parts[0])
            amount = int(parts[1])
            cursor.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (amount, target_id))
            conn.commit()
            bot.send_message(user_id, f"{amount}💸 {target_id}-қа берілді.")
            bot.send_message(target_id, f"🎉 Сізге {amount}💸 берілді!")
        except:
            pass
        return
    
    # Басқа хабарламалар
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
# Callback handler for approve/reject
# ---------------------------
@bot.callback_query_handler(func=lambda c: True)
def handle_cb(call):
    data = call.data
    user_id = call.from_user.id
    if user_id!=ADMIN_ID:
        bot.answer_callback_query(call.id, "Тек админ.")
        return
    if data.startswith("approve_") or data.startswith("reject_"):
        action, pid = data.split("_")
        pid = int(pid)
        with db_lock:
            p = cursor.execute("SELECT uploader_id, content_type, file_id, file_path FROM pending WHERE id=?", (pid,)).fetchone()
            if not p:
                bot.answer_callback_query(call.id, "Pending жоқ")
                return
            uploader_id, ctype, file_id, file_path = p
            if action=="approve":
                if ctype=="video":
                    cursor.execute("INSERT INTO videos (file_id, file_path, added_by, created_at) VALUES (?, ?, ?, ?)",
                                   (file_id, file_path, user_id, datetime.utcnow().isoformat()))
                    cursor.execute("UPDATE users SET balance = balance + 12 WHERE user_id=?", (uploader_id,))
                else:
                    cursor.execute("INSERT INTO photos (file_id, file_path, added_by, created_at) VALUES (?, ?, ?, ?)",
                                   (file_id, file_path, user_id, datetime.utcnow().isoformat()))
                    cursor.execute("UPDATE users SET balance = balance + 12 WHERE user_id=?", (uploader_id,))
                cursor.execute("DELETE FROM pending WHERE id=?", (pid,))
                conn.commit()
                bot.send_message(uploader_id, f"🎉 Сіздің {ctype} мақұлданды! +12💸 берілді.")
                bot.answer_callback_query(call.id, "Мақұлданды")
            else:
                cursor.execute("DELETE FROM pending WHERE id=?", (pid,))
                conn.commit()
                bot.send_message(uploader_id, f"❌ Сіздің файл мақұлданбады.")
                bot.answer_callback_query(call.id, "Тасталды")

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
