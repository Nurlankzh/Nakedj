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

# ==========================================
# CONFIGURATION (Баптаулар)
# ==========================================

BOT_TOKEN = "6851505012:AAHA88fc7S7FH7AfbDx1h_layrzV6OjMbxI"
ADMIN_ID = 6303091468
CHANNEL_USERNAME = "@uyatsizoqiga"
WEBHOOK_URL = "https://web-production-0cd8e.up.railway.app"
MEDIA_DIR = "media"
DB_FILE = "data.db"
PORT = int(os.environ.get("PORT", 10000)) 

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

if not os.path.exists(MEDIA_DIR):
    os.makedirs(MEDIA_DIR)

# ==========================================
# INITIALIZATION (Деректер қоры)
# ==========================================

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)
db_lock = threading.Lock()

def get_db_connection():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    with db_lock:
        cursor.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            balance INTEGER DEFAULT 0,
            progress_media INTEGER DEFAULT 0,
            invited_by INTEGER,
            last_bonus_at TEXT,
            joined_at TEXT
        )""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS pending (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uploader_id INTEGER,
            content_type TEXT,
            file_id TEXT,
            created_at TEXT
        )""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS contents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id TEXT,
            content_type TEXT,
            added_by INTEGER
        )""")
        conn.commit()
    conn.close()

init_db()

# ==========================================
# KEYBOARDS (Батырмалар)
# ==========================================

def get_main_keyboard(user_id):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(KeyboardButton("🖼 Файылдарды көру"), KeyboardButton("📸 Фото жіберу"), KeyboardButton("🎥 Видео жіберу"))
    kb.row(KeyboardButton("🎁 Күнделікті бонус"), KeyboardButton("👤 Профиль"), KeyboardButton("🔗 Реферал"))
    
    if user_id == ADMIN_ID:  
        kb.row(KeyboardButton("✅ Күтудегі файлдар"), KeyboardButton("📊 Статистика"))  
        kb.row(KeyboardButton("📢 Рассылка"), KeyboardButton("💰 Бонус беру"))  
    return kb

# ==========================================
# HELPER FUNCTIONS
# ==========================================

def ensure_user(user_id, invited_by=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    with db_lock:
        user = cursor.execute("SELECT 1 FROM users WHERE user_id=?", (user_id,)).fetchone()
        if not user:
            now = datetime.utcnow().isoformat()
            cursor.execute("INSERT INTO users (user_id, balance, invited_by, joined_at, last_bonus_at) VALUES (?, ?, ?, ?, ?)",
                           (user_id, 0, invited_by, now, datetime.min.isoformat()))
            conn.commit()
            if invited_by and invited_by != user_id:
                # ШАҚЫРҒАНҒА 12 БОНУС
                cursor.execute("UPDATE users SET balance = balance + 12 WHERE user_id=?", (invited_by,))
                conn.commit()
                try: bot.send_message(invited_by, "🎊 Сіздің сілтемеңізбен адам тіркелді! Сізге +12 бонус берілді.")
                except: pass
    conn.close()

def check_subscription(user_id):
    if user_id == ADMIN_ID: return True
    try:
        member = bot.get_chat_member(CHANNEL_USERNAME, user_id)
        return member.status in ['member', 'administrator', 'creator']
    except: return True # Канал тексеруде қате болса жібере салу

# ==========================================
# HANDLERS
# ==========================================

@bot.message_handler(commands=['start'])
def start_cmd(message):
    user_id = message.from_user.id
    ref_id = None
    parts = message.text.split()
    if len(parts) > 1 and parts[1].isdigit():
        ref_id = int(parts[1])
    
    ensure_user(user_id, ref_id)
    bot.send_message(user_id, "✋ Сәлем! Төмендегі батырмаларды қолданыңыз:", reply_markup=get_main_keyboard(user_id))

@bot.message_handler(func=lambda m: m.text == "🎁 Күнделікті бонус")
def get_daily_bonus(message):
    user_id = message.from_user.id
    conn = get_db_connection()
    user = conn.execute("SELECT last_bonus_at FROM users WHERE user_id=?", (user_id,)).fetchone()
    
    if user:
        last_bonus = datetime.fromisoformat(user[0])
        if datetime.utcnow() - last_bonus >= timedelta(hours=24):
            with db_lock:
                conn.execute("UPDATE users SET balance = balance + 10, last_bonus_at = ? WHERE user_id=?", 
                             (datetime.utcnow().isoformat(), user_id))
                conn.commit()
            bot.send_message(user_id, "💰 Сізге 10 бонус берілді! Келесі бонусты 24 сағаттан соң береді.")
        else:
            bot.send_message(user_id, "⚠️ Сізге 10 бонус берілді, келесі бонусты 24 сағаттан соң береді.")
    conn.close()

@bot.message_handler(content_types=['photo', 'video'])
def handle_upload(message):
    user_id = message.from_user.id
    ctype = message.content_type
    file_id = message.photo[-1].file_id if ctype == 'photo' else message.video.file_id
    
    conn = get_db_connection()
    with db_lock:
        conn.execute("INSERT INTO pending (uploader_id, content_type, file_id, created_at) VALUES (?,?,?,?)",
                     (user_id, ctype, file_id, datetime.utcnow().isoformat()))
        conn.commit()
    conn.close()
    bot.send_message(user_id, "📩 Файл админге жіберілді. Мақұлданса бонус аласыз.")

@bot.callback_query_handler(func=lambda call: True)
def admin_action(call):
    if call.data.startswith(("app_", "rej_")):
        action, pid = call.data.split("_")
        conn = get_db_connection()
        p = conn.execute("SELECT uploader_id, content_type, file_id FROM pending WHERE id=?", (pid,)).fetchone()
        
        if p:
            uid, ctype, fid = p
            if action == "app":
                bonus = 15 if ctype == 'photo' else 18
                with db_lock:
                    conn.execute("INSERT INTO contents (file_id, content_type, added_by) VALUES (?,?,?)", (fid, ctype, uid))
                    conn.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (bonus, uid))
                    conn.execute("DELETE FROM pending WHERE id=?", (pid,))
                    conn.commit()
                bot.send_message(uid, f"✅ Админ файлыңызды мақұлдады! +{bonus} бонус берілді.")
                bot.edit_message_caption(f"✅ Мақұлданды (+{bonus})", call.message.chat.id, call.message.message_id)
            else:
                with db_lock:
                    conn.execute("DELETE FROM pending WHERE id=?", (pid,))
                    conn.commit()
                bot.send_message(uid, "❌ Кешіріңіз, админ мақұлдамады.")
                bot.edit_message_caption("❌ Бас тартылды", call.message.chat.id, call.message.message_id)
        conn.close()

@bot.message_handler(func=lambda m: True)
def text_handler(message):
    user_id = message.from_user.id
    text = message.text
    ensure_user(user_id)
    
    conn = get_db_connection()
    user = conn.execute("SELECT balance, progress_media FROM users WHERE user_id=?", (user_id,)).fetchone()

    if text == "🖼 Файылдарды көру":
        if not check_subscription(user_id):
            bot.send_message(user_id, f"⚠️ Каналға тіркеліңіз: {CHANNEL_USERNAME}")
        else:
            all_content = conn.execute("SELECT file_id, content_type FROM contents ORDER BY id ASC").fetchall()
            if not all_content:
                bot.send_message(user_id, "📂 Файлдар әлі жоқ.")
            else:
                idx = user[1] if user[1] < len(all_content) else 0
                fid, ctype = all_content[idx]
                try:
                    if ctype == 'photo': bot.send_photo(user_id, fid)
                    else: bot.send_video(user_id, fid)
                    with db_lock:
                        conn.execute("UPDATE users SET progress_media = ? WHERE user_id=?", (idx + 1, user_id))
                        conn.commit()
                except: bot.send_message(user_id, "❌ Қате шықты.")

    elif text == "👤 Профиль":
        bot.send_message(user_id, f"👤 ID: `{user_id}`\n💰 Баланс: {user[0]} бонус", parse_mode="Markdown")

    elif text == "🔗 Реферал":
        bot.send_message(user_id, f"🎁 Дос шақырғаныңыз үшін 12 бонус аласыз!\nСілтеме: https://t.me/Qazaqsha_onimbot?start={user_id}")

    # ADMIN FUNCTIONS
    if user_id == ADMIN_ID:
        if text == "✅ Күтудегі файлдар":
            pends = conn.execute("SELECT id, uploader_id, content_type, file_id FROM pending LIMIT 5").fetchall()
            for pid, uid, ctype, fid in pends:
                markup = InlineKeyboardMarkup().add(
                    InlineKeyboardButton("✅ Мақұлдау", callback_data=f"app_{pid}"),
                    InlineKeyboardButton("❌ Бас тарту", callback_data=f"rej_{pid}")
                )
                if ctype == 'photo': bot.send_photo(ADMIN_ID, fid, caption=f"Юзер: {uid}", reply_markup=markup)
                else: bot.send_video(ADMIN_ID, fid, caption=f"Юзер: {uid}", reply_markup=markup)

        elif text == "📊 Статистика":
            count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            bot.send_message(ADMIN_ID, f"📊 Пайдаланушылар саны: {count}")

    conn.close()

# ==========================================
# WEBHOOK & RUN
# ==========================================

@app.route(f"/{BOT_TOKEN}", methods=['POST'])
def get_update():
    bot.process_new_updates([telebot.types.Update.de_json(request.get_data().decode('utf-8'))])
    return "!", 200

if __name__ == "__main__":
    bot.remove_webhook()
    bot.set_webhook(url=f"{WEBHOOK_URL}/{BOT_TOKEN}")
    app.run(host="0.0.0.0", port=PORT)

