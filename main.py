import asyncio
import logging
import random
from datetime import datetime

import aiosqlite
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.utils import executor
from aiogram.dispatcher.middlewares import BaseMiddleware
from aiogram.dispatcher.handler import CancelHandler

# ========== CONFIG ==========
TOKEN = "6592332777:AAEGSbHq71W_X2DXwyXqrJcAqt-XSsHbqCk"
ADMIN_ID = 6303091468
DB_NAME = "bot.db"
CHANNEL = "@your_channel"

bot = Bot(TOKEN, parse_mode="HTML")
dp = Dispatcher(bot, storage=MemoryStorage())

logging.basicConfig(level=logging.INFO)

# ========== DB ==========
class DB:
    def __init__(self):
        self.conn = None

    async def connect(self):
        self.conn = await aiosqlite.connect(DB_NAME)
        self.conn.row_factory = aiosqlite.Row

        await self.conn.executescript("""
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY,
            balance INTEGER DEFAULT 5,
            banned INTEGER DEFAULT 0,
            joined TEXT
        );

        CREATE TABLE IF NOT EXISTS content(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id TEXT,
            genre TEXT
        );
        """)
        await self.conn.commit()

db = DB()

# ========== FSM ==========
class Admin(StatesGroup):
    add_file = State()
    add_genre = State()
    broadcast = State()
    ban = State()

# ========== ANTI FLOOD ==========
class Flood(BaseMiddleware):
    def __init__(self):
        self.last = {}
        super().__init__()

    async def on_process_message(self, msg: types.Message, data: dict):
        uid = msg.from_user.id
        now = asyncio.get_event_loop().time()

        if uid in self.last and now - self.last[uid] < 0.5:
            await msg.reply("⏳ Тым жылдам")
            raise CancelHandler()

        self.last[uid] = now

dp.middleware.setup(Flood())

# ========== HELP ==========
async def check_sub(uid):
    try:
        m = await bot.get_chat_member(CHANNEL, uid)
        return m.status not in ["left", "kicked"]
    except:
        return True

# ========== UI ==========
def kb(uid):
    k = types.ReplyKeyboardMarkup(resize_keyboard=True)
    k.add("🎬 Көру", "👤 Профиль")
    if uid == ADMIN_ID:
        k.add("⚙️ Admin")
    return k

# ========== START ==========
@dp.message_handler(commands=['start'])
async def start(m):
    uid = m.from_user.id

    await db.conn.execute(
        "INSERT OR IGNORE INTO users(id, joined) VALUES(?,?)",
        (uid, datetime.now().isoformat())
    )
    await db.conn.commit()

    await m.answer("🚀 BOT READY", reply_markup=kb(uid))

# ========== PROFILE ==========
@dp.message_handler(lambda m: m.text == "👤 Профиль")
async def profile(m):
    u = await db.conn.execute_fetchone("SELECT * FROM users WHERE id=?", (m.from_user.id,))
    await m.answer(f"ID: {u['id']}\nBalance: {u['balance']}")

# ========== CONTENT ==========
@dp.message_handler(lambda m: m.text == "🎬 Көру")
async def watch(m):
    if not await check_sub(m.from_user.id):
        return await m.answer("Subscribe first")

    kb = types.InlineKeyboardMarkup()
    for g in ["Action", "Movie", "Comedy"]:
        kb.add(types.InlineKeyboardButton(g, callback_data=f"g_{g}"))

    await m.answer("Genre:", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data.startswith("g_"))
async def get(c):
    genre = c.data.split("_")[1]

    u = await db.conn.execute_fetchone(
        "SELECT balance FROM users WHERE id=?", (c.from_user.id,)
    )

    if u["balance"] <= 0:
        return await c.answer("No balance", show_alert=True)

    content = await db.conn.execute_fetchone(
        "SELECT * FROM content WHERE genre=? ORDER BY RANDOM() LIMIT 1",
        (genre,)
    )

    if not content:
        return await c.answer("Empty")

    await db.conn.execute(
        "UPDATE users SET balance=balance-1 WHERE id=?",
        (c.from_user.id,)
    )
    await db.conn.commit()

    await bot.send_video(c.from_user.id, content["file_id"])
    await c.answer("OK")

# ========== ADMIN ==========
@dp.message_handler(lambda m: m.text == "⚙️ Admin", user_id=ADMIN_ID)
async def admin(m):
    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("➕ Add", callback_data="add"),
        types.InlineKeyboardButton("📢 BC", callback_data="bc"),
        types.InlineKeyboardButton("🚫 Ban", callback_data="ban")
    )
    await m.answer("ADMIN", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data == "add", user_id=ADMIN_ID)
async def add(c):
    await Admin.add_file.set()
    await c.message.answer("Send video")

@dp.message_handler(content_types=['video'], state=Admin.add_file)
async def save(m, state):
    await state.update_data(fid=m.video.file_id)
    await Admin.add_genre.set()
    await m.answer("Genre?")

@dp.message_handler(state=Admin.add_genre)
async def save2(m, state):
    d = await state.get_data()

    await db.conn.execute(
        "INSERT INTO content(file_id, genre) VALUES(?,?)",
        (d["fid"], m.text)
    )
    await db.conn.commit()

    await state.finish()
    await m.answer("Saved")

# ========== STARTUP ==========
async def on_start(_):
    await db.connect()
    print("ONLINE")

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True, on_startup=on_start)
