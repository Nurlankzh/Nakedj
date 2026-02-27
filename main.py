import os
import logging
import sqlite3
import threading
from datetime import datetime, timedelta
from flask import Flask, request
import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
import random

# ---------------------------
# CONFIG
# ---------------------------
BOT_TOKEN = "7875991285:AAG4pChovJ67bxytVzB2-aIXrRYKUoWRtvw"  # Өз токеніңді қой
ADMIN_ID = 6303091468
CHANNEL_USERNAME = "@kazakcombots"
WEBHOOK_URL = "https://web-production-0cd8e.up.railway.app"
MEDIA_DIR = "media"
DB_FILE = "data.db"
PORT = 10000
SHOP_USERNAME = "@KazHUBKZ"

# ---------------------------
# Logging
# ---------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)
logger.info("Starting bot module...")

# ---------------------------
# Ensure folders
# ---------------------------
os.makedirs(MEDIA_DIR, exist_ok=True)

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
    )""")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS pending (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        uploader_id INTEGER,
        content_type TEXT,
        file_id TEXT,
        file_path TEXT,
        created_at TEXT
    )""")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS videos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        file_id TEXT,
        file_path TEXT,
        added_by INTEGER,
        created_at TEXT
    )""")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS photos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        file_id TEXT,
        file_path TEXT,
        added_by INTEGER,
        created_at TEXT
    )""")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS lottery (
        user_id INTEGER PRIMARY KEY,
        joined_at TEXT
    )""")
    conn.commit()

# ---------------------------
# HELPERS
# ---------------------------
def ensure_user(user_id, invited_by=None):
    with db_lock:
        exists = cursor.execute("SELECT 1 FROM users WHERE user_id=?", (user_id,)).fetchone()
        if not exists:
            cursor.execute("INSERT INTO users (user_id,balance,invited_by) VALUES (?,?,?)", (user_id,3,invited_by))
            conn.commit()
            if invited_by and invited_by != user_id:
                cursor.execute("UPDATE users SET balance = balance + 6 WHERE user_id=?", (invited_by,))
                conn.commit()
                try: bot.send_message(invited_by, "🎉 Сіз жаңа қолданушы шақырдыңыз! +6💸 берілді.")
                except: pass

def get_main_keyboard(admin=False, lottery_active=False):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(KeyboardButton("🎥 Видео көру"), KeyboardButton("➕ Видео/Фото жіберу"))
    kb.row(KeyboardButton("💸 Мой бонус"), KeyboardButton("🔗 Реферал сілтеме"))
    kb.row(KeyboardButton("🛒 Магазин"), KeyboardButton("ℹ️ Ақпарат"))
    if lottery_active: kb.row(KeyboardButton("🎯 Лотереяға қатысу"))
    if admin:
        kb.row(
            KeyboardButton("💰 Бонус беру"),
            KeyboardButton("✅ Pending файлдар"),
            KeyboardButton("📊 Статистика"),
            KeyboardButton("📢 Рассылка"),
            KeyboardButton("🎯 Лотерея бастау"),
            KeyboardButton("🏆 Топ 10 шақырғандар"),
            KeyboardButton("🎖 Лотерея жеңімпазын таңдау")
        )
    return kb

def save_file(file_id, is_video=True):
    file_info = bot.get_file(file_id)
    b = bot.download_file(file_info.file_path)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
    ext = ".mp4" if is_video else ".jpg"
    fname = f"{ts}_{file_id.replace('/','_')}{ext}"
    path = os.path.join(MEDIA_DIR, fname)
    with open(path,"wb") as f: f.write(b)
    return path

def check_subscription(user_id):
    try:
        member = bot.get_chat_member(CHANNEL_USERNAME, user_id)
        return member.status in ["member","administrator","creator"]
    except: return False

def remove_old_pending():
    with db_lock:
        old = datetime.utcnow() - timedelta(hours=5)
        cursor.execute("DELETE FROM pending WHERE created_at<?", (old.isoformat(),))
        conn.commit()

def lottery_status():
    with db_lock:
        return cursor.execute("SELECT COUNT(*) FROM lottery").fetchone()[0] > 0

# ---------------------------
# START COMMAND
# ---------------------------
@bot.message_handler(commands=['start'])
def cmd_start(msg):
    user_id = msg.from_user.id
    args = msg.text.split()
    ref = int(args[1]) if len(args)>1 and args[1].isdigit() else None
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
        bot.send_message(user_id, "✅ Сіз 18+ ересектер ботқа қол жеткіздіңіз.",
                         reply_markup=get_main_keyboard(admin=(user_id==ADMIN_ID), lottery_active=lottery_status()))
    else:
        cursor.execute("UPDATE users SET is_adult=0 WHERE user_id=?", (user_id,))
        conn.commit()
        bot.send_message(user_id, "❌ Бұл бот тек 18+ адамдарға арналған.")

# ---------------------------
# TEXT HANDLER
# ---------------------------
@bot.message_handler(func=lambda m: True)
def handle_text(msg):
    remove_old_pending()
    user_id = msg.from_user.id
    text = msg.text
    u = cursor.execute("SELECT is_adult FROM users WHERE user_id=?", (user_id,)).fetchone()
    if not u or u[0]!=1: 
        bot.send_message(user_id, "❌ Бұл бот тек 18+ пайдаланушыларға арналған.")
        return
    ensure_user(user_id)

    # -------- Видео көру --------
    if text=="🎥 Видео көру":
        if not check_subscription(user_id):
            bot.send_message(user_id,f"📢 Видео көру үшін {CHANNEL_USERNAME} каналына тіркеліңіз!")
            return
        with db_lock:
            balance,progress = cursor.execute("SELECT balance, progress_video FROM users WHERE user_id=?",(user_id,)).fetchone()
            rows = cursor.execute("SELECT file_id, file_path FROM videos ORDER BY id ASC").fetchall()
            if not rows: bot.send_message(user_id,"🎬 Видеолар жоқ."); return
            if user_id!=ADMIN_ID and balance<2: bot.send_message(user_id,"💸 Видео көру үшін 2 бонус қажет."); return
            idx = progress if progress<len(rows) else 0
            file_id,file_path = rows[idx]
            try:
                if file_path and os.path.exists(file_path):
                    with open(file_path,"rb") as f: bot.send_video(user_id,f)
                else: bot.send_video(user_id,file_id)
            except: bot.send_message(user_id,"Видео жібергенде қате."); return
            cursor.execute("UPDATE users SET balance=?, progress_video=? WHERE user_id=?",(max(balance-2,0), idx+1, user_id))
            conn.commit()
        return

    # -------- Видео/Фото жіберу --------
    elif text=="➕ Видео/Фото жіберу":
        bot.send_message(user_id,"Файл жіберіңіз. Админ мақұлдайды."); return

    # -------- Бонус --------
    elif text=="💸 Мой бонус":
        bal = cursor.execute("SELECT balance FROM users WHERE user_id=?",(user_id,)).fetchone()[0]
        bot.send_message(user_id,f"Сізде қазір: {bal}💸"); return

    # -------- Реферал --------
    elif text=="🔗 Реферал сілтеме":
        bot.send_message(user_id,f"Сіздің реферал сілтеме: https://t.me/KazHub_slivbot?start={user_id}"); return

    # -------- Магазин --------
    elif text=="🛒 Магазин":
        bot.send_message(user_id,f"Бонус сатып алғыңыз келсе: {SHOP_USERNAME} жазыңыз."); return

    # -------- Ақпарат --------
    elif text=="ℹ️ Ақпарат":
        bot.send_message(user_id,"Бот қалай жұмыс істейді:\n- Видео көру үшін бонус қажет\n- Видео/Фото жіберу админ арқылы\n- Реферал арқылы бонус\n- 18+ адамдарға арналған"); return

    # -------- Лотереяға қатысу --------
    elif text=="🎯 Лотереяға қатысу":
        with db_lock:
            if not lottery_status(): bot.send_message(user_id,"Лотерея әлі басталмаған."); return
            exists = cursor.execute("SELECT 1 FROM lottery WHERE user_id=?",(user_id,)).fetchone()
            if exists: bot.send_message(user_id,"Сіз бұрын қосылғансыз!"); return
            cursor.execute("INSERT INTO lottery (user_id, joined_at) VALUES (?,?)",(user_id, datetime.utcnow().isoformat()))
            conn.commit()
        bot.send_message(user_id,"🎉 Сіз Лотереяға қосылдыңыз!"); return

    # -------- Admin-only --------
    if user_id!=ADMIN_ID: return

    # -------- Бонус беру --------
    if " " in text:
        try:
            parts = text.split()
            target_id = int(parts[0])
            amount = int(parts[1])
            cursor.execute("UPDATE users SET balance=balance+? WHERE user_id=?",(amount,target_id))
            conn.commit()
            bot.send_message(user_id,f"{amount}💸 {target_id}-қа берілді.")
            bot.send_message(target_id,f"🎉 Сізге {amount}💸 берілді!")
        except: pass
        return

    # -------- Pending файлдар --------
    elif text=="✅ Pending файлдар":
        pendings = cursor.execute("SELECT id,uploader_id,content_type,file_id,file_path FROM pending ORDER BY id ASC").fetchall()
        if not pendings: bot.send_message(user_id,"Pending файлдар жоқ."); return
        for pid,uploader,ctype,file_id,file_path in pendings:
            kb = InlineKeyboardMarkup()
            kb.add(InlineKeyboardButton("Мақұлдау", callback_data=f"approve_{pid}"))
            kb.add(InlineKeyboardButton("Растамау", callback_data=f"reject_{pid}"))
            try:
                if ctype=="video":
                    if file_path and os.path.exists(file_path):
                        with open(file_path,"rb") as f: bot.send_video(user_id,f,caption=f"#{pid} {ctype} from {uploader}", reply_markup=kb)
                    else: bot.send_video(user_id,file_id,caption=f"#{pid} {ctype} from {uploader}", reply_markup=kb)
                else:
                    if file_path and os.path.exists(file_path):
                        with open(file_path,"rb") as f: bot.send_photo(user_id,f,caption=f"#{pid} {ctype} from {uploader}", reply_markup=kb)
                    else: bot.send_photo(user_id,file_id,caption=f"#{pid} {ctype} from {uploader}", reply_markup=kb)
            except: pass
        return

    # -------- Статистика --------
    elif text=="📊 Статистика":
        users_count = cursor.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        videos_count = cursor.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
        pending_count = cursor.execute("SELECT COUNT(*) FROM pending").fetchone()[0]
        bot.send_message(user_id,f"📊 Статистика:\nҚолданушылар: {users_count}\nВидео: {videos_count}\nPending: {pending_count}")
        return

    # -------- Рассылка --------
    elif text=="📢 Рассылка":
        bot.send_message(user_id,"Жіберілетін хабарламаны жіберіңіз:")
        bot.register_next_step_handler(msg, handle_broadcast)
        return

    # -------- Лотерея бастау --------
    elif text=="🎯 Лотерея бастау":
        with db_lock:
            cursor.execute("DELETE FROM lottery")
            conn.commit()
        bot.send_message(user_id,"🎯 Лотерея басталды! Қолданушылар 24 сағат ішінде қатыса алады.")
        return

    # -------- Лотерея жеңімпазын таңдау --------
    elif text=="🎖 Лотерея жеңімпазын таңдау":
        with db_lock:
            participants = cursor.execute("SELECT user_id FROM lottery").fetchall()
            if not participants:
                bot.send_message(user_id,"❌ Лотереяға қатысушылар жоқ.")
                return
            winner = random.choice(participants)[0]
            cursor.execute("DELETE FROM lottery")
            conn.commit()
        bot.send_message(user_id,f"🎉 Жеңімпаз: {winner}!")
        bot.send_message(winner,"🎊 Сіз лотереядан жеңдіңіз!")
        return

    # -------- Топ 10 шақырғандар --------
    elif text=="🏆 Топ 10 шақырғандар":
        top10 = cursor.execute("SELECT invited_by, COUNT(*) as cnt FROM users WHERE invited_by IS NOT NULL GROUP BY invited_by ORDER BY cnt DESC LIMIT 10").fetchall()
        msg_text = "🏆 Топ 10 шақырғандар:\n"
        for u,cnt in top10: msg_text += f"{u}: {cnt} шақырды\n"
        bot.send_message(user_id,msg_text)
        return

# ---------------------------
# MEDIA HANDLER
# ---------------------------
@bot.message_handler(content_types=['video','photo','document'])
def handle_media(msg):
    remove_old_pending()
    user_id = msg.from_user.id
    is_video = msg.content_type in ['video','document']
    try:
        file_id = msg.video.file_id if msg.content_type=='video' else msg.photo[-1].file_id if msg.content_type=='photo' else msg.document.file_id
        path = save_file(file_id,is_video)
    except: bot.send_message(user_id,"Файл сақталмады!"); return

    if user_id==ADMIN_ID:
        table = "videos" if is_video else "photos"
        with db_lock:
            cursor.execute(f"INSERT INTO {table} (file_id,file_path,added_by,created_at) VALUES (?,?,?,?)",(file_id,path,user_id,datetime.utcnow().isoformat()))
            conn.commit()
        bot.send_message(user_id,"✅ Файл сақталды (Admin)."); return

    with db_lock:
        cursor.execute("INSERT INTO pending (uploader_id,content_type,file_id,file_path,created_at) VALUES (?,?,?,?,?)",(user_id,'video' if is_video else 'photo',file_id,path,datetime.utcnow().isoformat()))
        conn.commit()
    bot.send_message(user_id,"✅ Файл модерацияға жіберілді.")

# ---------------------------
# CALLBACK HANDLER
# ---------------------------
@bot.callback_query_handler(func=lambda c: True)
def handle_cb(call):
    data = call.data; user_id = call.from_user.id
    if data.startswith("adult_"): handle_adult_cb(call); return
    if user_id!=ADMIN_ID: return
    if data.startswith("approve_") or data.startswith("reject_"):
        action,pid = data.split("_"); pid=int(pid)
        p = cursor.execute("SELECT uploader_id, content_type, file_id, file_path FROM pending WHERE id=?",(pid,)).fetchone()
        if not p: return
        uploader_id,ctype,file_id,file_path = p
        table = "videos" if ctype=="video" else "photos"
        if action=="approve":
            cursor.execute(f"INSERT INTO {table} (file_id,file_path,added_by,created_at) VALUES (?,?,?,?)",(file_id,file_path,user_id,datetime.utcnow().isoformat()))
            cursor.execute("UPDATE users SET balance=balance+12 WHERE user_id=?",(uploader_id,))
            bot.send_message(uploader_id,f"🎉 Сіздің {ctype} мақұлданды! +12💸")
        else:
            bot.send_message(uploader_id,f"❌ Сіздің файл мақұлданбады.")
        cursor.execute("DELETE FROM pending WHERE id=?",(pid,))
        conn.commit()
        bot.answer_callback_query(call.id,"Дайын")

# ---------------------------
# BROADCAST
# ---------------------------
def handle_broadcast(msg):
    text = msg.text
    users = cursor.execute("SELECT user_id FROM users WHERE is_adult=1").fetchall()
    count = 0
    for u in users:
        try: bot.send_message(u[0], text); count+=1
        except: pass
    bot.send_message(ADMIN_ID,f"Рассылка аяқталды. Жіберілді: {count} қолданушыға.")

# ---------------------------
# WEBHOOK + FLASK (жалғасы)
# ---------------------------
@app.route(f"/{BOT_TOKEN}", methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return ''
    else:
        return '', 403

def setup_webhook():
    try:
        bot.remove_webhook()
        bot.set_webhook(url=f"{WEBHOOK_URL}/{BOT_TOKEN}")
        logger.info("Webhook updated successfully")
    except Exception as e:
        logger.error(f"Webhook error: {e}")

# ---------------------------
# Bot іске қосу
# ---------------------------
setup_webhook()

if __name__=="__main__":
    logger.info(f"Starting Flask server on port {PORT}...")
    app.run(host="0.0.0.0", port=PORT)
