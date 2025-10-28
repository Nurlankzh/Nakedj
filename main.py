import os
from flask import Flask, request
import telebot
import logging
from telebot import types

# -------------------------
# Конфигурацияны .env-тен оқимыз
# -------------------------
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
VIDEO_DIR = os.getenv("VIDEO_DIR", "videos")
DB_FILE = os.getenv("DB_FILE", "data.db")

# -------------------------
# Flask және Telegram bot
# -------------------------
app = Flask(__name__)
bot = telebot.TeleBot(BOT_TOKEN)

# -------------------------
# Logging debug үшін
# -------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()

# -------------------------
# Видео папка бар-жоғын тексереміз
# -------------------------
if not os.path.exists(VIDEO_DIR):
    os.makedirs(VIDEO_DIR)

# -------------------------
# /start командасы
# -------------------------
@bot.message_handler(commands=['start'])
def handle_start(message):
    user_id = message.from_user.id
    logger.info(f"/start received from {user_id}: {message.text}")
    
    if user_id == ADMIN_ID:
        bot.send_message(user_id, "Сәлем, Админ! Бұл сіздің панеліңіз.\nҚолданушылардың хабарламаларын көре аласыз.")
    else:
        bot.send_message(user_id, "Сәлем! Бұл қолданушы панелі.\nБот жұмыс істеп тұр.")
    
    bot.send_message(user_id, "Сіз хабарлама жіберсеңіз, лог шығады.")

# -------------------------
# Барлық хабарламаларды қабылдау
# -------------------------
@bot.message_handler(func=lambda message: True)
def handle_all_messages(message):
    user_id = message.from_user.id
    text = message.text or "<non-text message>"
    logger.info(f"Message received from {user_id}: {text}")
    
    # Админге хабарлау
    if user_id != ADMIN_ID:
        bot.send_message(ADMIN_ID, f"Қолданушы {user_id} жазды:\n{text}")
    
    bot.send_message(user_id, f"Сіздің хабарламаңыз қабылданды:\n{text}")

# -------------------------
# Flask маршруты
# -------------------------
@app.route("/", methods=["GET"])
def index():
    return "Bot is running.", 200

@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    json_str = request.get_data().decode("utf-8")
    logger.info(f"Webhook POST received: {json_str}")
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return "", 200

# -------------------------
# Webhook орнату
# -------------------------
@app.before_first_request
def setup_webhook():
    try:
        bot.remove_webhook()
        bot.set_webhook(url=f"{WEBHOOK_URL}/{BOT_TOKEN}")
        logger.info(f"Webhook set successfully at {WEBHOOK_URL}/{BOT_TOKEN}")
    except Exception as e:
        logger.error(f"Error setting webhook: {e}")

# -------------------------
# Flask серверін іске қосу
# -------------------------
if __name__ == "__main__":
    logger.info("Starting Flask server...")
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
