import asyncio
import aiosqlite
import logging
import os
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.utils import executor

--- CONFIG ---

API_TOKEN = os.getenv('BOT_TOKEN', '6592332777:AAEGSbHq71W_X2DXwyXqrJcAqt-XSsHbqCk')
ADMIN_ID = 6303091468
CHANNEL_ID = "@QZSTOP"
DB_PATH = "bot_v14_pro.db"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN, parse_mode="HTML")
dp = Dispatcher(bot, storage=MemoryStorage())

--- FSM STATES ---

class AdminStates(StatesGroup):
add_content_file = State()
add_content_genre = State()
ban_user = State()
unban_user = State()
broadcast_msg = State()
search_user = State()

--- DATABASE MANAGER ---

class Database:
def init(self):
self.conn = None

async def connect(self):  
    self.conn = await aiosqlite.connect(DB_PATH)  
    self.conn.row_factory = aiosqlite.Row  
    await self.conn.execute("PRAGMA journal_mode=WAL;")  
    await self.init_tables()  

async def init_tables(self):  
    async with self.conn:  
        await self.conn.execute('''CREATE TABLE IF NOT EXISTS users (  
            id INTEGER PRIMARY KEY, balance INTEGER DEFAULT 20,   
            is_banned INTEGER DEFAULT 0, joined_at TEXT)''')  
        await self.conn.execute('''CREATE TABLE IF NOT EXISTS contents (  
            id INTEGER PRIMARY KEY AUTOINCREMENT, file_id TEXT,   
            type TEXT, genre TEXT, views INTEGER DEFAULT 0)''')  
        await self.conn.execute('''CREATE TABLE IF NOT EXISTS history (  
            user_id INTEGER, content_id INTEGER,  
            PRIMARY KEY (user_id, content_id))''')  
    logging.info("PRO Database Loaded.")

db_manager = Database()

--- ADMIN PANEL KEYBOARD ---

def get_admin_kb():
kb = types.InlineKeyboardMarkup(row_width=2)
kb.add(types.InlineKeyboardButton("➕ Контент қосу", callback_data="adm_add"),
types.InlineKeyboardButton("📢 Рассылка", callback_data="adm_bc"))
kb.add(types.InlineKeyboardButton("🚫 Бан", callback_data="adm_ban"),
types.InlineKeyboardButton("🔓 Разбан", callback_data="adm_unban"))
kb.add(types.InlineKeyboardButton("🔍 Юзер іздеу", callback_data="adm_search"),
types.InlineKeyboardButton("📊 Статистика", callback_data="adm_stats"))
return kb

--- ADMIN HANDLERS ---

@dp.message_handler(lambda m: m.text == "⚙️ Админ Панель" and m.from_user.id == ADMIN_ID)
async def admin_entry(message: types.Message):
await message.answer("👑 <b>PRO Admin Panel V14</b>\nБасқару жүйесіне қош келдіңіз!", reply_markup=get_admin_kb())

1. 📊 STATISTICS (FULL LOGIC)

@dp.callback_query_handler(lambda c: c.data == "adm_stats", user_id=ADMIN_ID)
async def adm_stats(callback: types.CallbackQuery):
async with db_manager.conn.execute("SELECT COUNT() FROM users") as cur: u_total = (await cur.fetchone())[0]
async with db_manager.conn.execute("SELECT COUNT() FROM users WHERE is_banned=1") as cur: u_banned = (await cur.fetchone())[0]
async with db_manager.conn.execute("SELECT SUM(views) FROM contents") as cur: total_views = (await cur.fetchone())[0] or 0
async with db_manager.conn.execute("SELECT genre, COUNT(*) as c FROM contents GROUP BY genre") as cur:
genres = await cur.fetchall()
g_txt = "\n".join([f"🔹 {g['genre']}: {g['c']} файл" for g in genres])

txt = (f"📊 <b>Толық статистика:</b>\n\n"  
       f"👥 Юзерлер: {u_total} (🚫 Банда: {u_banned})\n"  
       f"👁 Жалпы көрілім: {total_views}\n\n"  
       f"📦 База құрамы:\n{g_txt if g_txt else 'Бос'}")  
await callback.message.edit_text(txt, reply_markup=get_admin_kb())

2. 📢 BROADCAST (MESSAGING SYSTEM)

@dp.callback_query_handler(lambda c: c.data == "adm_bc", user_id=ADMIN_ID)
async def adm_bc_start(callback: types.CallbackQuery):
await AdminStates.broadcast_msg.set()
await callback.message.answer("📢 Рассылка жасау үшін хабарлама жіберіңіз (мәтін, фото немесе видео):")

@dp.message_handler(state=AdminStates.broadcast_msg, content_types=['text', 'photo', 'video'], user_id=ADMIN_ID)
async def adm_bc_execute(message: types.Message, state: FSMContext):
async with db_manager.conn.execute("SELECT id FROM users") as cur: users = await cur.fetchall()
await state.finish()

count, errors = 0, 0  
status_msg = await message.answer(f"⏳ Рассылка басталды... (0/{len(users)})")  

for u in users:  
    try:  
        await message.copy_to(u['id'])  
        count += 1  
        if count % 20 == 0: await status_msg.edit_text(f"⏳ Жіберілуде... ({count}/{len(users)})")  
    except: errors += 1  
    await asyncio.sleep(0.05) # Anti-flood  

await message.answer(f"✅ <b>Рассылка аяқталды!</b>\n📥 Сәтті: {count}\n❌ Қате: {errors}")

3. 🚫 BAN SYSTEM (LOGIC ADDED)

@dp.callback_query_handler(lambda c: c.data == "adm_ban", user_id=ADMIN_ID)
async def adm_ban_start(callback: types.CallbackQuery):
await AdminStates.ban_user.set()
await callback.message.answer("🚫 Банға салатын қолданушының ID-ін жіберіңіз:")

@dp.message_handler(state=AdminStates.ban_user, user_id=ADMIN_ID)
async def adm_ban_exec(message: types.Message, state: FSMContext):
if not message.text.isdigit(): return await message.answer("❌ ID тек сандардан тұруы керек!")
uid = int(message.text)
async with db_manager.conn:
await db_manager.conn.execute("UPDATE users SET is_banned = 1 WHERE id = ?", (uid,))
await state.finish()
await message.answer(f"✅ Юзер {uid} бұғатталды.")

4. ➕ ADD CONTENT (STABLE)

@dp.callback_query_handler(lambda c: c.data == "adm_add", user_id=ADMIN_ID)
async def adm_add_start(callback: types.CallbackQuery):
await AdminStates.add_content_file.set()
await callback.message.answer("📹 Файл жіберіңіз (Video/Photo):")

@dp.message_handler(state=AdminStates.add_content_file, content_types=['video', 'photo'], user_id=ADMIN_ID)
async def adm_add_file(message: types.Message, state: FSMContext):
fid = message.video.file_id if message.video else message.photo[-1].file_id
ftype = "video" if message.video else "photo"
await state.update_data(fid=fid, ftype=ftype)
await AdminStates.add_content_genre.set()
await message.answer("📝 Жанрын енгізіңіз:")

@dp.message_handler(state=AdminStates.add_content_genre, user_id=ADMIN_ID)
async def adm_add_genre(message: types.Message, state: FSMContext):
data = await state.get_data()
async with db_manager.conn:
await db_manager.conn.execute("INSERT INTO contents (file_id, type, genre) VALUES (?, ?, ?)",
(data['fid'], data['ftype'], message.text))
await state.finish()
await message.answer("✅ Контент сақталды!")

--- STARTUP ---

async def on_startup(_):
await db_manager.connect()
print("PRO ADMIN PANEL V14 ACTIVE")

if name == "main":
executor.start_polling(dp, skip_updates=True, on_startup=on_startup)
