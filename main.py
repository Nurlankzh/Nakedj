import telebot
from telebot import types
from flask import Flask, request
import sqlite3
import threading
import time

# 🔑 Бот мәліметтері
BOT_TOKEN = "8419149602:AAHvLF3XmreCAQpvJy_8-RRJDH0g_qy9Oto"
ADMIN_ID = 6927494520
WEBHOOK_URL = "https://nakedj-5.onrender.com"

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# 📦 Деректер базасы
conn = sqlite3.connect("data.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("""CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    bonus INTEGER DEFAULT 5,
    progress INTEGER DEFAULT 0,
    referrals TEXT DEFAULT ''
)""")
cursor.execute("""CREATE TABLE IF NOT EXISTS videos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id TEXT
)""")
conn.commit()

# 🔁 Күн сайын бонус қосу
def daily_bonus():
    while True:
        cursor.execute("UPDATE users SET bonus = bonus + 5")
        conn.commit()
        users = cursor.execute("SELECT user_id FROM users").fetchall()
        for user in users:
            try:
                bot.send_message(user[0], "🎁 Сізге жаңа 5 бонус берілді!")
            except:
                pass
        time.sleep(86400)

threading.Thread(target=daily_bonus, daemon=True).start()

# 🏠 /start
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    args = message.text.split()
    ref_id = args[1] if len(args) > 1 else None

    user_exists = cursor.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,)).fetchone()
    if not user_exists:
        cursor.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
        conn.commit()
        bot.send_message(user_id, "🎉 Сізге +5 бонус берілді!")

        # Реферал бонус
        if ref_id and ref_id.isdigit() and int(ref_id) != user_id:
            ref_user = cursor.execute("SELECT 1 FROM users WHERE user_id = ?", (int(ref_id),)).fetchone()
            if ref_user:
                cursor.execute("UPDATE users SET bonus = bonus + 5, referrals = referrals || ? || ',' WHERE user_id = ?",
                               (str(user_id), int(ref_id)))
                conn.commit()
                bot.send_message(int(ref_id), f"🎁 Сіз жаңа қолданушы шақырдыңыз! +5 бонус ✅")

    # 📝 Меню батырмалары
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn1 = types.KeyboardButton("🎥 Видео")
    btn2 = types.KeyboardButton("👥 Реферал алу")
    btn3 = types.KeyboardButton("📢 Каналымызға қосылу")
    btn4 = types.KeyboardButton("📦 Канал алу")
    if user_id == ADMIN_ID:
        btn5 = types.KeyboardButton("📊 Статистика")
        btn6 = types.KeyboardButton("🗑 Видеоларды өшіру")
        btn7 = types.KeyboardButton("📩 Рассылка")
        markup.add(btn1, btn2, btn3, btn4)
        markup.add(btn5, btn6, btn7)
    else:
        markup.add(btn1, btn2, btn3, btn4)

    bot.send_message(user_id,
                     "Сәлем 👋\nБұл бот арқылы видеоларды көріп бонус аласың!\n"
                     "🎥 Әр видео = 1 бонус\nКүн сайын 5 бонус автоматты түрде беріледі 🎁",
                     reply_markup=markup)

# 🎥 Видео
@bot.message_handler(func=lambda m: m.text == "🎥 Видео")
def video_watch(message):
    user_id = message.from_user.id
    user = cursor.execute("SELECT bonus, progress FROM users WHERE user_id = ?", (user_id,)).fetchone()
    if not user:
        start(message)
        return

    bonus, progress = user
    videos = cursor.execute("SELECT file_id FROM videos").fetchall()
    if bonus <= 0:
        bot.send_message(user_id, "❌ Бонус біткен. Адам шақырыңыз немесе 24 сағат күтіңіз.")
        return
    if progress >= len(videos):
        bot.send_message(user_id, "🎬 Барлық видеоларды көріп болдыңыз!")
        return

    video_id = videos[progress][0]
    bot.send_video(user_id, video_id)
    cursor.execute("UPDATE users SET bonus = ?, progress = ? WHERE user_id = ?",
                   (bonus - 1, progress + 1, user_id))
    conn.commit()
    bot.send_message(user_id, f"✅ Видео көрсетілді!\nҚалған бонус: {bonus - 1} 🎁")

# 👥 Реферал алу
@bot.message_handler(func=lambda m: m.text == "👥 Реферал алу")
def referral(message):
    user_id = message.from_user.id
    ref_link = f"https://t.me/Sallemkz_bot?start={user_id}"
    bot.send_message(user_id, f"🔗 Сіздің сілтемеңіз:\n{ref_link}\n\nӘр шақырған адам үшін +5 бонус 🎁")

# 📢 Каналымызға қосылу
@bot.message_handler(func=lambda m: m.text == "📢 Каналымызға қосылу")
def join_channel(message):
    user_id = message.from_user.id
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("🔙 Басты мәзірге оралу"))
    bot.send_message(
        user_id,
        "🌟 Каналдарға қосылыңыз:\n\n"
        "1️⃣ https://t.me/Qazhuboyndar\n"
        "2️⃣ https://t.me/+XRoxE_8bUM1mMmIy",
        reply_markup=markup
    )

# 📦 Канал алу
@bot.message_handler(func=lambda m: m.text == "📦 Канал алу")
def get_channel(message):
    user_id = message.from_user.id
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("🔙 Артқа"))
    bot.send_message(
        user_id,
        "❤️ Канал алғыңыз келсе жазыңыз:\n@KazHubALU ✨️",
        reply_markup=markup
    )

# 🔙 Басты мәзірге оралу / Артқа
@bot.message_handler(func=lambda m: m.text in ["🔙 Басты мәзірге оралу", "🔙 Артқа"])
def back_to_menu(message):
    start(message)

# 📊 Статистика (админ)
@bot.message_handler(func=lambda m: m.text == "📊 Статистика" and m.from_user.id == ADMIN_ID)
def stats(message):
    total = cursor.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    total_videos = cursor.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
    bot.send_message(message.chat.id, f"👥 Қолданушылар: {total}\n🎥 Видеолар саны: {total_videos}")

# 🗑 Видеоларды өшіру
@bot.message_handler(func=lambda m: m.text == "🗑 Видеоларды өшіру" and m.from_user.id == ADMIN_ID)
def confirm_delete(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("✅ Иә, өшір"), types.KeyboardButton("❎ Жоқ"))
    bot.send_message(message.chat.id, "Сіз видеоларды өшіргіңіз келе ме?", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "✅ Иә, өшір" and m.from_user.id == ADMIN_ID)
def delete_videos(message):
    cursor.execute("DELETE FROM videos")
    cursor.execute("UPDATE users SET progress = 0")
    conn.commit()
    bot.send_message(message.chat.id, "✅ Барлық видеолар өшірілді!")
    start(message)

@bot.message_handler(func=lambda m: m.text == "❎ Жоқ" and m.from_user.id == ADMIN_ID)
def cancel_delete(message):
    bot.send_message(message.chat.id, "❎ Видеолар сақталды, ештеңе өшірілмеді.")
    start(message)

# 📩 Админ рассылка
admin_broadcast = {}

@bot.message_handler(func=lambda m: m.text == "📩 Рассылка" and m.from_user.id == ADMIN_ID)
def start_broadcast(message):
    bot.send_message(message.chat.id, "✏️ Қандай хабарлама жібергіңіз келеді?")
    admin_broadcast[message.chat.id] = "WAITING_TEXT"

@bot.message_handler(func=lambda m: admin_broadcast.get(m.chat.id) == "WAITING_TEXT")
def get_broadcast_text(message):
    admin_broadcast[message.chat.id] = message.text
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("✅ Ия"), types.KeyboardButton("❎ Жоқ"))
    bot.send_message(message.chat.id, f"Хабарламаны жіберейін бе?\n\n{message.text}", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text in ["✅ Ия", "❎ Жоқ"] and m.from_user.id == ADMIN_ID)
def confirm_broadcast(message):
    if message.text == "✅ Ия":
        text = admin_broadcast.get(message.chat.id)
        users = cursor.execute("SELECT user_id FROM users").fetchall()
        for u in users:
            try:
                bot.send_message(u[0], text)
            except:
                pass
        bot.send_message(message.chat.id, "✅ Хабарлама барлық қолданушыларға жіберілді!")
    else:
        bot.send_message(message.chat.id, "❎ Рассылка тоқтатылды.")
    admin_broadcast.pop(message.chat.id, None)
    start(message)

# 📩 Админ видео қосу
@bot.message_handler(content_types=['video'])
def add_video(message):
    if message.from_user.id != ADMIN_ID:
        return
    cursor.execute("INSERT INTO videos (file_id) VALUES (?)", (message.video.file_id,))
    conn.commit()
    total = cursor.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
    bot.send_message(message.chat.id, f"✅ Видео сақталды! Барлығы: {total} 🎥")

# 🌐 Flask Webhook бөлігі
@app.route(f"/{BOT_TOKEN}", methods=['POST'])
def webhook():
    update = telebot.types.Update.de_json(request.stream.read().decode('utf-8'))
    bot.process_new_updates([update])
    return "ok", 200

@app.route("/")
def index():
    bot.remove_webhook()
    bot.set_webhook(url=f"{WEBHOOK_URL}/{BOT_TOKEN}")
    return "Бот жұмыс істеп тұр ✅", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
