import os
import logging
import sqlite3
import threading
import time
from datetime import datetime, timedelta
from flask import Flask, request
import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

# ---------------------------
# CONFIG
# ---------------------------
BOT_TOKEN = os.getenv("BOT_TOKEN") or "8419149602:AAHvLF3XmreCAQpvJy_8-RRJDH0g_qy9Oto"
ADMIN_ID = 6303091468
CHANNEL_USERNAME = "@kazakcombots"
WEBHOOK_URL = os.getenv("WEBHOOK_URL") or "https://web-production-0cd8e.up.railway.app"
VIDEO_DIR = "videos"
DB_FILE = "data.db"
PORT = int(os.getenv("PORT") or 10000)

# ---------------------------
# Logging
# ---------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)
logger.info("Starting bot...")

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
        invited_by INTEGER,
        is_adult INTEGER DEFAULT 0
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
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS lottery (
        user_id INTEGER PRIMARY KEY,
        name TEXT,
        invites INTEGER DEFAULT 0,
        participating INTEGER DEFAULT 0,
        joined_at TEXT
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
            if invited_by and invited_by != user_id:
                cursor.execute("UPDATE users SET balance = balance + 6 WHERE user_id=?", (invited_by,))
                cursor.execute("INSERT INTO lottery(user_id, name, invites, participating, joined_at) VALUES (?, ?, 1, 1, ?) "
                               "ON CONFLICT(user_id) DO UPDATE SET invites = invites + 1",
                               (invited_by, f"User {invited_by}", datetime.utcnow().isoformat()))
                conn.commit()
                try:
                    bot.send_message(invited_by, "🎉 Сіз жаңа қолданушы шақырдыңыз! +6💸 берілді.")
                except: pass

def get_main_keyboard(admin=False, lottery_active=False):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(KeyboardButton("🎥 Видео көру"), KeyboardButton("➕ Видео/Фото жіберу"))
    kb.row(KeyboardButton("💸 Мой бонус"), KeyboardButton("🔗 Реферал сілтеме"))
    kb.row(KeyboardButton("🛒 Магазин"), KeyboardButton("ℹ️ Ақпарат"))
    if lottery_active:
        kb.row(KeyboardButton("🎯 Лотереяға қатысу"))
    if admin:
        kb.row(KeyboardButton("💰 Бонус беру"), KeyboardButton("✅ Pending файлдар"),
               KeyboardButton("📊 Статистика"), KeyboardButton("📢 Рассылка"), KeyboardButton("🎯 Лотерея бастау"))
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

def remove_old_pending():
    with db_lock:
        old = datetime.utcnow() - timedelta(hours=5)
        old_str = old.isoformat()
        cursor.execute("DELETE FROM pending WHERE created_at<?", (old_str,))
        conn.commit()

def get_top10_lottery():
    with db_lock:
        rows = cursor.execute("SELECT name, invites FROM lottery WHERE participating=1 ORDER BY invites DESC, joined_at ASC LIMIT 10").fetchall()
    text = "🏆 Лотерея Топ 10:\n"
    if not rows:
        text += "Әзірге қатысушылар жоқ."
    else:
        for idx, (name, invites) in enumerate(rows, start=1):
            text += f"{idx}. {name} - {invites} шақыру\n"
    return text

# ---------------------------
# Background Top10 updater
# ---------------------------
def update_top10_lottery():
    while True:
        try:
            with db_lock:
                rows = cursor.execute("""
                    SELECT user_id, invites 
                    FROM lottery 
                    WHERE participating=1 
                    ORDER BY invites DESC, joined_at ASC
                    LIMIT 10
                """).fetchall()
                for user_id, invites in rows:
                    try:
                        bot.send_message(user_id, f"🏆 Сіз топ 10-ға кірдіңіз! Қазіргі шақырғандар саны: {invites}")
                    except:
                        pass
        except Exception as e:
            logger.exception(f"update_top10_lottery error: {e}")
        time.sleep(3600)

threading.Thread(target=update_top10_lottery, daemon=True).start()

# ---------------------------
# Start + 18+
# ---------------------------
@bot.message_handler(commands=['start'])
def cmd_start(msg):
    user_id = msg.from_user.id
    args = msg.text.split()
    ref = int(args[1]) if len(args) >1 and args[1].isdigit() else None
    ensure_user(user_id, invited_by=ref)
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("Ия", callback_data="adult_yes"))
    kb.add(InlineKeyboardButton("Жоқ", callback_data="adult_no"))
    bot.send_message(user_id, "🔞 Сіз 18 жасқа толдыңыз ба?", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("adult_"))
def handle_adult_cb(call):
    user_id = call.from_user.id
    if call.data=="adult_yes":
        cursor.execute("UPDATE users SET is_adult=1 WHERE user_id=?", (user_id,))
        conn.commit()
        bot.send_message(user_id, "✅ Сіз 18+ ересектер ботқа қол жеткіздіңіз.", reply_markup=get_main_keyboard(admin=(user_id==ADMIN_ID)))
    else:
        cursor.execute("UPDATE users SET is_adult=0 WHERE user_id=?", (user_id,))
        conn.commit()
        bot.send_message(user_id, "❌ Бұл бот тек 18+ адамдарға арналған.")

# ---------------------------
# Text handler (Video, Bonus, Referral, Admin)
# ---------------------------
@bot.message_handler(func=lambda m: True)
def handle_text(msg):
    remove_old_pending()
    user_id = msg.from_user.id
    text = msg.text
    ensure_user(user_id)

    u = cursor.execute("SELECT is_adult, balance, progress_video FROM users WHERE user_id=?", (user_id,)).fetchone()
    if not u or u[0]!=1:
        bot.send_message(user_id, "❌ Бұл бот тек 18+ пайдаланушыларға арналған.")
        return
    is_adult,balance,progress = u

    # --- Видео көру ---
    if text=="🎥 Видео көру":
        if not check_subscription(user_id):
            bot.send_message(user_id, f"📢 Видео көру үшін {CHANNEL_USERNAME} каналына тіркеліңіз!")
            return
        with db_lock:
            rows = cursor.execute("SELECT id, file_id, file_path FROM videos ORDER BY id ASC").fetchall()
            if not rows:
                bot.send_message(user_id, "🎬 Видеолар жоқ.")
                return
            if user_id!=ADMIN_ID and balance<2:
                bot.send_message(user_id, "💸 Видео көру үшін 2 бонус қажет.")
                return
            idx = progress if progress<len(rows) else 0
            file_id, file_path = rows[idx][1], rows[idx][2]
            try:
                if file_path and os.path.exists(file_path):
                    with open(file_path,"rb") as f:
                        bot.send_video(user_id,f)
                else:
                    bot.send_video(user_id,file_id)
            except:
                bot.send_message(user_id,"Видео жібергенде қате.")
                return
            cursor.execute("UPDATE users SET balance=?, progress_video=? WHERE user_id=?",
                           (max(balance-2,0), idx+1, user_id))
            conn.commit()
        return

    # --- Бонус ---
    if text=="💸 Мой бонус":
        bal = cursor.execute("SELECT balance FROM users WHERE user_id=?", (user_id,)).fetchone()[0]
        bot.send_message(user_id,f"Сізде қазір: {bal}💸")
        return

    # --- Реферал ---
    if text=="🔗 Реферал сілтеме":
        bot.send_message(user_id,f"Сіздің реферал сілтеме: https://t.me/Sallemkz_bot?start={user_id}")
        return

    # --- Лотерея ---
    if text=="🎯 Лотереяға қатысу":
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("Ия", callback_data="lottery_yes"))
        kb.add(InlineKeyboardButton("Жоқ", callback_data="lottery_no"))
        bot.send_message(user_id,get_top10_lottery(),reply_markup=kb)
        return

    # --- Магазин ---
    if text=="🛒 Магазин":
        bot.send_message(user_id,"Бонус сатып алғыңыз келсе: @KazHUBKZ жазыңыз.")
        return

    # --- Ақпарат ---
    if text=="ℹ️ Ақпарат":
        bot.send_message(user_id,"Бот қалай жұмыс істейді:\n- Видео көру үшін бонус қажет\n- Видео/Фото жіберу админ арқылы\n- Реферал арқылы бонус\n- 18+ адамдарға арналған")
        return

    # --- Admin панель ---
    if user_id==ADMIN_ID:
        if text=="✅ Pending файлдар":
            with db_lock:
                rows = cursor.execute("SELECT id, uploader_id, content_type, file_id FROM pending").fetchall()
            if not rows:
                bot.send_message(user_id,"Pending файлдар жоқ.")
            else:
                for row in rows:
                    pid, uid, ctype, fid = row
                    kb = InlineKeyboardMarkup()
                    kb.add(InlineKeyboardButton("Approve", callback_data=f"approve_{pid}"))
                    kb.add(InlineKeyboardButton("Reject", callback_data=f"reject_{pid}"))
                    bot.send_message(user_id,f"ID:{pid} | {ctype} | Uploader:{uid}", reply_markup=kb)
            return
        if text=="💰 Бонус беру":
            bot.send_message(user_id,"Қолданушы ID + бонус санын жіберіңіз (мысалы: 123456 5)")
            bot.register_next_step_handler(msg, admin_give_bonus)
            return
        if text=="📊 Статистика":
            with db_lock:
                total_users = cursor.execute("SELECT COUNT(*) FROM users").fetchone()[0]
                bot.send_message(user_id,f"📊 Жалпы қолданушылар: {total_users}")
            return
        if text=="📢 Рассылка":
            bot.send_message(user_id,"Хабарламаңызды жіберіңіз, барлық қолданушыларға таратылады.")
            bot.register_next_step_handler(msg, admin_broadcast)
            return
        if text=="🎯 Лотерея бастау":
            bot.send_message(user_id,"Лотерея басталды!")
            with db_lock:
                cursor.execute("UPDATE lottery SET participating=1")
                conn.commit()
            return

    kb = get_main_keyboard(admin=(user_id==ADMIN_ID))
    bot.send_message(user_id,"Түсінбедім 😅",reply_markup=kb)

# ---------------------------
# Admin functions
# ---------------------------
def admin_give_bonus(msg):
    try:
        parts = msg.text.split()
        uid = int(parts[0])
        amount = int(parts[1])
        with db_lock:
            cursor.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (amount, uid))
            conn.commit()
        bot.send_message(ADMIN_ID,f"✅ {uid} қолданушыға {amount} бонус берілді.")
        bot.send_message(uid,f"🎉 Сізге {amount} бонус берілді!")
    except:
        bot.send_message(ADMIN_ID,"Қате. Қолданушы ID және бонус санын дұрыс жіберіңіз.")

def admin_broadcast(msg):
    text = msg.text
    with db_lock:
        users = cursor.execute("SELECT user_id FROM users").fetchall()
    for (uid,) in users:
        try:
            bot.send_message(uid,text)
        except:
            continue
    bot.send_message(ADMIN_ID,"Рассылка аяқталды.")

# ---------------------------
# Pending callbacks
# ---------------------------
@bot.callback_query_handler(func=lambda c: c.data.startswith(("approve_","reject_")))
def handle_pending_cb(call):
    action,pid = call.data.split("_")
    pid = int(pid)
    with db_lock:
        row = cursor.execute("SELECT uploader_id, content_type, file_id, file_path FROM pending WHERE id=?", (pid,)).fetchone()
        if not row:
            bot.answer_callback_query(call.id,"Файл жоқ")
            return
        uid, ctype, fid, fpath = row
        if action=="approve":
            if ctype=="video":
                cursor.execute("INSERT INTO videos(file_id, file_path, added_by, created_at) VALUES (?,?,?,?)",(fid,fpath,uid,datetime.utcnow().isoformat()))
            else:
                cursor.execute("INSERT INTO photos(file_id, file_path, added_by, created_at) VALUES (?,?,?,?)",(fid,fpath,uid,datetime.utcnow().isoformat()))
            bot.send_message(uid,f"✅ Сіздің {ctype} файлыңыз мақұлданды.")
        else:
            bot.send_message(uid,f"❌ Сіздің {ctype} файлыңыз мақұлданбады.")
        cursor.execute("DELETE FROM pending WHERE id=?", (pid,))
        conn.commit()
        bot.answer_callback_query(call.id,"OK")

# ---------------------------
# Лотерея Callback
# ---------------------------
@bot.callback_query_handler(func=lambda c: c.data.startswith("lottery_"))
def handle_lottery_cb(call):
    user_id = call.from_user.id
    action = call.data.split("_")[1]
    user_name = call.from_user.first_name
    if call.from_user.last_name:
        user_name += " "+call.from_user.last_name
    with db_lock:
        if action=="yes":
            cursor.execute("""
                INSERT INTO lottery (user_id, name, participating, joined_at)
                VALUES (?, ?, 1, ?)
                ON CONFLICT(user_id) DO UPDATE SET participating=1
            """,(user_id,user_name,datetime.utcnow().isoformat()))
            conn.commit()
            bot.send_message(user_id,f"🎉 Құтықтаймыз! Сіздің реферал сілтемеңіз: https://t.me/Sallemkz_bot?start={user_id}")
        else:
            cursor.execute("UPDATE lottery SET participating=0 WHERE user_id=?",(user_id,))
            conn.commit()
            bot.send_message(user_id,"Жарайды, лотереяға қатыспайсыз.")
    bot.answer_callback_query(call.id)

# ---------------------------
# Webhook + Flask
# ---------------------------
@app.route("/", methods=['GET'])
def index_route():
    return "Bot running",200

@app.route(f"/{BOT_TOKEN}",methods=['POST'])
def webhook():
    try:
        json_str = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_str)
        bot.process_new_updates([update])
    except:
        logger.exception("Webhook error")
    return "",200

def setup_webhook():
    bot.remove_webhook()
    bot.set_webhook(url=f"{WEBHOOK_URL}/{BOT_TOKEN}")

setup_webhook()

if __name__=="__main__":
    logger.info(f"Running Flask on port {PORT}")
    app.run(host="0.0.0.0", port=PORT)
