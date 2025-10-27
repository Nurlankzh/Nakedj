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
    progress INTEGER DEFAULT 0
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
    if not cursor.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,)).fetchone():
        cursor.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
        conn.commit()

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn1 = types.KeyboardButton("🎥 Видео")
    btn2 = types.KeyboardButton("🛍 Сатып алу")
    btn3 = types.KeyboardButton("👥 Реферал алу")
    if user_id == ADMIN_ID:
        btn4 = types.KeyboardButton("📊 Статистика")
        btn5 = types.KeyboardButton("🗑 Видеоларды өшіру")
        markup.add(btn1, btn2)
        markup.add(btn3, btn4)
        markup.add(btn5)
    else:
        markup.add(btn1, btn2)
        markup.add(btn3)

    bot.send_message(
        user_id,
        "Сәлем 👋\n\nБұл бот арқылы видеоларды көріп бонус аласың!\n"
        "🎥 Әр видео = 1 бонус\nКүн сайын 5 бонус автоматты түрде беріледі 🎁",
        reply_markup=markup
    )


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


# 🛍 Сатып алу
@bot.message_handler(func=lambda m: m.text == "🛍 Сатып алу")
def buy(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("🔙 Артқа"))
    bot.send_message(message.chat.id, "@KazHubALU жазыңыз — видеолар сатылымда 🎥", reply_markup=markup)


# 🔙 Артқа
@bot.message_handler(func=lambda m: m.text == "🔙 Артқа")
def back(message):
    start(message)


# 👥 Реферал алу
@bot.message_handler(func=lambda m: m.text == "👥 Реферал алу")
def referral(message):
    user_id = message.from_user.id
    ref_link = f"https://t.me/Sallemkz_bot?start={user_id}"
    bot.send_message(user_id, f"🔗 Сіздің сілтемеңіз:\n{ref_link}\n\nӘр шақырған адам үшін +5 бонус 🎁")


# 📊 Статистика
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


# ✅ Иә
@bot.message_handler(func=lambda m: m.text == "✅ Иә, өшір" and m.from_user.id == ADMIN_ID)
def delete_videos(message):
    cursor.execute("DELETE FROM videos")
    cursor.execute("UPDATE users SET progress = 0")
    conn.commit()
    bot.send_message(message.chat.id, "✅ Барлық видеолар өшірілді!")
    start(message)


# ❎ Жоқ
@bot.message_handler(func=lambda m: m.text == "❎ Жоқ" and m.from_user.id == ADMIN_ID)
def cancel_delete(message):
    bot.send_message(message.chat.id, "❎ Видеолар сақталды, ештеңе өшірілмеді.")
    start(message)


# 📩 Админ видео жібереді
@bot.message_handler(content_types=['video'])
def add_video(message):
    if message.from_user.id != ADMIN_ID:
        return
    cursor.execute("INSERT INTO videos (file_id) VALUES (?)", (message.video.file_id,))
    conn.commit()
    bot.send_message(message.chat.id, f"✅ Видео сақталды! Барлығы: {cursor.execute('SELECT COUNT(*) FROM videos').fetchone()[0]} 🎥")


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
