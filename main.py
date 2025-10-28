import os
import sqlite3
import threading
import time
from datetime import datetime
from flask import Flask, request
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# === Конфиг: env-дан оқимыз ===
BOT_TOKEN = os.environ.get("BOT_TOKEN") or "PASTE_YOUR_TOKEN_HERE"
ADMIN_ID = int(os.environ.get("ADMIN_ID", "6927494520"))
WEBHOOK_URL = os.environ.get("WEBHOOK_URL") or "https://your-render-url.onrender.com"
VIDEO_DIR = os.environ.get("VIDEO_DIR", "videos")
DB_FILE = os.environ.get("DB_FILE", "data.db")

# === файл/папка дайындау ===
os.makedirs(VIDEO_DIR, exist_ok=True)

# === Bot & Flask ===
bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# === DB (sqlite) ===
conn = sqlite3.connect(DB_FILE, check_same_thread=False)
cursor = conn.cursor()
lock = threading.Lock()

# users: user_id PRIMARY, balance, progress_video, invited_by
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    balance INTEGER DEFAULT 12,
    progress_video INTEGER DEFAULT 0,
    invited_by INTEGER
)
""")
# pending uploads from users: id, uploader_id, type ('video'|'photo'), file_id, file_path, created_at
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
# approved videos/photos:
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
    # download file from telegram and save to VIDEO_DIR
    file_info = bot.get_file(file_id)
    b = bot.download_file(file_info.file_path)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
    ext = ".mp4" if is_video else ".jpg"
    fname = f"{ts}_{file_id}{ext}"
    path = os.path.join(VIDEO_DIR, fname)
    with open(path, "wb") as f:
        f.write(b)
    return path

# === /start handler ===
@bot.message_handler(commands=['start'])
def cmd_start(message):
    user_id = message.from_user.id
    args = message.text.split()
    ref = args[1] if len(args)>1 else None
    with lock:
        exists = cursor.execute("SELECT 1 FROM users WHERE user_id=?", (user_id,)).fetchone()
        if not exists:
            # default 12 balance
            invited_by = int(ref) if ref and ref.isdigit() and int(ref)!=user_id else None
            cursor.execute("INSERT INTO users (user_id, balance, invited_by) VALUES (?, ?, ?)",
                           (user_id, 12, invited_by))
            conn.commit()
            if invited_by:
                # give inviter 12
                cursor.execute("UPDATE users SET balance = balance + 12 WHERE user_id=?", (invited_by,))
                conn.commit()
                try:
                    bot.send_message(invited_by, f"🎉 Сіз жаңа қолданушы шақырдыңыз! +12💸 берілді.")
                except: pass

    # Send welcome + inline menu
    with lock:
        bal = cursor.execute("SELECT balance FROM users WHERE user_id=?", (user_id,)).fetchone()[0]
    text = f"Сәлем 👋\nСізде қазір: {bal}💸\nТөмендегі батырмаларды таңдаңыз:"
    bot.send_message(user_id, text, reply_markup=get_main_inline(user_id))

# === Callback queries (inline buttons) ===
@bot.callback_query_handler(func=lambda c: True)
def handle_cb(call):
    user_id = call.from_user.id
    data = call.data

    if data == "buy_channel":
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("Басты мәзірге оралу", callback_data="back_main"))
        bot.edit_message_text("Канал сатып алғыңыз келсе жазыңыз @KazHubALU", call.message.chat.id, call.message.message_id, reply_markup=kb)
        return

    if data == "channels":
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("Басты мәзірге оралу", callback_data="back_main"))
        text = "Тіркеліңіз — барлық жаңалықтар осында:\n1) https://t.me/+XRoxE_8bUM1mMmIy\n2) https://t.me/bokseklub"
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=kb)
        return

    if data == "watch_video":
        # send next video in sequence if user has balance >=3 or admin
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
                # if balance 0 - give referral link
                if balance <= 0:
                    bot.answer_callback_query(call.id, "Сіздің балансыңыз жетпейді. Дос шақырыңыз: " + f"https://t.me/{bot.get_me().username}?start={user_id}")
                    return
                bot.answer_callback_query(call.id, "Біздің видео көру үшін 3💸 керек.")
                return
            idx = progress if progress < len(rows) else 0
            row = rows[idx]
            file_id = row[1]
            file_path = row[2]
            try:
                # prefer local file
                if file_path and os.path.exists(file_path):
                    with open(file_path, "rb") as f:
                        bot.send_video(user_id, f, caption=f"✅ Видео көрсетілді. Қалған: { (balance-3) if user_id!=ADMIN_ID else balance }💸")
                else:
                    bot.send_video(user_id, file_id, caption=f"✅ Видео көрсетілді. Қалған: { (balance-3) if user_id!=ADMIN_ID else balance }💸")
            except Exception as e:
                bot.answer_callback_query(call.id, "Видео жібергенде қате. Админге хабарлаңыз.")
                return
            # update progress and balance
            if user_id != ADMIN_ID:
                cursor.execute("UPDATE users SET balance = ?, progress_video = ? WHERE user_id=?",
                               (max(balance-3, 0), idx+1, user_id))
            else:
                cursor.execute("UPDATE users SET progress_video = ? WHERE user_id=?", (idx+1, user_id))
            conn.commit()
            bot.answer_callback_query(call.id, "Видео алынды.")

        return

    if data == "upload_menu":
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("Видео жіберу (админға жіберіледі)", callback_data="upload_video_hint"))
        kb.add(InlineKeyboardButton("Фото жіберу (админға жіберіледі)", callback_data="upload_photo_hint"))
        kb.add(InlineKeyboardButton("Басты мәзірге оралу", callback_data="back_main"))
        bot.edit_message_text("Видео немесе фото жүктегіңіз келсе соны таңдаңыз. (Файлды осы чатқа жүктеңіз)", call.message.chat.id, call.message.message_id, reply_markup=kb)
        return

    if data == "upload_video_hint":
        bot.answer_callback_query(call.id, "Видео жіберіңіз — ол алдымен модерацияға түседі.")
        return

    if data == "upload_photo_hint":
        bot.answer_callback_query(call.id, "Фото жіберіңіз — ол алдымен модерацияға түседі.")
        return

    if data == "back_main":
        # edit back to main inline
        with lock:
            bal = cursor.execute("SELECT balance FROM users WHERE user_id=?", (user_id,)).fetchone()[0]
        bot.edit_message_text(f"Сізде қазір: {bal}💸\nТөмендегі батырмаларды таңдаңыз:", call.message.chat.id, call.message.message_id, reply_markup=get_main_inline(user_id))
        return

    # admin callbacks for pending items: format: approve_vid_{id} / reject_vid_{id} / approve_ph_{id} ...
    if data.startswith("approve_vid_") or data.startswith("reject_vid_") or data.startswith("approve_ph_") or data.startswith("reject_ph_"):
        if user_id != ADMIN_ID:
            bot.answer_callback_query(call.id, "Тек админ ғана.")
            return
        parts = data.split("_")
        action = parts[0]  # approve/reject
        typ = parts[1]     # vid/ph (we used naming with underscore)
        pid = int(parts[-1])
        # fetch pending row
        with lock:
            p = cursor.execute("SELECT uploader_id, content_type, file_id, file_path FROM pending WHERE id=?", (pid,)).fetchone()
            if not p:
                bot.answer_callback_query(call.id, "Pending табылмады.")
                return
            uploader_id, ctype, file_id, file_path = p
            if action == "approve":
                if ctype == "video":
                    # move to videos
                    cursor.execute("INSERT INTO videos (file_id, file_path, added_by, created_at) VALUES (?, ?, ?, ?)",
                                   (file_id, file_path, user_id, datetime.utcnow().isoformat()))
                    # give uploader 40
                    cursor.execute("UPDATE users SET balance = balance + 40 WHERE user_id=?", (uploader_id,))
                    conn.commit()
                    bot.send_message(uploader_id, "🎉 Сіздің видеоңыз мақұлданды! +40💸 қосылды. Рақмет!")
                elif ctype == "photo":
                    cursor.execute("INSERT INTO photos (file_id, file_path, added_by, created_at) VALUES (?, ?, ?, ?)",
                                   (file_id, file_path, user_id, datetime.utcnow().isoformat()))
                    cursor.execute("UPDATE users SET balance = balance + 30 WHERE user_id=?", (uploader_id,))
                    conn.commit()
                    bot.send_message(uploader_id, "🎉 Сіздің фотоңыз мақұлданды! +30💸 қосылды. Рақмет!")
                # delete pending
                cursor.execute("DELETE FROM pending WHERE id=?", (pid,))
                conn.commit()
                bot.answer_callback_query(call.id, "Мақұлданды және авторға сыйақы берілді.")
                # edit admin message
                try:
                    bot.edit_message_text(f"Pending #{pid} — мақұлданды ✅", call.message.chat.id, call.message.message_id)
                except: pass
            else:
                # reject
                cursor.execute("DELETE FROM pending WHERE id=?", (pid,))
                conn.commit()
                bot.answer_callback_query(call.id, "Тасталды.")
                bot.send_message(uploader_id, "❌ Сіздің файл модерацияда қабылданбады.")
                try:
                    bot.edit_message_text(f"Pending #{pid} — тасталды ❌", call.message.chat.id, call.message.message_id)
                except: pass
        return

# === Receiving media (video/photo) ===
@bot.message_handler(content_types=['video', 'photo'])
def handle_media(message):
    user_id = message.from_user.id
    is_video = (message.content_type == 'video')
    # admin direct add: if admin and wants to add directly to approved:
    if user_id == ADMIN_ID:
        # save file and add immediately to videos/photos
        file_id = message.video.file_id if is_video else message.photo[-1].file_id
        try:
            path = save_file_from_message(file_id, is_video=is_video)
        except Exception as e:
            bot.send_message(user_id, f"Файл сақталмады: {e}")
            return
        with lock:
            if is_video:
                cursor.execute("INSERT INTO videos (file_id, file_path, added_by, created_at) VALUES (?, ?, ?, ?)",
                               (file_id, path, user_id, datetime.utcnow().isoformat()))
            else:
                cursor.execute("INSERT INTO photos (file_id, file_path, added_by, created_at) VALUES (?, ?, ?, ?)",
                               (file_id, path, user_id, datetime.utcnow().isoformat()))
            conn.commit()
            total_v = cursor.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
            total_p = cursor.execute("SELECT COUNT(*) FROM photos").fetchone()[0]
        bot.send_message(user_id, f"✅ Қуаныштымын! Файл сақталды. (Videos: {total_v}, Photos: {total_p})")
        return

    # regular user upload -> pending
    file_id = message.video.file_id if is_video else message.photo[-1].file_id
    try:
        path = save_file_from_message(file_id, is_video=is_video)
    except Exception as e:
        bot.send_message(user_id, f"Файл сақталмады: {e}")
        return

    with lock:
        cursor.execute("INSERT INTO pending (uploader_id, content_type, file_id, file_path, created_at) VALUES (?, ?, ?, ?, ?)",
                       (user_id, 'video' if is_video else 'photo', file_id, path, datetime.utcnow().isoformat()))
        pid = cursor.lastrowid
        conn.commit()

    # notify uploader
    bot.send_message(user_id, "✅ Файл модерацияға жіберілді. Админ мақұлдағаннан кейін сізге хабарланады.")

    # notify admin with approve/reject inline buttons
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("Approve (+40/+30)", callback_data=f"approve_vid_{pid}" if is_video else f"approve_ph_{pid}"))
    kb.add(InlineKeyboardButton("Reject", callback_data=f"reject_vid_{pid}" if is_video else f"reject_ph_{pid}"))
    # send small info to admin with preview
    try:
        if is_video:
            with open(path, "rb") as f:
                bot.send_video(ADMIN_ID, f, caption=f"New pending video #{pid} from {user_id}", reply_markup=kb)
        else:
            with open(path, "rb") as f:
                bot.send_photo(ADMIN_ID, f, caption=f"New pending photo #{pid} from {user_id}", reply_markup=kb)
    except Exception as e:
        # maybe admin can't get file (large) — just notify
        bot.send_message(ADMIN_ID, f"New pending ({'video' if is_video else 'photo'}) #{pid} from {user_id}. Approve/Reject in chat.", reply_markup=kb)

# === Root and webhook endpoints ===
@app.route("/")
def index():
    try:
        bot.remove_webhook()
        bot.set_webhook(url=f"{WEBHOOK_URL}/{BOT_TOKEN}")
        return "Bot is live ✅", 200
    except Exception as e:
        return f"Webhook setup error: {e}", 500

@app.route(f"/{BOT_TOKEN}", methods=['POST'])
def webhook():
    try:
        update = telebot.types.Update.de_json(request.stream.read().decode('utf-8'))
        bot.process_new_updates([update])
    except Exception as e:
        print("Webhook process error:", e)
    return "ok", 200

if __name__ == "__main__":
    # For local debugging only:
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
