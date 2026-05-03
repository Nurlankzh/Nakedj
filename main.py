import asyncio
import logging
import time
import random
import aiosqlite
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.utils import executor

API_TOKEN = "6592332777:AAEGSbHq71W_X2DXwyXqrJcAqt-XSsHbqCk"
ADMIN_ID = 6303091468
CHANNEL = "@QZSTOP"
DB = "ultimate.db"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN, parse_mode="HTML")
dp = Dispatcher(bot, storage=MemoryStorage())

# --- ЖАНРЛАР ---
GENRES = {
    "🎬 Қазақша": 5,
    "🥵 Орысша": 4,
    "🤭 Балалар": 6,
    "😍 Американша": 3
}

# --- STATES ---
class Upload(StatesGroup):
    choose_genre = State()
    wait_video = State()

class Admin(StatesGroup):
    give_money = State()

# --- DB ---
async def init_db():
    async with aiosqlite.connect(DB) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY,
            balance INTEGER DEFAULT 10
        )
        """)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS content(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id TEXT,
            type TEXT,
            genre TEXT
        )
        """)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS user_videos(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            file_id TEXT,
            genre TEXT
        )
        """)
        await db.commit()

# --- KEYBOARDS ---
def main_kb(uid):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("🎬 Контент", "💰 Баланс")
    kb.add("👥 Реферал", "📤 Видео жіберу")
    if uid == ADMIN_ID:
        kb.add("⚙️ Админ")
    return kb

def genre_kb():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    for g in GENRES:
        kb.add(g)
    kb.add("🔙 Артқа")
    return kb

# --- START ---
@dp.message_handler(commands=['start'])
async def start(m: types.Message):
    async with aiosqlite.connect(DB) as db:
        await db.execute("INSERT OR IGNORE INTO users(id) VALUES(?)",(m.from_user.id,))
        await db.commit()

    await m.answer("👋 Қош келдің!", reply_markup=main_kb(m.from_user.id))

# --- BACK ---
@dp.message_handler(lambda m: m.text == "🔙 Артқа")
async def back(m: types.Message):
    await m.answer("🏠 Меню", reply_markup=main_kb(m.from_user.id))

# --- BALANCE ---
@dp.message_handler(lambda m: m.text == "💰 Баланс")
async def balance(m: types.Message):
    async with aiosqlite.connect(DB) as db:
        async with db.execute("SELECT balance FROM users WHERE id=?",(m.from_user.id,)) as cur:
            b = await cur.fetchone()
    await m.answer(f"💰 Баланс: {b[0]}")

# --- REF ---
@dp.message_handler(lambda m: m.text == "👥 Реферал")
async def ref(m: types.Message):
    me = await bot.get_me()
    link = f"https://t.me/{me.username}?start={m.from_user.id}"

    txt = f"""👥 Реферал жүйесі:

Дос шақырсаң → +6 монета аласың 💰

Сенің сілтемең:
{link}
"""
    await m.answer(txt)

# --- CONTENT ---
@dp.message_handler(lambda m: m.text == "🎬 Контент")
async def content(m: types.Message):
    await m.answer("Жанр таңда:", reply_markup=genre_kb())

@dp.message_handler(lambda m: m.text in GENRES)
async def show(m: types.Message):
    price = GENRES[m.text]

    async with aiosqlite.connect(DB) as db:
        async with db.execute("SELECT balance FROM users WHERE id=?",(m.from_user.id,)) as cur:
            b = await cur.fetchone()

        if b[0] < price:
            me = await bot.get_me()
            link = f"https://t.me/{me.username}?start={m.from_user.id}"
            return await m.answer(f"❌ Монета жетпейді!\nДос шақыр:\n{link}")

        async with db.execute("SELECT * FROM content WHERE genre=? ORDER BY RANDOM() LIMIT 1",(m.text,)) as cur:
            c = await cur.fetchone()

        if not c:
            return await m.answer("Контент жоқ")

        await db.execute("UPDATE users SET balance=balance-? WHERE id=?",(price,m.from_user.id))
        await db.commit()

    if c[2] == "video":
        await bot.send_video(m.chat.id, c[1])
    else:
        await bot.send_photo(m.chat.id, c[1])

# --- USER VIDEO UPLOAD ---
@dp.message_handler(lambda m: m.text == "📤 Видео жіберу")
async def upload_start(m: types.Message):
    await Upload.choose_genre.set()
    await m.answer("Қай жанр?", reply_markup=genre_kb())

@dp.message_handler(state=Upload.choose_genre)
async def choose_genre(m: types.Message, state: FSMContext):
    if m.text not in GENRES:
        return
    await state.update_data(genre=m.text)
    await Upload.wait_video.set()
    await m.answer("Видео жібер")

@dp.message_handler(content_types=['video'], state=Upload.wait_video)
async def upload_video(m: types.Message, state: FSMContext):
    data = await state.get_data()
    genre = data['genre']

    async with aiosqlite.connect(DB) as db:
        await db.execute("INSERT INTO user_videos(user_id,file_id,genre) VALUES(?,?,?)",
                         (m.from_user.id, m.video.file_id, genre))
        await db.commit()

    await bot.send_message(ADMIN_ID, f"📥 Жаңа видео\nЖанр: {genre}\nUser: {m.from_user.id}")
    await bot.send_video(ADMIN_ID, m.video.file_id)

    await m.answer("✅ Жіберілді! Тағы жібересің бе?")
    
# --- ADMIN PANEL ---
@dp.message_handler(lambda m: m.text == "⚙️ Админ", user_id=ADMIN_ID)
async def admin(m: types.Message):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("💸 Монета беру", "📊 Стат")
    kb.add("📥 Видео көру", "🔙 Артқа")
    await m.answer("👑 Админ панель", reply_markup=kb)

# --- GIVE MONEY ---
@dp.message_handler(lambda m: m.text == "💸 Монета беру", user_id=ADMIN_ID)
async def give_money(m: types.Message):
    await Admin.give_money.set()
    await m.answer("ID және сумма жаз: 123456 10")

@dp.message_handler(state=Admin.give_money)
async def give_money_do(m: types.Message, state: FSMContext):
    uid, amount = m.text.split()
    async with aiosqlite.connect(DB) as db:
        await db.execute("UPDATE users SET balance=balance+? WHERE id=?",(amount,uid))
        await db.commit()
    await m.answer("Берілді")
    await state.finish()

# --- ADMIN VIEW VIDEOS ---
@dp.message_handler(lambda m: m.text == "📥 Видео көру", user_id=ADMIN_ID)
async def view_videos(m: types.Message):
    async with aiosqlite.connect(DB) as db:
        async with db.execute("SELECT DISTINCT genre FROM user_videos") as cur:
            genres = await cur.fetchall()

    kb = types.InlineKeyboardMarkup()
    for g in genres:
        kb.add(types.InlineKeyboardButton(g[0], callback_data=f"view_{g[0]}"))

    await m.answer("Жанр таңда:", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data.startswith("view_"))
async def show_admin_videos(c: types.CallbackQuery):
    genre = c.data.split("_")[1]

    async with aiosqlite.connect(DB) as db:
        async with db.execute("SELECT * FROM user_videos WHERE genre=?",(genre,)) as cur:
            vids = await cur.fetchall()

    for v in vids:
        await bot.send_video(ADMIN_ID, v[2], caption=f"User: {v[1]}")

# --- RUN ---
if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(init_db())
    executor.start_polling(dp, skip_updates=True)
