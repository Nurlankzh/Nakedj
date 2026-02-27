import os
import logging
import sqlite3
import threading
import random
import time
from datetime import datetime, timedelta
from flask import Flask, request
import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

# ---------------------------
# CONFIGURATION
# ---------------------------
BOT_TOKEN = "7875991285:AAG4pChovJ67bxytVzB2-aIXrRYKUoWRtvw"
ADMIN_ID = 6303091468
CHANNEL_USERNAME = "@kazakcombots"
WEBHOOK_URL = "https://web-production-0cd8e.up.railway.app"
MEDIA_DIR = "media"
DB_FILE = "data.db"
PORT = 10000
SHOP_USERNAME = "@KazHUBKZ"

# Logging setup
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

if not os.path.exists(MEDIA_DIR):
    os.makedirs(MEDIA_DIR)

# ---------------------------
# INITIALIZATION
# ---------------------------
bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)
db_lock = threading.Lock()

def get_db_connection():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    return conn

# Database Tables Setup
def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    with db_lock:
        cursor.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            balance INTEGER DEFAULT 3,
            progress_video INTEGER DEFAULT 0,
            invited_by INTEGER,
            is_adult INTEGER DEFAULT 0,
            joined_at TEXT
        )""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS pending (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uploader_id INTEGER,
            content_type TEXT,
            file_id TEXT,
            file_path TEXT,
            created_at TEXT
        )""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id TEXT,
            file_path TEXT,
            added_by INTEGER,
            created_at TEXT
        )""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS photos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id TEXT,
            file_path TEXT,
            added_by INTEGER,
            created_at TEXT
        )""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS lottery (
            user_id INTEGER PRIMARY KEY,
            joined_at TEXT
        )""")
        conn.commit()
    conn.close()

init_db()

# ---------------------------
# KEYBOARDS
# ---------------------------
def get_main_keyboard(user_id):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(KeyboardButton("🎥 Видео көру"), KeyboardButton("➕ Видео/Фото жіберу"))
    kb.row(KeyboardButton("💸 Мой бонус"), KeyboardButton("🔗 Реферал сілтеме"))
    kb.row(KeyboardButton("🛒 Магазин"), KeyboardButton("ℹ️ Ақпарат"))
    
    # Лотерея белсенді болса көрсету
    if lottery_status():
        kb.row(KeyboardButton("🎯 Лотереяға қатысу"))
        
    if user_id == ADMIN_ID:
        kb.row(KeyboardButton("✅ Pending файлдар"), KeyboardButton("📊 Статистика"))
        kb.row(KeyboardButton("🎯 Лотерея бастау"), KeyboardButton("🎖 Лотерея жеңімпазын таңдау"))
        kb.row(KeyboardButton("🏆 Топ 10 шақырғандар"), KeyboardButton("📢 Рассылка"))
        kb.row(KeyboardButton("💰 Бонус беру"))
    return kb

# ---------------------------
# HELPER FUNCTIONS
# ---------------------------
def ensure_user(user_id, invited_by=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    with db_lock:
        user = cursor.execute("SELECT 1 FROM users WHERE user_id=?", (user_id,)).fetchone()
        if not user:
            now = datetime.utcnow().isoformat()
            cursor.execute("INSERT INTO users (user_id, balance, invited_by, joined_at) VALUES (?, ?, ?, ?)", 
                           (user_id, 3, invited_by, now))
            conn.commit()
            if invited_by and invited_by != user_id:
                cursor.execute("UPDATE users SET balance = balance + 6 WHERE user_id=?", (invited_by,))
                conn.commit()
                try:
                    bot.send_message(invited_by, "🎊 Сіздің сілтемеңізбен жаңа қолданушы тіркелді! Сізге +6💸 бонус берілді.")
                except: pass
    conn.close()

def check_subscription(user_id):
    if user_id == ADMIN_ID: return True
    try:
        member = bot.get_chat_member(CHANNEL_USERNAME, user_id)
        return member.status in ['member', 'administrator', 'creator']
    except: return False

def lottery_status():
    conn = get_db_connection()
    count = conn.execute("SELECT COUNT(*) FROM lottery").fetchone()[0]
    conn.close()
    return count >= 0 # Логика бойынша кесте бар болса

def save_media_file(file_id, is_video=True):
    file_info = bot.get_file(file_id)
    downloaded_file = bot.download_file(file_info.file_path)
    ext = ".mp4" if is_video else ".jpg"
    filename = f"{int(time.time())}_{file_id[:10]}{ext}"
    path = os.path.join(MEDIA_DIR, filename)
    with open(path, 'wb') as new_file:
        new_file.write(downloaded_file)
    return path

# ---------------------------
# COMMAND HANDLERS
# ---------------------------
@bot.message_handler(commands=['start'])
def start_cmd(message):
    user_id = message.from_user.id
    text_parts = message.text.split()
    ref_id = None
    if len(text_parts) > 1 and text_parts[1].isdigit():
        ref_id = int(text_parts[1])
    
    ensure_user(user_id, ref_id)
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("✅ Ия, 18-ден астым", callback_data="confirm_adult"),
               InlineKeyboardButton("❌ Жоқ", callback_data="decline_adult"))
    
    bot.send_message(user_id, "✋ Сәлем! Ботты қолдану үшін жасыңыз 18-ден асқан болуы керек. Растайсыз ба?", reply_markup=markup)

# ---------------------------
# CALLBACK HANDLERS
# ---------------------------
@bot.callback_query_handler(func=lambda call: True)
def callback_manager(call):
    user_id = call.from_user.id
    conn = get_db_connection()
    cursor = conn.cursor()

    if call.data == "confirm_adult":
        with db_lock:
            cursor.execute("UPDATE users SET is_adult=1 WHERE user_id=?", (user_id,))
            conn.commit()
        bot.edit_message_text("✅ Рақмет! Енді боттың барлық мүмкіндігі ашық.", chat_id=user_id, message_id=call.message.message_id)
        bot.send_message(user_id, "Төмендегі батырмаларды қолданыңыз:", reply_markup=get_main_keyboard(user_id))

    elif call.data == "decline_adult":
        bot.answer_callback_query(call.id, "Кешіріңіз, бұл бот тек ересектерге арналған.", show_alert=True)

    elif call.data.startswith("appr_"):
        pid = call.data.split("_")[1]
        with db_lock:
            p = cursor.execute("SELECT uploader_id, content_type, file_id, file_path FROM pending WHERE id=?", (pid,)).fetchone()
            if p:
                uid, ctype, fid, fpath = p
                table = "videos" if ctype == "video" else "photos"
                cursor.execute(f"INSERT INTO {table} (file_id, file_path, added_by, created_at) VALUES (?,?,?,?)", 
                               (fid, fpath, uid, datetime.utcnow().isoformat()))
                cursor.execute("UPDATE users SET balance = balance + 12 WHERE user_id=?", (uid,))
                cursor.execute("DELETE FROM pending WHERE id=?", (pid,))
                conn.commit()
                try: bot.send_message(uid, "✅ Құттықтаймыз! Сіз жіберген файл мақұлданды. +12💸 берілді.")
                except: pass
        bot.edit_message_caption("✅ Мақұлданды", chat_id=ADMIN_ID, message_id=call.message.message_id)

    elif call.data.startswith("rejc_"):
        pid = call.data.split("_")[1]
        with db_lock:
            cursor.execute("DELETE FROM pending WHERE id=?", (pid,))
            conn.commit()
        bot.edit_message_caption("❌ Бас тартылды", chat_id=ADMIN_ID, message_id=call.message.message_id)
    
    conn.close()

# ---------------------------
# MEDIA HANDLER
# ---------------------------
@bot.message_handler(content_types=['photo', 'video'])
def media_handler(message):
    user_id = message.from_user.id
    is_video = message.content_type == 'video'
    file_id = message.video.file_id if is_video else message.photo[-1].file_id
    
    path = save_media_file(file_id, is_video)
    conn = get_db_connection()
    with db_lock:
        conn.execute("INSERT INTO pending (uploader_id, content_type, file_id, file_path, created_at) VALUES (?,?,?,?,?)",
                     (user_id, 'video' if is_video else 'photo', file_id, path, datetime.utcnow().isoformat()))
        conn.commit()
    conn.close()
    bot.send_message(user_id, "📩 Рақмет! Файл модерацияға жіберілді. Админ тексерген соң бонус аласыз.")

# ---------------------------
# MAIN TEXT HANDLER (ADMIN + USER)
# ---------------------------
@bot.message_handler(func=lambda m: True)
def text_handler(message):
    user_id = message.from_user.id
    text = message.text
    conn = get_db_connection()
    cursor = conn.cursor()

    # Тексеру
    user_data = cursor.execute("SELECT is_adult, balance, progress_video FROM users WHERE user_id=?", (user_id,)).fetchone()
    if not user_data:
        ensure_user(user_id)
        return
    
    if user_data[0] == 0:
        bot.send_message(user_id, "⚠️ Алдымен /start басып, жасыңызды растаңыз.")
        return

    # --- ПАЙДАЛАНУШЫ ФУНКЦИЯЛАРЫ ---
    if text == "🎥 Видео көру":
        if not check_subscription(user_id):
            bot.send_message(user_id, f"⚠️ Видео көру үшін алдымен каналымызға тіркеліңіз: {CHANNEL_USERNAME}")
            return
        
        balance, progress = user_data[1], user_data[2]
        if balance < 2 and user_id != ADMIN_ID:
            bot.send_message(user_id, "❌ Кешіріңіз, видео көру үшін кемі 2💸 бонус керек.")
            return

        videos = cursor.execute("SELECT file_id, file_path FROM videos ORDER BY id ASC").fetchall()
        if not videos:
            bot.send_message(user_id, "😔 Әзірге видеолар жоқ. Кейінірек тексеріңіз.")
            return

        idx = progress if progress < len(videos) else 0
        vid_id, vid_path = videos[idx]
        
        try:
            bot.send_video(user_id, vid_id)
            with db_lock:
                new_bal = balance if user_id == ADMIN_ID else balance - 2
                cursor.execute("UPDATE users SET balance=?, progress_video=? WHERE user_id=?", (new_bal, idx+1, user_id))
                conn.commit()
        except:
            bot.send_message(user_id, "❌ Видео жіберуде қате шықты.")

    elif text == "💸 Мой бонус":
        bot.send_message(user_id, f"💰 Сіздің балансыңыз: {user_data[1]}💸")

    elif text == "🔗 Реферал сілтеме":
        ref_link = f"https://t.me/{(bot.get_me().username)}?start={user_id}"
        bot.send_message(user_id, f"🎁 Достарыңызды шақырып, бонус алыңыз!\n\nӘр дос үшін: +6💸\nСілтемеңіз: {ref_link}")

    elif text == "🛒 Магазин":
        bot.send_message(user_id, f"🛍 Бонустар сатып алу үшін админге жазыңыз: {SHOP_USERNAME}")

    elif text == "ℹ️ Ақпарат":
        info_text = (
            "📖 **Бот ережесі:**\n\n"
            "- 1 видео көру = 2💸 бонус\n"
            "- Дос шақыру = 6💸 бонус\n"
            "- Видео жіберу = 12💸 бонус (мақұлданса)\n"
            "- Барлық видеолар 18+ форматында."
        )
        bot.send_message(user_id, info_text, parse_mode="Markdown")

    elif text == "🎯 Лотереяға қатысу":
        with db_lock:
            exists = cursor.execute("SELECT 1 FROM lottery WHERE user_id=?", (user_id,)).fetchone()
            if exists:
                bot.send_message(user_id, "⚠️ Сіз лотереяға қатысып қойғансыз.")
            else:
                cursor.execute("INSERT INTO lottery (user_id, joined_at) VALUES (?, ?)", (user_id, datetime.utcnow().isoformat()))
                conn.commit()
                bot.send_message(user_id, "✅ Сіз лотерея қатысушыларының тізіміне қосылдыңыз!")

    # --- АДМИН ФУНКЦИЯЛАРЫ ---
    if user_id == ADMIN_ID:
        if text == "✅ Pending файлдар":
            pendings = cursor.execute("SELECT id, uploader_id, content_type, file_id FROM pending LIMIT 10").fetchall()
            if not pendings:
                bot.send_message(ADMIN_ID, "📭 Күтудегі файлдар жоқ.")
                return
            for pid, uid, ctype, fid in pendings:
                markup = InlineKeyboardMarkup()
                markup.add(InlineKeyboardButton("✅ Мақұлдау", callback_data=f"appr_{pid}"),
                           InlineKeyboardButton("❌ Бас тарту", callback_data=f"rejc_{pid}"))
                if ctype == 'video':
                    bot.send_video(ADMIN_ID, fid, caption=f"Жіберуші: {uid}", reply_markup=markup)
                else:
                    bot.send_photo(ADMIN_ID, fid, caption=f"Жіберуші: {uid}", reply_markup=markup)

        elif text == "📊 Статистика":
            total_users = cursor.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            total_vids = cursor.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
            total_pend = cursor.execute("SELECT COUNT(*) FROM pending").fetchone()[0]
            bot.send_message(ADMIN_ID, f"📊 **Бот статистикасы:**\n\n👥 Юзерлер: {total_users}\n🎥 Видеолар: {total_vids}\n⏳ Күтуде: {total_pend}")

        elif text == "🎯 Лотерея бастау":
            with db_lock:
                cursor.execute("DELETE FROM lottery")
                conn.commit()
            bot.send_message(ADMIN_ID, "🎯 Лотерея тазаланды және жаңадан басталды!")

        elif text == "🎖 Лотерея жеңімпазын таңдау":
            users = cursor.execute("SELECT user_id FROM lottery").fetchall()
            if not users:
                bot.send_message(ADMIN_ID, "❌ Қатысушылар жоқ.")
            else:
                winner = random.choice(users)[0]
                bot.send_message(ADMIN_ID, f"🏆 Жеңімпаз ID: {winner}")
                try: bot.send_message(winner, "🎊 Құттықтаймыз! Сіз лотереяда жеңімпаз атандыңыз!")
                except: pass

        elif text == "🏆 Топ 10 шақырғандар":
            top_referrals = cursor.execute("""
                SELECT invited_by, COUNT(*) as count 
                FROM users 
                WHERE invited_by IS NOT NULL 
                GROUP BY invited_by 
                ORDER BY count DESC 
                LIMIT 10
            """).fetchall()
            report = "🏆 **Ең көп адам шақырғандар:**\n\n"
            for i, (uid, count) in enumerate(top_referrals, 1):
                report += f"{i}. ID: `{uid}` — {count} адам\n"
            bot.send_message(ADMIN_ID, report, parse_mode="Markdown")

        elif text == "📢 Рассылка":
            bot.send_message(ADMIN_ID, "📢 Барлық қолданушыларға жіберілетін мәтінді немесе файлды жіберіңіз:")
            bot.register_next_step_handler(message, run_broadcast)

        elif text == "💰 Бонус беру":
            bot.send_message(ADMIN_ID, "Жазыңыз: `ID Мөлшер` (Мысалы: `6303091468 100`)")

        elif " " in text and text.replace(" ", "").isdigit():
            try:
                parts = text.split()
                target_id = int(parts[0])
                amount = int(parts[1])
                with db_lock:
                    cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (amount, target_id))
                    conn.commit()
                bot.send_message(ADMIN_ID, f"✅ ID {target_id} пайдаланушыға {amount}💸 берілді.")
                try: bot.send_message(target_id, f"🎁 Админ сізге {amount}💸 бонус берді!")
                except: pass
            except: pass

    conn.close()

# ---------------------------
# BROADCAST LOGIC
# ---------------------------
def run_broadcast(message):
    conn = get_db_connection()
    users = conn.execute("SELECT user_id FROM users").fetchall()
    conn.close()
    
    success = 0
    for (uid,) in users:
        try:
            if message.content_type == 'text':
                bot.send_message(uid, message.text)
            elif message.content_type == 'photo':
                bot.send_photo(uid, message.photo[-1].file_id, caption=message.caption)
            elif message.content_type == 'video':
                bot.send_video(uid, message.video.file_id, caption=message.caption)
            success += 1
            time.sleep(0.1) # Блокқа түспеу үшін
        except: continue
    
    bot.send_message(ADMIN_ID, f"📢 Рассылка аяқталды. {success} адамға жетті.")

# ---------------------------
# WEBHOOK SERVER
# ---------------------------
@app.route(f"/{BOT_TOKEN}", methods=['POST'])
def get_update():
    json_string = request.get_data().decode('utf-8')
    update = telebot.types.Update.de_json(json_string)
    bot.process_new_updates([update])
    return "!", 200

if __name__ == "__main__":
    bot.remove_webhook()
    bot.set_webhook(url=f"{WEBHOOK_URL}/{BOT_TOKEN}")
    app.run(host="0.0.0.0", port=PORT)
