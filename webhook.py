import os
import logging
from flask import Flask, request
import telebot

# ---------------------------
# CONFIG
# ---------------------------
BOT_TOKEN = os.getenv("BOT_TOKEN") or "8419149602:AAHvLF3XmreCAQpvJy_8-RRJDH0g_qy9Oto"
WEBHOOK_URL = os.getenv("WEBHOOK_URL") or "https://nakedj-7-g6vy.onrender.com"
PORT = int(os.getenv("PORT") or 10000)

# ---------------------------
# Logging
# ---------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------
# Bot + Flask
# ---------------------------
bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# ---------------------------
# Flask webhook endpoint
# ---------------------------
@app.route("/webhook", methods=['POST'])
def webhook():
    try:
        json_str = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_str)
        bot.process_new_updates([update])
    except Exception:
        logger.exception("Webhook processing error")
    return "", 200

@app.route("/", methods=['GET'])
def index():
    return "Bot is running", 200

# ---------------------------
# Setup webhook
# ---------------------------
def setup_webhook():
    try:
        bot.remove_webhook()
        full_url = WEBHOOK_URL.rstrip("/") + "/webhook"
        result = bot.set_webhook(url=full_url)
        logger.info(f"Webhook set -> {full_url}  result: {result}")
    except Exception:
        logger.exception("Failed to set webhook")

setup_webhook()

# ---------------------------
# Run Flask
# ---------------------------
if __name__ == "__main__":
    logger.info(f"Starting Flask on port {PORT}")
    app.run(host="0.0.0.0", port=PORT)
