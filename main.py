import os
import sqlite3
import threading
from datetime import datetime
from flask import Flask, request
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# === Конфиг ===
BOT_TOKEN = "8419149602:AAHvLF3XmreCAQpvJy_8-RRJDH0g_qy9Oto"  # Сіздің бот токеніңіз
ADMIN_ID = 6927494520  # Сіздің Telegram ID
WEBHOOK_URL = "https://nakedj-5-hscc.onrender.com"  # Сіздің сервер URL

VIDEO_DIR = "videos"
DB_FILE = "data.db"
os.makedirs(VIDEO_DIR, exist_ok=True)

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# === Database ===
conn = sqlite3.connect(DB_FILE, check_same_thread=False)
cursor = conn.cursor()
lock = threading.Lock()

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

# === Helpers ===
def get_main_inline(user_id):
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("Канал алу", callback_data="buy_channel"))
    kb.add(InlineKeyboardButton("Арналарымыз", callback_data="channels"))
    kb.add(InlineKeyboardButton("🎥 Видео", callback_data="watch_video"))
    kb.add(InlineKeyboardButton("➕ Видео/Фото қосу", callback_data="upload_menu"))
    return kb

def save_file_from_message(file_id, is_video=True):
    file_info = bot.get_file(file_id)
    b = bot.download_file(file_info.file_path)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
    ext = ".mp4" if is_video else ".jpg"
    fname = f"{ts}_{file_id}{ext}"
    path = os.path.join(VIDEO_DIR, fname)
    with open(path, "wb") as f:
        f.write(b)
    return path

# === /start ===
@bot.message_handler(commands=['start'])
def cmd_start(message):
    user_id = message.from_user.id
    args = message.text.split()
    ref = args[1] if len(args) > 1 else None
    with lock:
        exists = cursor.execute("SELECT 1 FROM users WHERE user_id=?", (user_id,)).fetchone()
        if not exists:
            invited_by = int(ref) if ref and ref.isdigit() and int(ref) != user_id else None
            cursor.execute("INSERT INTO users (user_id, balance, invited_by) VALUES (?, ?, ?)",
                           (user_id, 12, invited_by))
            conn.commit()
            if invited_by:
                cursor.execute("UPDATE users SET balance = balance + 12 WHERE user_id=?", (invited_by,))
                conn.commit()
                try: bot.send_message(invited_by, f"🎉 Сіз жаңа қолданушы шақырдыңыз! +12💸 берілді.")
                except: pass
    with lock:
        bal = cursor.execute("SELECT balance FROM users WHERE user_id=?", (user_id,)).fetchone()[0]
    text = f"Сәлем 👋\nСізде қазір: {bal}💸\nТөмендегі батырмаларды таңдаңыз:"
    bot.send_message(user_id, text, reply_markup=get_main_inline(user_id))

# === Callback queries ===
@bot.callback_query_handler(func=lambda c: True)
def handle_cb(call):
    user_id = call.from_user.id
    data = call.data

    # --- Main buttons ---
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
        with lock:
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
                bot.answer_callback_query(call.id, "Біздің видео көру үшін 3💸 керек.")
                return
            idx = progress if progress < len(rows) else 0
            row = rows[idx]
            file_id = row[1]
            file_path = row[2]
            try:
                if file_path and os.path.exists(file_path):
                    with open(file_path, "rb") as f:
                        bot.send_video(user_id, f, caption=f"✅ Видео көрсетілді. Қалған: {(balance-3) if user_id!=ADMIN_ID else balance}💸")
                else:
                    bot.send_video(user_id, file_id, caption=f"✅ Видео көрсетілді. Қалған: {(balance-3) if user_id!=ADMIN_ID else balance}💸")
            except Exception:
                bot.answer_callback_query(call.id, "Видео жібергенде қате. Админге хабарлаңыз.")
                return
            if user_id != ADMIN_ID:
                cursor.execute("UPDATE users SET balance=?, progress_video=? WHERE user_id=?",
                               (max(balance-3,0), idx+1, user_id))
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
        bot.edit_message_text("Видео немесе фото жүктегіңіз келсе соны таңдаңыз. (Файлды осы чатқа жүктеңіз)",
                              call.message.chat.id, call.message.message_id, reply_markup=kb)
        return

    if data == "upload_video_hint":
        bot.answer_callback_query(call.id, "Видео жіберіңіз — ол алдымен модерацияға түседі.")
        return

    if data == "upload_photo_hint":
        bot.answer_callback_query(call.id, "Фото жіберіңіз — ол алдымен модерацияға түседі.")
        return

    if data == "back_main":
        with lock:
            bal = cursor.execute("SELECT balance FROM users WHERE user_id=?", (user_id,)).fetchone()[0]
        bot.edit_message_text(f"Сізде қазір: {bal}💸\nТөмендегі батырмаларды таңдаңыз:",
                              call.message.chat.id, call.message.message_id, reply_markup=get_main_inline(user_id))
        return

# === Media handler ===
@bot.message_handler(content_types=['video','photo'])
def handle_media(message):
    user_id = message.from_user.id
    is_video = message.content_type == 'video'
    file_id = message.video.file_id if is_video else message.photo[-1].file_id

    try:
        path = save_file_from_message(file_id, is_video=is_video)
    except Exception as e:
        bot.send_message(user_id, f"Файл сақталмады: {e}")
        return

    if user_id == ADMIN_ID:
        with lock:
            if is_video:
                cursor.execute("INSERT INTO videos (file_id, file_path, added_by, created_at) VALUES (?, ?, ?, ?)",
                               (file_id, path, user_id, datetime.utcnow().isoformat()))
            else:
                cursor.execute("INSERT INTO photos (file_id, file_path, added_by, created_at) VALUES (?, ?, ?, ?)",
                               (file_id, path, user_id, datetime.utcnow().isoformat()))
            conn.commit()
        bot.send_message(user_id, "✅ Файл сақталды (admin).")
        return

    with lock:
        cursor.execute("INSERT INTO pending (uploader_id, content_type, file_id, file_path, created_at) VALUES (?,?,?,?,?)",
                       (user_id, 'video' if is_video else 'photo', file_id, path, datetime.utcnow().isoformat()))
        pid = cursor.lastrowid
        conn.commit()

    bot.send_message(user_id, "✅ Файл модерацияға жіберілді. Админ мақұлдағаннан кейін хабарланады.")
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("Approve (+40/+30)", callback_data=f"approve_vid_{pid}" if is_video else f"approve_ph_{pid}"))
    kb.add(InlineKeyboardButton("Reject", callback_data=f"reject_vid_{pid}" if is_video else f"reject_ph_{pid}"))
    try:
        if is_video:
            with open(path,"rb") as f: bot.send_video(ADMIN_ID,f,caption=f"New pending video #{pid} from {user_id}",reply_markup=kb)
        else:
            with open(path,"rb") as f: bot.send_photo(ADMIN_ID,f,caption=f"New pending photo #{pid} from {user_id}",reply_markup=kb)
    except:
        bot.send_message(ADMIN_ID,f"New pending ({'video' if is_video else 'photo'}) #{pid} from {user_id}. Approve/Reject in chat.",reply_markup=kb)

# === Flask endpoints ===
@app.route("/")
def index():
    return "Bot is live ✅",200

@app.route(f"/{BOT_TOKEN}",methods=['POST'])
def webhook():
    try:
        update = telebot.types.Update.de_json(request.stream.read().decode('utf-8'))
        bot.process_new_updates([update])
    except Exception as e:
        print("Webhook process error:",e)
    return "ok",200

# === Deployment setup ===
def set_webhook():
    try:
        bot.remove_webhook()
        bot.set_webhook(url=f"{WEBHOOK_URL}/{BOT_TOKEN}")
        print("Webhook set successfully!")
    except Exception as e:
        print("Error setting webhook:",e)

set_webhook()  # Render-де бір рет орындалады

if __name__=="__main__":
    app.run(host="0.0.0.0",port=int(os.environ.get("PORT",10000)))
