import asyncio
import logging
import os
import random
from datetime import datetime, timedelta

import aiosqlite
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.dispatcher.middlewares import BaseMiddleware
from aiogram.dispatcher.handler import CancelHandler, current_handler
from aiogram.utils import executor
from aiogram.utils.exceptions import Throttled, BadRequest

# ================= CONFIG =================
API_TOKEN = "6592332777:AAEGSbHq71W_X2DXwyXqrJcAqt-XSsHbqCk"
ADMIN_ID = 6303091468
CHANNEL = "@QZSTOP"
DB_PATH = "enterprise_core.db"

logging.basicConfig(level=logging.INFO)

bot = Bot(token=API_TOKEN, parse_mode="HTML")
dp = Dispatcher(bot, storage=MemoryStorage())

# ================= DATABASE LAYER =================
class DB:
    def __init__(self):
        self.db = None

    async def connect(self):
        self.db = await aiosqlite.connect(DB_PATH, isolation_level=None)
        self.db.row_factory = aiosqlite.Row

        await self.db.executescript("""
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY,
            balance INTEGER DEFAULT 10,
            banned INTEGER DEFAULT 0,
            last_bonus TEXT
        );

        CREATE TABLE IF NOT EXISTS content(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id TEXT,
            genre TEXT,
            views INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS history(
            user_id INTEGER,
            content_id INTEGER
        );
        """)

db = DB()

# ================= SECURITY MIDDLEWARE =================
class AntiFlood(BaseMiddleware):
    def __init__(self): super().__init__()

    async def on_process_message(self, message, data):
        handler = current_handler.get()
        if not handler: return

        try:
            await dp.throttle("global", rate=0.7)
        except Throttled:
            await message.reply("⏳ Жылдамдық тым жоғары!")
            raise CancelHandler()

dp.middleware.setup(AntiFlood())

# ================= CORE HELPERS =================
async def check_subscription(uid: int):
    try:
        m = await bot.get_chat_member(CHANNEL, uid)
        return m.status not in ["left", "kicked"]
    except:
        return True  # enterprise fallback

async def get_content(uid: int, genre: str):
    # ZERO duplication + fast random
    q = """
    SELECT * FROM content
    WHERE genre=? AND id NOT IN (
        SELECT content_id FROM history WHERE user_id=?
    )
    ORDER BY RANDOM()
    LIMIT 1
    """
    async with db.db.execute(q, (genre, uid)) as cur:
        return await cur.fetchone()

# ================= FSM =================
class AdminState(StatesGroup):
    add_file = State()
    add_genre = State()
    broadcast = State()
    ban_user = State()

# ================= USER SYSTEM =================
@dp.message_handler(commands=["start"])
async def start(m: types.Message):
    uid = m.from_user.id

    await db.db.execute(
        "INSERT OR IGNORE INTO users(id) VALUES(?)",
        (uid,)
    )

    await db.db.commit()

    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("🎬 Контент", "👤 Профиль", "🎁 Бонус")
    if uid == ADMIN_ID:
        kb.add("⚙️ Admin")

    await m.answer("🚀 ENTERPRISE CORE ACTIVE", reply_markup=kb)

# ================= PROFILE =================
@dp.message_handler(lambda m: m.text == "👤 Профиль")
async def profile(m):
    async with db.db.execute("SELECT * FROM users WHERE id=?", (m.from_user.id,)) as c:
        u = await c.fetchone()

    await m.answer(
        f"👤 ID: {u['id']}\n💰 Balance: {u['balance']}"
    )

# ================= CONTENT ENGINE =================
@dp.message_handler(lambda m: m.text == "🎬 Контент")
async def genres(m):
    if not await check_subscription(m.from_user.id):
        return await m.answer("❌ Каналға тіркеліңіз")

    kb = types.InlineKeyboardMarkup()
    for g in ["Action", "Comedy", "Movie"]:
        kb.add(types.InlineKeyboardButton(g, callback_data=f"g_{g}"))

    await m.answer("🎭 Жанр таңдаңыз:", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data.startswith("g_"))
async def send(c):
    uid = c.from_user.id
    genre = c.data.split("_")[1]

    async with db.db.execute("SELECT balance FROM users WHERE id=?", (uid,)) as cur:
        u = await cur.fetchone()
        if not u or u["balance"] < 1:
            return await c.answer("❌ Баланс жоқ", show_alert=True)

    content = await get_content(uid, genre)

    if not content:
        return await c.answer("📭 Контент жоқ")

    # atomic update
    await db.db.execute("UPDATE users SET balance=balance-1 WHERE id=?", (uid,))
    await db.db.execute("INSERT INTO history VALUES(?,?)", (uid, content["id"]))
    await db.db.commit()

    await bot.send_video(uid, content["file_id"])
    await c.answer("✅ OK")

# ================= BONUS SYSTEM =================
@dp.message_handler(lambda m: m.text == "🎁 Бонус")
async def bonus(m):
    uid = m.from_user.id

    async with db.db.execute("SELECT last_bonus FROM users WHERE id=?", (uid,)) as c:
        u = await c.fetchone()

    now = datetime.now()

    if u and u["last_bonus"]:
        last = datetime.fromisoformat(u["last_bonus"])
        if now - last < timedelta(hours=24):
            return await m.answer("⏳ 24 сағат күтіңіз")

    await db.db.execute(
        "UPDATE users SET balance=balance+5, last_bonus=? WHERE id=?",
        (now.isoformat(), uid)
    )
    await db.db.commit()

    await m.answer("🎁 +5 баланс")

# ================= ADMIN PANEL =================
@dp.message_handler(lambda m: m.text == "⚙️ Admin")
async def admin(m):
    if m.from_user.id != ADMIN_ID:
        return

    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("➕ Add", callback_data="add"),
        types.InlineKeyboardButton("📊 Stats", callback_data="stats"),
        types.InlineKeyboardButton("🚫 Ban", callback_data="ban")
    )

    await m.answer("👑 ENTERPRISE ADMIN", reply_markup=kb)

# ================= STARTUP =================
async def on_startup(_):
    await db.connect()
    print("ENTERPRISE CORE V1 RUNNING")

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup)
