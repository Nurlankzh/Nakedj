import asyncio
import logging
import random
import time
import aiosqlite
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.dispatcher.middlewares import BaseMiddleware
from aiogram.dispatcher.handler import CancelHandler
from aiogram.utils import executor
from aiogram.utils.exceptions import Throttled

# --- CONFIG ---
API_TOKEN = "6592332777:AAEGSbHq71W_X2DXwyXqrJcAqt-XSsHbqCk"
ADMIN_ID = 6303091468
CHANNEL = "@QZSTOP"
DB = "enterprise.db"

GENRES = ["🎬 Кино", "😂 Прикол", "🔥 Тренд", "🎌 Аниме", "📺 Сериал"]

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN, parse_mode="HTML")
dp = Dispatcher(bot, storage=MemoryStorage())

# --- DB INIT ---
async def init_db():
    async with aiosqlite.connect(DB) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY,
            balance INTEGER DEFAULT 5,
            ref INTEGER,
            is_banned INTEGER DEFAULT 0,
            joined INTEGER
        )""")

        await db.execute("""
        CREATE TABLE IF NOT EXISTS content(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id TEXT,
            type TEXT,
            genre TEXT,
            views INTEGER DEFAULT 0
        )""")

        await db.commit()

# --- MIDDLEWARE ---
class AntiFlood(BaseMiddleware):
    async def on_process_message(self, message: types.Message, data):
        try:
            await dp.throttle("msg", rate=0.4)
        except Throttled:
            await message.answer("⚠️ Тез жазба")
            raise CancelHandler()

dp.middleware.setup(AntiFlood())

# --- STATES ---
class Admin(StatesGroup):
    add_file = State()
    add_genre = State()
    broadcast = State()
    ban = State()
    unban = State()

# --- UTILS ---
async def get_user(uid):
    async with aiosqlite.connect(DB) as db:
        async with db.execute("SELECT * FROM users WHERE id=?", (uid,)) as cur:
            return await cur.fetchone()

async def check_sub(uid):
    try:
        m = await bot.get_chat_member(CHANNEL, uid)
        return m.status != "left"
    except:
        return True

# --- KEYBOARDS ---
def main_kb(uid):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("🎬 Контент", "👤 Профиль")
    kb.add("💰 Баланс", "👥 Реферал")
    if uid == ADMIN_ID:
        kb.add("⚙️ Админ")
    return kb

def genre_kb():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    for g in GENRES:
        kb.add(g)
    kb.add("🔙 Артқа")
    return kb

def admin_kb():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("➕ Қосу", "📢 Рассылка")
    kb.add("🚫 Бан", "🔓 Разбан")
    kb.add("📊 Стат", "🔙 Артқа")
    return kb

# --- START ---
@dp.message_handler(commands=['start'])
async def start(m: types.Message):
    uid = m.from_user.id
    ref = m.get_args()

    async with aiosqlite.connect(DB) as db:
        await db.execute("INSERT OR IGNORE INTO users(id, joined) VALUES (?,?)",
                         (uid, int(time.time())))

        if ref.isdigit():
            await db.execute("UPDATE users SET balance = balance + 2 WHERE id=?", (ref,))

        await db.commit()

    await m.answer("👋 Қош келдің!", reply_markup=main_kb(uid))

# --- PROFILE ---
@dp.message_handler(lambda m: m.text == "👤 Профиль")
async def profile(m: types.Message):
    u = await get_user(m.from_user.id)
    await m.answer(f"🆔 {u[0]}\n💰 {u[1]} монета")

# --- BALANCE ---
@dp.message_handler(lambda m: m.text == "💰 Баланс")
async def balance(m: types.Message):
    u = await get_user(m.from_user.id)
    await m.answer(f"💰 {u[1]} монета")

# --- REF ---
@dp.message_handler(lambda m: m.text == "👥 Реферал")
async def ref(m: types.Message):
    me = await bot.get_me()
    link = f"https://t.me/{me.username}?start={m.from_user.id}"
    await m.answer(f"🔗 Сілтеме:\n{link}")

# --- CONTENT MENU ---
@dp.message_handler(lambda m: m.text == "🎬 Контент")
async def content(m: types.Message):
    if not await check_sub(m.from_user.id):
        return await m.answer(f"Алдымен каналға тіркел: {CHANNEL}")
    await m.answer("Жанр таңда:", reply_markup=genre_kb())

# --- SHOW CONTENT ---
@dp.message_handler(lambda m: m.text in GENRES)
async def show(m: types.Message):
    uid = m.from_user.id
    u = await get_user(uid)

    if u[1] <= 0:
        return await m.answer("Баланс жоқ")

    async with aiosqlite.connect(DB) as db:
        async with db.execute(
            "SELECT * FROM content WHERE genre=? ORDER BY RANDOM() LIMIT 1",
            (m.text,)
        ) as cur:
            c = await cur.fetchone()

        if not c:
            return await m.answer("Контент жоқ")

        await db.execute("UPDATE users SET balance=balance-1 WHERE id=?", (uid,))
        await db.execute("UPDATE content SET views=views+1 WHERE id=?", (c[0],))
        await db.commit()

    if c[2] == "video":
        await bot.send_video(uid, c[1])
    else:
        await bot.send_photo(uid, c[1])

# --- ADMIN PANEL ---
@dp.message_handler(lambda m: m.text == "⚙️ Админ", user_id=ADMIN_ID)
async def admin(m: types.Message):
    await m.answer("👑 Админ панель", reply_markup=admin_kb())

# --- ADD CONTENT ---
@dp.message_handler(lambda m: m.text == "➕ Қосу", user_id=ADMIN_ID)
async def add_start(m: types.Message):
    await Admin.add_file.set()
    await m.answer("Файл жібер")

@dp.message_handler(content_types=['video', 'photo'], state=Admin.add_file)
async def add_file(m: types.Message, state: FSMContext):
    fid = m.video.file_id if m.video else m.photo[-1].file_id
    ftype = "video" if m.video else "photo"

    await state.update_data(fid=fid, type=ftype)
    await Admin.add_genre.set()
    await m.answer("Жанр таңда:\n" + "\n".join(GENRES))

@dp.message_handler(state=Admin.add_genre)
async def add_done(m: types.Message, state: FSMContext):
    data = await state.get_data()

    async with aiosqlite.connect(DB) as db:
        await db.execute("INSERT INTO content(file_id,type,genre) VALUES (?,?,?)",
                         (data['fid'], data['type'], m.text))
        await db.commit()

    await m.answer("✅ Қосылды")
    await state.finish()

# --- BROADCAST ---
@dp.message_handler(lambda m: m.text == "📢 Рассылка", user_id=ADMIN_ID)
async def bc(m: types.Message):
    await Admin.broadcast.set()
    await m.answer("Текст жібер")

@dp.message_handler(state=Admin.broadcast)
async def bc_run(m: types.Message, state: FSMContext):
    async with aiosqlite.connect(DB) as db:
        async with db.execute("SELECT id FROM users") as cur:
            users = await cur.fetchall()

    for u in users:
        try:
            await bot.send_message(u[0], m.text)
            await asyncio.sleep(0.05)
        except:
            pass

    await m.answer("✅ Дайын")
    await state.finish()

# --- BAN ---
@dp.message_handler(lambda m: m.text == "🚫 Бан", user_id=ADMIN_ID)
async def ban(m: types.Message):
    await Admin.ban.set()
    await m.answer("ID жаз")

@dp.message_handler(state=Admin.ban)
async def ban_do(m: types.Message, state: FSMContext):
    async with aiosqlite.connect(DB) as db:
        await db.execute("UPDATE users SET is_banned=1 WHERE id=?", (m.text,))
        await db.commit()
    await m.answer("Бан берілді")
    await state.finish()

# --- UNBAN ---
@dp.message_handler(lambda m: m.text == "🔓 Разбан", user_id=ADMIN_ID)
async def unban(m: types.Message):
    await Admin.unban.set()
    await m.answer("ID жаз")

@dp.message_handler(state=Admin.unban)
async def unban_do(m: types.Message, state: FSMContext):
    async with aiosqlite.connect(DB) as db:
        await db.execute("UPDATE users SET is_banned=0 WHERE id=?", (m.text,))
        await db.commit()
    await m.answer("Разбан жасалды")
    await state.finish()

# --- STAT ---
@dp.message_handler(lambda m: m.text == "📊 Стат", user_id=ADMIN_ID)
async def stat(m: types.Message):
    async with aiosqlite.connect(DB) as db:
        async with db.execute("SELECT COUNT(*) FROM users") as cur:
            users = (await cur.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM content") as cur:
            cont = (await cur.fetchone())[0]

    await m.answer(f"👥 {users}\n🎬 {cont}")

# --- RUN ---
if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(init_db())
    executor.start_polling(dp, skip_updates=True)
