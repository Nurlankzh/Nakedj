# main.py
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
BOT_TOKEN = "7875991285:AAG4pChovJ67bxytVzB2-aIXrRYKUoWRtvw"
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
    with open(path,"wb") as f:
        f.write(b)
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
    ref = int(args[1]) if len(args) > 1 and args[1].isdigit() else None
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
    if not u or u[0] != 1:
        bot.send_message(user_id, "❌ Бұл бот тек 18+ пайдаланушыларға арналған.")
        return
    ensure_user(user_id)

    # --- VIDEO ---
    if text == "🎥 Видео көру":
        if not check_subscription(user_id):
            bot.send_message(user_id, f"📢 Видео көру үшін {CHANNEL_USERNAME} каналына тіркеліңіз!")
            return
        with db_lock:
            balance, progress = cursor.execute("SELECT balance, progress_video FROM users WHERE user_id=?", (user_id,)).fetchone()
            rows = cursor.execute("SELECT file_id, file_path FROM videos ORDER BY id ASC").fetchall()
            if not rows:
                bot.send_message(user_id, "🎬 Видеолар жоқ.")
                return
            if user_id != ADMIN_ID and balance < 2:
                bot.send_message(user_id, "💸 Видео көру үшін 2 бонус қажет.")
                return
            idx = progress if progress < len(rows) else 0
            file_id, file_path = rows[idx]
            try:
                if file_path and os.path.exists(file_path):
                    with open(file_path, "rb") as f:
                        bot.send_video(user_id, f)
                else:
                    bot.send_video(user_id, file_id)
            except:
                bot.send_message(user_id, "Видео жібергенде қате.")
                return
            cursor.execute("UPDATE users SET balance=?, progress_video=? WHERE user_id=?", (max(balance-2,0), idx+1, user_id))
            conn.commit()
        return

    # --- MEDIA UPLOAD ---
    elif text == "➕ Видео/Фото жіберу":
        bot.send_message(user_id, "Файл жіберіңіз. Админ мақұлдайды.")
        return

    # --- BONUS ---
    elif text == "💸 Мой бонус":
        bal = cursor.execute("SELECT balance FROM users WHERE user_id=?", (user_id,)).fetchone()[0]
        bot.send_message(user_id, f"Сізде қазір: {bal}💸")
        return

    # --- REFERRAL ---
    elif text == "🔗 Реферал сілтеме":
        bot.send_message(user_id, f"Сіздің реферал сілтеме: https://t.me/KazHub_slivbot?start={user_id}")
        return

    # --- SHOP ---
    elif text == "🛒 Магазин":
        bot.send_message(user_id, f"Бонус сатып алғыңыз келсе: {SHOP_USERNAME} жазыңыз.")
        return

    # --- INFO ---
    elif text == "ℹ️ Ақпарат":
        bot.send_message(user_id, "Бот қалай жұмыс істейді:\n- Видео көру үшін бонус қажет\n- Видео/Фото жіберу админ арқылы\n- Реферал арқылы бонус\n- 18+ адамдарға арналған")
        return

    # --- LOTTERY JOIN ---
    elif text == "🎯 Лотереяға қатысу":
        with db_lock:
            if not lottery_status():
                bot.send_message(user_id,"Лотерея әлі басталмаған.")
                return
            exists = cursor.execute("SELECT 1 FROM lottery WHERE user_id=?",(user_id,)).fetchone()
            if exists:
                bot.send_message(user_id,"Сіз бұрын қосылғансыз!")
                return
            cursor.execute("INSERT INTO lottery (user_id, joined_at) VALUES (?,?)",(user_id, datetime.utcnow().isoformat()))
            conn.commit()
        bot.send_message(user_id,"🎉 Сіз Лотереяға қосылдыңыз!")
        return

    # --- ADMIN ONLY ---
    if user_id != ADMIN_ID:
        return

    # Бонус беру
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

    # Pending
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
                    else:
                        bot.send_video(user_id,file_id,caption=f"#{pid} {ctype} from {uploader}", reply_markup=kb)
                else:
                    if file_path and os.path.exists(file_path):
                        with open(file_path,"rb") as f: bot.send_photo(user_id,f,caption=f"#{pid} {ctype} from {uploader}", reply_markup=kb)
                    else:
                        bot.send_photo(user_id,file_id,caption=f"#{pid} {ctype} from {uploader}", reply_markup=kb)
            except: pass
        return

    # Лотерея бастау
    elif text=="🎯 Лотерея бастау":
        with db_lock:
            cursor.execute("DELETE FROM lottery")
            conn.commit()
        bot.send_message(user_id,"🎯 Лотерея басталды! Қолданушылар 24 сағат ішінде қатыса алады.")
        return

    # Лотерея жеңімпазын таңдау
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

    # Топ 10 шақырғандар
    elif text=="🏆 Топ 10 шақырғандар":
        top10 = cursor.execute("SELECT invited_by, COUNT(*) as cnt FROM users WHERE invited_by IS NOT NULL GROUP BY invited_by ORDER BY cnt DESC LIMIT 10").fetchall()
        msg_text = "🏆 Топ 10 шақырғандар:\n"
        for u,cnt in top10: 
            msg_text += f"{u}: {cnt} шақырды\n"
        bot.send_message(user_id,msg_text)
        return

    # Статистика
    elif text=="📊 Статистика":
        users_count = cursor.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        videos_count = cursor.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
        pending_count = cursor.execute("SELECT COUNT(*) FROM pending").fetchone()[0]
        bot.send_message(user_id,f"📊 Статистика:\nҚолданушылар: {users_count}\nВидео: {videos_count}\nPending: {pending_count}")
        return

    # Рассылка
    elif text=="📢 Рассылка":
        bot.send_message(user_id,"Жіберілетін хабарламаны жіберіңіз:")
        bot.register_next_step_handler(msg, handle_broadcast)
        return

# ---------------------------
# MEDIA HANDLER
# ---------------------------
@bot.message_handler(func=lambda m: True)
def handle_text(msg):
    remove_old_pending()
    user_id = msg.from_user.id
    text = msg.text
    
    # Пайдаланушыны тексеру
    u = cursor.execute("SELECT is_adult FROM users WHERE user_id=?", (user_id,)).fetchone()
    if not u or u[0] != 1:
        bot.send_message(user_id, "❌ Бұл бот тек 18+ пайдаланушыларға арналған.")
        return
    ensure_user(user_id)

    # --- БАРЛЫҚ ПАЙДАЛАНУШЫЛАРҒА АРНАЛҒАН БАТЫРМАЛАР ---
    if text == "🎥 Видео көру":
        if not check_subscription(user_id):
            bot.send_message(user_id, f"📢 Видео көру үшін {CHANNEL_USERNAME} каналына тіркеліңіз!")
            return
        with db_lock:
            res = cursor.execute("SELECT balance, progress_video FROM users WHERE user_id=?", (user_id,)).fetchone()
            balance, progress = res
            rows = cursor.execute("SELECT file_id, file_path FROM videos ORDER BY id ASC").fetchall()
            if not rows:
                bot.send_message(user_id, "🎬 Видеолар әзірге жоқ.")
                return
            if user_id != ADMIN_ID and balance < 2:
                bot.send_message(user_id, "💸 Видео көру үшін 2 бонус қажет.")
                return
            idx = progress if progress < len(rows) else 0
            file_id, file_path = rows[idx]
            try:
                if file_path and os.path.exists(file_path):
                    with open(file_path, "rb") as f: bot.send_video(user_id, f)
                else: bot.send_video(user_id, file_id)
                cursor.execute("UPDATE users SET balance=?, progress_video=? WHERE user_id=?", (max(balance-2,0), idx+1, user_id))
                conn.commit()
            except:
                bot.send_message(user_id, "❌ Видео жіберу кезінде қате шықты.")
        return

    elif text == "➕ Видео/Фото жіберу":
        bot.send_message(user_id, "📤 Файл жіберіңіз (Видео немесе Фото). Админ мақұлдаған соң сізге бонус беріледі.")
        return

    elif text == "💸 Мой бонус":
        bal = cursor.execute("SELECT balance FROM users WHERE user_id=?", (user_id,)).fetchone()[0]
        bot.send_message(user_id, f"💰 Сіздің балансыңыз: {bal}💸")
        return

    elif text == "🔗 Реферал сілтеме":
        bot.send_message(user_id, f"🔗 Сіздің реферал сілтемеңіз:\nhttps://t.me/KazHub_slivbot?start={user_id}\n\nӘр шақырылған адам үшін +6💸 аласыз!")
        return

    elif text == "🛒 Магазин":
        bot.send_message(user_id, f"🛒 Бонус сатып алу үшін: {SHOP_USERNAME}")
        return

    elif text == "ℹ️ Ақпарат":
        bot.send_message(user_id, "ℹ️ Бот туралы:\n- 1 видео көру = 2💸\n- Видео жіберіп мақұлданса = 12💸\n- Дос шақырсаңыз = 6💸")
        return

    elif text == "🎯 Лотереяға қатысу":
        if not lottery_status():
            bot.send_message(user_id, "❌ Лотерея әлі басталған жоқ.")
            return
        with db_lock:
            exists = cursor.execute("SELECT 1 FROM lottery WHERE user_id=?", (user_id,)).fetchone()
            if exists:
                bot.send_message(user_id, "⚠️ Сіз тізімде барсыз!")
                return
            cursor.execute("INSERT INTO lottery (user_id, joined_at) VALUES (?,?)", (user_id, datetime.utcnow().isoformat()))
            conn.commit()
        bot.send_message(user_id, "🎉 Сіз сәтті тіркелдіңіз!")
        return

    # --- ТЕК АДМИНГЕ АРНАЛҒАН БАТЫРМАЛАР ---
    if user_id == ADMIN_ID:
        if text == "✅ Pending файлдар":
            pendings = cursor.execute("SELECT id,uploader_id,content_type,file_id,file_path FROM pending ORDER BY id ASC").fetchall()
            if not pendings:
                bot.send_message(user_id, "📭 Күтудегі файлдар жоқ.")
                return
            for pid, uploader, ctype, file_id, file_path in pendings:
                kb = InlineKeyboardMarkup()
                kb.add(InlineKeyboardButton("✅ Мақұлдау", callback_data=f"approve_{pid}"),
                       InlineKeyboardButton("❌ Растамау", callback_data=f"reject_{pid}"))
                caption = f"ID: #{pid}\nЖіберуші: {uploader}\nТүрі: {ctype}"
                try:
                    if ctype == "video":
                        if file_path and os.path.exists(file_path):
                            with open(file_path, "rb") as f: bot.send_video(user_id, f, caption=caption, reply_markup=kb)
                        else: bot.send_video(user_id, file_id, caption=caption, reply_markup=kb)
                    else:
                        if file_path and os.path.exists(file_path):
                            with open(file_path, "rb") as f: bot.send_photo(user_id, f, caption=caption, reply_markup=kb)
                        else: bot.send_photo(user_id, file_id, caption=caption, reply_markup=kb)
                except: pass
            return

        elif text == "📊 Статистика":
            u_cnt = cursor.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            v_cnt = cursor.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
            p_cnt = cursor.execute("SELECT COUNT(*) FROM pending").fetchone()[0]
            bot.send_message(user_id, f"📊 Статистика:\n👥 Пайдаланушылар: {u_cnt}\n🎥 Видеолар: {v_cnt}\n⏳ Күтуде: {p_cnt}")
            return

        elif text == "🎯 Лотерея бастау":
            with db_lock:
                cursor.execute("DELETE FROM lottery")
                conn.commit()
            bot.send_message(user_id, "🎯 Жаңа лотерея басталды!")
            return

        elif text == "🎖 Лотерея жеңімпазын таңдау":
            participants = cursor.execute("SELECT user_id FROM lottery").fetchall()
            if not participants:
                bot.send_message(user_id, "❌ Қатысушылар жоқ.")
                return
            winner = random.choice(participants)[0]
            bot.send_message(user_id, f"🏆 Жеңімпаз ID: {winner}")
            bot.send_message(winner, "🎊 Құттықтаймыз! Сіз лотереяда жеңдіңіз!")
            return

        elif text == "🏆 Топ 10 шақырғандар":
            top = cursor.execute("SELECT invited_by, COUNT(*) as cnt FROM users WHERE invited_by IS NOT NULL GROUP BY invited_by ORDER BY cnt DESC LIMIT 10").fetchall()
            res = "🏆 Үздік шақырушылар:\n"
            for u, c in top: res += f"ID {u}: {c} адам\n"
            bot.send_message(user_id, res)
            return

        elif text == "📢 Рассылка":
            bot.send_message(user_id, "📢 Хабарлама мәтінін жазыңыз:")
            bot.register_next_step_handler(msg, handle_broadcast)
            return

        # Бонус беру тек "ID Мөлшері" форматында болса (мысалы: 6303091468 50)
        elif " " in text:
            try:
                parts = text.split()
                if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                    t_id, amt = int(parts[0]), int(parts[1])
                    cursor.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (amt, t_id))
                    conn.commit()
                    bot.send_message(user_id, f"✅ {amt}💸 берілді.")
                    bot.send_message(t_id, f"🎁 Админ сізге {amt}💸 бонус берді!")
            except: pass
            return

            # ---------------------------
# CALLBACK HANDLER
# ---------------------------
@bot.callback_query_handler(func=lambda c: True)
def handle_callbacks(call):
    user_id = call.from_user.id
    data = call.data

    # 18+ тексеру
    if data.startswith("adult_"):
        if data == "adult_yes":
            cursor.execute("UPDATE users SET is_adult=1 WHERE user_id=?", (user_id,))
            conn.commit()
            bot.send_message(user_id, "✅ Сіз 18+ ересектер ботқа қол жеткіздіңіз.",
                             reply_markup=get_main_keyboard(admin=(user_id==ADMIN_ID), lottery_active=lottery_status()))
        else:
            cursor.execute("UPDATE users SET is_adult=0 WHERE user_id=?", (user_id,))
            conn.commit()
            bot.send_message(user_id, "❌ Бұл бот тек 18+ адамдарға арналған.")
        return

    # Pending файлдарды мақұлдау/кері қайтару
    if data.startswith("approve_") or data.startswith("reject_"):
        pid = int(data.split("_")[1])
        with db_lock:
            pending = cursor.execute("SELECT uploader_id, content_type, file_id, file_path FROM pending WHERE id=?", (pid,)).fetchone()
            if not pending: return
            uploader, ctype, file_id, file_path = pending
            if data.startswith("approve_"):
                if ctype == "video":
                    cursor.execute("INSERT INTO videos (file_id,file_path,added_by,created_at) VALUES (?,?,?,?)",
                                   (file_id, file_path, uploader, datetime.utcnow().isoformat()))
                else:
                    cursor.execute("INSERT INTO photos (file_id,file_path,added_by,created_at) VALUES (?,?,?,?)",
                                   (file_id, file_path, uploader, datetime.utcnow().isoformat()))
                bot.send_message(uploader, f"✅ Сіздің {ctype} файлыңыз мақұлданды! +12💸")
                cursor.execute("UPDATE users SET balance=balance+12 WHERE user_id=?", (uploader,))
            else:
                bot.send_message(uploader, f"❌ Сіздің {ctype} файлыңыз мақұлданбады.")
            cursor.execute("DELETE FROM pending WHERE id=?", (pid,))
            conn.commit()
        return

# ---------------------------
# BROADCAST HANDLER
# ---------------------------
def handle_broadcast(msg):
    text = msg.text
    with db_lock:
        users = cursor.execute("SELECT user_id FROM users").fetchall()
    for (uid,) in users:
        try:
            bot.send_message(uid, text)
        except: pass

# ---------------------------
# FLASK WEBHOOK
# ---------------------------
@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    json_str = request.get_data().decode("utf-8")
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return "ok", 200

# ---------------------------
# BOT STARTER
# ---------------------------
if __name__ == "__main__":
    # Webhook орнату
    bot.remove_webhook()
    bot.set_webhook(url=f"{WEBHOOK_URL}/{BOT_TOKEN}")
    logger.info("Bot started with webhook.")
    # Flask серверін іске қосу
    app.run(host="0.0.0.0", port=PORT)
