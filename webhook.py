import os
import logging
import sqlite3
import threading
from datetime import datetime
from flask import Flask, request, redirect, url_for, escape

import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# ---------------------------
# CONFIG (HARDCODED FALLBACK)
# Prefer using environment variables (Render -> Environment)
# ---------------------------
# *** Your token is inserted here because you asked to include it. ***
BOT_TOKEN = os.getenv("BOT_TOKEN") or "8419149602:AAHvLF3XmreCAQpvJy_8-RRJDH0g_qy9Oto"
ADMIN_ID = int(os.getenv("ADMIN_ID") or "6927494520")
# Set WEBHOOK_URL to your Render public URL, e.g. "https://nakedj-7-g6vy.onrender.com"
WEBHOOK_URL = os.getenv("WEBHOOK_URL") or "https://nakedj-7-g6vy.onrender.com"
VIDEO_DIR = os.getenv("VIDEO_DIR") or "videos"
DB_FILE = os.getenv("DB_FILE") or "data.db"
PORT = int(os.getenv("PORT") or 10000)
# Optional simple web admin password (use env in production)
ADMIN_WEB_PASS = os.getenv("ADMIN_WEB_PASS") or "change_this_password"

# ---------------------------
# Logging (debug)
# ---------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("nakedj")
logger.info("Starting webhook.py module...")

# ---------------------------
# Ensure folders
# ---------------------------
os.makedirs(VIDEO_DIR, exist_ok=True)

# ---------------------------
# Bot + Flask + DB init
# ---------------------------
bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# sqlite (single file DB). Allow cross-thread usage (we use lock).
conn = sqlite3.connect(DB_FILE, check_same_thread=False)
cursor = conn.cursor()
db_lock = threading.Lock()

# Create tables if not exists
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
    """Download file from Telegram and save to disk; return path."""
    try:
        file_info = bot.get_file(file_id)
        b = bot.download_file(file_info.file_path)
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
        ext = ".mp4" if is_video else ".jpg"
        safe_id = file_id.replace("/", "_")
        fname = f"{ts}_{safe_id}{ext}"
        path = os.path.join(VIDEO_DIR, fname)
        with open(path, "wb") as f:
            f.write(b)
        logger.info(f"Saved file to {path}")
        return path
    except Exception:
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
# Telegram Handlers
# ---------------------------
@bot.message_handler(commands=['start'])
def cmd_start(message):
    try:
        user_id = message.from_user.id
        args = message.text.split()
        ref = None
        if len(args) > 1:
            a = args[1]
            if a.isdigit():
                ref = int(a)
            elif a.startswith("start=") and a[6:].isdigit():
                ref = int(a[6:])
        ensure_user(user_id, invited_by=ref)
        # credit inviter once (if exists)
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
        logger.info(f"/start from {user_id} — balance {bal}")
    except Exception:
        logger.exception("cmd_start error")

@bot.message_handler(content_types=['text'])
def handle_text(message):
    user_id = message.from_user.id
    txt = message.text or ""
    logger.info(f"TEXT from {user_id}: {txt}")
    # admin quick panel via chat
    if txt.startswith("/admin") and user_id == ADMIN_ID:
        with db_lock:
            users_count = cursor.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            videos_count = cursor.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
            pending_count = cursor.execute("SELECT COUNT(*) FROM pending").fetchone()[0]
        bot.send_message(ADMIN_ID, f"📊 Admin stats:\nUsers: {users_count}\nVideos: {videos_count}\nPending: {pending_count}")
        return
    # otherwise show main menu
    ensure_user(user_id)
    with db_lock:
        bal = cursor.execute("SELECT balance FROM users WHERE user_id=?", (user_id,)).fetchone()[0]
    bot.send_message(user_id, f"Сіз жаздыңыз: {escape(txt)}\nСізде: {bal}💸", reply_markup=get_main_inline(user_id))

@bot.message_handler(content_types=['video','photo','document'])
def handle_media(message):
    user_id = message.from_user.id
    is_video = (message.content_type == 'video') or (
        message.content_type == 'document' and getattr(message.document, "mime_type", "") and "video" in message.document.mime_type
    )
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
        logger.exception("handle_media save error")
        return

    # admin direct add
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
        logger.info(f"Admin uploaded and saved: {path}")
        return

    # normal user => pending
    with db_lock:
        cursor.execute("INSERT INTO pending (uploader_id, content_type, file_id, file_path, created_at) VALUES (?, ?, ?, ?, ?)",
                       (user_id, 'video' if is_video else 'photo', file_id, path, datetime.utcnow().isoformat()))
        pid = cursor.lastrowid
        conn.commit()
    bot.send_message(user_id, "✅ Файл модерацияға жіберілді. Админ мақұлдағаннан кейін хабарланады.")
    logger.info(f"User {user_id} uploaded pending #{pid} -> {path}")

    # notify admin with inline approve/reject
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
        try:
            bot.send_message(ADMIN_ID, f"New pending #{pid} from {user_id}. Approve/Reject in chat.", reply_markup=kb)
        except Exception:
            logger.exception("failed to notify admin about pending")

@bot.callback_query_handler(func=lambda c: True)
def handle_cb(call):
    data = call.data or ""
    uid = call.from_user.id
    logger.info(f"Callback from {uid}: {data}")
    try:
        if data == "buy_channel":
            kb = InlineKeyboardMarkup()
            kb.add(InlineKeyboardButton("Басты мәзірге оралу", callback_data="back_main"))
            bot.edit_message_text("Канал сатып алғыңыз келсе жазып жіберіңіз: @KazHubALU",
                                  call.message.chat.id, call.message.message_id, reply_markup=kb)
            return
        if data == "channels":
            kb = InlineKeyboardMarkup()
            kb.add(InlineKeyboardButton("Басты мәзірге оралу", callback_data="back_main"))
            text = "Тіркеліңіз — барлық жаңалықтар:\n1) https://t.me/+XRoxE_8bUM1mMmIy\n2) https://t.me/bokseklub"
            bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=kb)
            return
        if data == "watch_video":
            with db_lock:
                u = cursor.execute("SELECT balance, progress_video FROM users WHERE user_id=?", (uid,)).fetchone()
                if not u:
                    bot.answer_callback_query(call.id, "Алдымен /start басыңыз.")
                    return
                balance, progress = u
                rows = cursor.execute("SELECT id, file_id, file_path FROM videos ORDER BY id ASC").fetchall()
                if not rows:
                    bot.answer_callback_query(call.id, "🎬 Видеолар жоқ.")
                    return
                if uid != ADMIN_ID and balance < 3:
                    if balance <= 0:
                        bot.answer_callback_query(call.id, "Сіздің балансыңыз жетпейді. Дос шақырыңыз: " + f"https://t.me/{bot.get_me().username}?start={uid}")
                        return
                    bot.answer_callback_query(call.id, "Видео көру үшін 3💸 қажет.")
                    return
                idx = progress if progress < len(rows) else 0
                row = rows[idx]
                file_id, file_path = row[1], row[2]
                try:
                    if file_path and os.path.exists(file_path):
                        with open(file_path, "rb") as f:
                            bot.send_video(uid, f, caption=f"✅ Видео көрсетілді. Қалған: {(balance-3) if uid!=ADMIN_ID else balance}💸")
                    else:
                        bot.send_video(uid, file_id, caption=f"✅ Видео көрсетілді. Қалған: {(balance-3) if uid!=ADMIN_ID else balance}💸")
                except Exception:
                    bot.answer_callback_query(call.id, "Видео жібергенде қате.")
                    logger.exception("send video error")
                    return
                if uid != ADMIN_ID:
                    cursor.execute("UPDATE users SET balance=?, progress_video=? WHERE user_id=?", (max(balance-3,0), idx+1, uid))
                else:
                    cursor.execute("UPDATE users SET progress_video=? WHERE user_id=?", (idx+1, uid))
                conn.commit()
                bot.answer_callback_query(call.id, "Видео алынды.")
            return
        if data == "upload_menu":
            kb = InlineKeyboardMarkup()
            kb.add(InlineKeyboardButton("Видео жіберу (админға)" , callback_data="upload_video_hint"))
            kb.add(InlineKeyboardButton("Фото жіберу (админға)" , callback_data="upload_photo_hint"))
            kb.add(InlineKeyboardButton("Басты мәзірге оралу", callback_data="back_main"))
            bot.edit_message_text("Видео немесе фото жүктегіңіз келсе соны таңдаңыз. (Файлды осы чатқа жүктеңіз)",
                                  call.message.chat.id, call.message.message_id, reply_markup=kb)
            return
        if data.startswith("approve_") or data.startswith("reject_"):
            # admin-only actions
            if uid != ADMIN_ID:
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
                                       (file_id, file_path, uid, datetime.utcnow().isoformat()))
                        cursor.execute("UPDATE users SET balance = balance + 40 WHERE user_id=?", (uploader_id,))
                        conn.commit()
                        bot.send_message(uploader_id, "🎉 Сіздің видеоңыз мақұлданды! +40💸")
                    else:
                        cursor.execute("INSERT INTO photos (file_id, file_path, added_by, created_at) VALUES (?, ?, ?, ?)",
                                       (file_id, file_path, uid, datetime.utcnow().isoformat()))
                        cursor.execute("UPDATE users SET balance = balance + 30 WHERE user_id=?", (uploader_id,))
                        conn.commit()
                        bot.send_message(uploader_id, "🎉 Сіздің фотоңыз мақұлданды! +30💸")
                    cursor.execute("DELETE FROM pending WHERE id=?", (pid,))
                    conn.commit()
                    bot.answer_callback_query(call.id, "Мақұлданды және авторға сыйақы берілді.")
                    try:
                        bot.edit_message_text(f"Pending #{pid} — мақұлданды ✅", call.message.chat.id, call.message.message_id)
                    except Exception:
                        pass
                else:
                    cursor.execute("DELETE FROM pending WHERE id=?", (pid,))
                    conn.commit()
                    bot.answer_callback_query(call.id, "Тасталды.")
                    bot.send_message(uploader_id, "❌ Сіздің файл модерацияда қабылданбады.")
                    try:
                        bot.edit_message_text(f"Pending #{pid} — тасталды ❌", call.message.chat.id, call.message.message_id)
                    except Exception:
                        pass
            return
        if data == "back_main":
            uid2 = call.from_user.id
            with db_lock:
                ensure_user(uid2)
                bal = cursor.execute("SELECT balance FROM users WHERE user_id=?", (uid2,)).fetchone()[0]
            bot.edit_message_text(f"Сізде қазір: {bal}💸\nТөмендегі батырмаларды таңдаңыз:", call.message.chat.id, call.message.message_id, reply_markup=get_main_inline(uid2))
            return
    except Exception:
        logger.exception("callback processing error")

# ---------------------------
# Flask endpoints: webhook + health + web admin panel
# ---------------------------
@app.route("/", methods=["GET"])
def index():
    return "Bot service is running ✅", 200

@app.route("/webhook", methods=["POST"])
def webhook_handler():
    try:
        json_str = request.get_data().decode("utf-8")
        update = telebot.types.Update.de_json(json_str)
        bot.process_new_updates([update])
    except Exception:
        logger.exception("Webhook processing error")
    return "", 200

# Simple web admin panel (protected by ?pass=ADMIN_WEB_PASS)
def require_pass(qpass):
    return qpass == ADMIN_WEB_PASS

@app.route("/admin", methods=["GET"])
def admin_panel():
    qpass = request.args.get("pass", "")
    if not require_pass(qpass):
        return f"<h3>Admin panel — Forbidden. Provide ?pass=SECRET</h3>", 403
    # build simple HTML summary + pending list
    html = ["<h2>Admin panel</h2>"]
    with db_lock:
        users = cursor.execute("SELECT user_id, balance, progress_video, invited_by FROM users ORDER BY rowid DESC LIMIT 200").fetchall()
        pending = cursor.execute("SELECT id, uploader_id, content_type, file_path, created_at FROM pending ORDER BY id DESC LIMIT 200").fetchall()
        videos = cursor.execute("SELECT id, file_path, added_by, created_at FROM videos ORDER BY id DESC LIMIT 200").fetchall()
    html.append("<h3>Users (latest 200)</h3><table border=1 cellpadding=4><tr><th>user_id</th><th>balance</th><th>progress</th><th>invited_by</th></tr>")
    for u in users:
        html.append(f"<tr><td>{u[0]}</td><td>{u[1]}</td><td>{u[2]}</td><td>{u[3]}</td></tr>")
    html.append("</table>")

    html.append("<h3>Pending (approve/reject)</h3><table border=1 cellpadding=4><tr><th>ID</th><th>uploader</th><th>type</th><th>path</th><th>created_at</th><th>actions</th></tr>")
    for p in pending:
        pid, upl, ctype, path, created = p
        approve_url = f"/admin/approve/{pid}?pass={ADMIN_WEB_PASS}"
        reject_url = f"/admin/reject/{pid}?pass={ADMIN_WEB_PASS}"
        html.append(f"<tr><td>{pid}</td><td>{upl}</td><td>{ctype}</td><td>{escape(path)}</td><td>{created}</td><td><a href='{approve_url}'>Approve</a> | <a href='{reject_url}'>Reject</a></td></tr>")
    html.append("</table>")

    html.append("<h3>Videos (latest 200)</h3><table border=1 cellpadding=4><tr><th>ID</th><th>path</th><th>added_by</th><th>created</th></tr>")
    for v in videos:
        html.append(f"<tr><td>{v[0]}</td><td>{escape(v[1])}</td><td>{v[2]}</td><td>{v[3]}</td></tr>")
    html.append("</table>")

    return "\n".join(html), 200

@app.route("/admin/approve/<int:pid>", methods=["GET"])
def admin_approve(pid):
    qpass = request.args.get("pass", "")
    if not require_pass(qpass):
        return "Forbidden", 403
    with db_lock:
        p = cursor.execute("SELECT uploader_id, content_type, file_id, file_path FROM pending WHERE id=?", (pid,)).fetchone()
        if not p:
            return f"Pending #{pid} not found", 404
        uploader_id, ctype, file_id, file_path = p
        if ctype == "video":
            cursor.execute("INSERT INTO videos (file_id, file_path, added_by, created_at) VALUES (?, ?, ?, ?)",
                           (file_id, file_path, ADMIN_ID, datetime.utcnow().isoformat()))
            cursor.execute("UPDATE users SET balance = balance + 40 WHERE user_id=?", (uploader_id,))
            conn.commit()
            try:
                bot.send_message(uploader_id, "🎉 Сіздің видеоңыз мақұлданды! +40💸")
            except Exception:
                logger.exception("notify uploader fail")
        else:
            cursor.execute("INSERT INTO photos (file_id, file_path, added_by, created_at) VALUES (?, ?, ?, ?)",
                           (file_id, file_path, ADMIN_ID, datetime.utcnow().isoformat()))
            cursor.execute("UPDATE users SET balance = balance + 30 WHERE user_id=?", (uploader_id,))
            conn.commit()
            try:
                bot.send_message(uploader_id, "🎉 Сіздің фотоңыз мақұлданды! +30💸")
            except Exception:
                logger.exception("notify uploader fail")
        cursor.execute("DELETE FROM pending WHERE id=?", (pid,))
        conn.commit()
    return redirect(url_for("admin_panel", pass=ADMIN_WEB_PASS))

@app.route("/admin/reject/<int:pid>", methods=["GET"])
def admin_reject(pid):
    qpass = request.args.get("pass", "")
    if not require_pass(qpass):
        return "Forbidden", 403
    with db_lock:
        p = cursor.execute("SELECT uploader_id FROM pending WHERE id=?", (pid,)).fetchone()
        if not p:
            return f"Pending #{pid} not found", 404
        uploader_id = p[0]
        cursor.execute("DELETE FROM pending WHERE id=?", (pid,))
        conn.commit()
        try:
            bot.send_message(uploader_id, "❌ Сіздің файл модерацияда қабылданбады.")
        except Exception:
            logger.exception("notify uploader fail")
    return redirect(url_for("admin_panel", pass=ADMIN_WEB_PASS))

# ---------------------------
# Webhook setup (set webhook url on start)
# ---------------------------
def setup_webhook():
    try:
        bot.remove_webhook()
        full_url = WEBHOOK_URL.rstrip("/") + "/webhook"
        result = bot.set_webhook(url=full_url)
        logger.info(f"Set webhook -> {full_url}  result: {result}")
    except Exception:
        logger.exception("Failed to set webhook")

# Call once on start
setup_webhook()

# ---------------------------
# Run flask (for local/testing only)
# For production Render you run with gunicorn or 'python webhook.py'
# ---------------------------
if __name__ == "__main__":
    logger.info(f"Starting Flask app on port {PORT}")
    app.run(host="0.0.0.0", port=PORT)
