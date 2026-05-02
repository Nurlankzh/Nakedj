import asyncio
import aiosqlite
import logging
import os
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.utils import executor

# --- CONFIG ---
# Токенді осында жазыңыз немесе OS айнымалысынан алады
API_TOKEN = os.getenv('BOT_TOKEN', '6592332777:AAEGSbHq71W_X2DXwyXqrJcAqt-XSsHbqCk')
ADMIN_ID = 6303091468
DB_PATH = "bot_v14_pro.db"

# Жанрлар тізімі (Осы жерден өзгертуге болады)
GENRES = ["Кино", "Мультфильм", "Аниме", "Сериал", "Дорама", "Төбелес"]

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN, parse_mode="HTML")
dp = Dispatcher(bot, storage=MemoryStorage())

# --- FSM STATES ---
class AdminStates(StatesGroup):
    add_content_file = State()
    add_content_genre = State()
    ban_user = State()
    broadcast_msg = State()
    ai_generate = State()

# --- DATABASE MANAGER ---
class Database:
    def __init__(self):
        self.conn = None

    async def connect(self):  
        self.conn = await aiosqlite.connect(DB_PATH)  
        self.conn.row_factory = aiosqlite.Row  
        await self.conn.execute("PRAGMA journal_mode=WAL;")  
        await self.init_tables()  

    async def init_tables(self):  
        async with self.conn:  
            await self.conn.execute('''CREATE TABLE IF NOT EXISTS users (  
                id INTEGER PRIMARY KEY, is_banned INTEGER DEFAULT 0)''')  
            await self.conn.execute('''CREATE TABLE IF NOT EXISTS contents (  
                id INTEGER PRIMARY KEY AUTOINCREMENT, file_id TEXT,   
                type TEXT, genre TEXT, views INTEGER DEFAULT 0)''')  
        logging.info("База сәтті іске қосылды.")

db_manager = Database()

# --- KEYBOARDS ---

def get_admin_kb():
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("➕ Контент қосу", callback_data="adm_add"),
        types.InlineKeyboardButton("🤖 AI Генератор", callback_data="adm_ai")
    )
    kb.add(
        types.InlineKeyboardButton("📢 Рассылка", callback_data="adm_bc"),
        types.InlineKeyboardButton("📊 Статистика", callback_data="adm_stats")
    )
    kb.add(
        types.InlineKeyboardButton("🚫 Бан", callback_data="adm_ban"),
        types.InlineKeyboardButton("🔓 Разбан", callback_data="adm_unban")
    )
    return kb

def get_genre_kb():
    kb = types.InlineKeyboardMarkup(row_width=2)
    buttons = [types.InlineKeyboardButton(text=g, callback_data=f"setgenre_{g}") for g in GENRES]
    kb.add(*buttons)
    return kb

# --- HANDLERS ---

@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    async with db_manager.conn:
        await db_manager.conn.execute("INSERT OR IGNORE INTO users (id) VALUES (?)", (message.from_user.id,))
    await message.answer("Сәлем! Ботқа қош келдіңіз.")
    if message.from_user.id == ADMIN_ID:
        await message.answer("Сіз админсіз. Панельді ашу үшін: /admin")

@dp.message_handler(commands=['admin'], user_id=ADMIN_ID)
async def admin_panel(message: types.Message):
    await message.answer("👑 <b>Админ Панель V14 PRO</b>", reply_markup=get_admin_kb())

# --- 1. СТАТИСТИКА ---
@dp.callback_query_handler(lambda c: c.data == "adm_stats", user_id=ADMIN_ID)
async def adm_stats(callback: types.CallbackQuery):
    async with db_manager.conn.execute("SELECT COUNT() FROM users") as cur: 
        u_total = (await cur.fetchone())[0]
    async with db_manager.conn.execute("SELECT COUNT() FROM contents") as cur: 
        c_total = (await cur.fetchone())[0]
    
    txt = (f"📊 <b>Статистика:</b>\n\n"
           f"👥 Юзерлер: {u_total}\n"
           f"📦 Файлдар: {c_total}")
    await callback.message.edit_text(txt, reply_markup=get_admin_kb())

# --- 2. КОНТЕНТ ҚОСУ (Жанр таңдаумен) ---
@dp.callback_query_handler(lambda c: c.data == "adm_add", user_id=ADMIN_ID)
async def add_content_step1(callback: types.CallbackQuery):
    await AdminStates.add_content_file.set()
    await callback.message.answer("📹 Файлды жіберіңіз (Видео немесе Фото):")

@dp.message_handler(state=AdminStates.add_content_file, content_types=['video', 'photo'], user_id=ADMIN_ID)
async def add_content_step2(message: types.Message, state: FSMContext):
    fid = message.video.file_id if message.video else message.photo[-1].file_id
    ftype = "video" if message.video else "photo"
    await state.update_data(fid=fid, ftype=ftype)
    
    await AdminStates.add_content_genre.set()
    await message.answer("📝 Жанрды таңдаңыз:", reply_markup=get_genre_kb())

@dp.callback_query_handler(lambda c: c.data.startswith("setgenre_"), state=AdminStates.add_content_genre, user_id=ADMIN_ID)
async def add_content_final(callback: types.CallbackQuery, state: FSMContext):
    genre = callback.data.split("_")[1]
    data = await state.get_data()
    
    async with db_manager.conn:
        await db_manager.conn.execute(
            "INSERT INTO contents (file_id, type, genre) VALUES (?, ?, ?)",
            (data['fid'], data['ftype'], genre)
        )
    await state.finish()
    await callback.message.edit_text(f"✅ Сақталды!\nТүрі: {data['ftype']}\nЖанр: {genre}")

# --- 3. AI ГЕНЕРАТОР (Имитация) ---
@dp.callback_query_handler(lambda c: c.data == "adm_ai", user_id=ADMIN_ID)
async def ai_start(callback: types.CallbackQuery):
    await AdminStates.ai_generate.set()
    await callback.message.answer("🤖 AI-ға сұрақ қойыңыз немесе кино атын жазыңыз:")

@dp.message_handler(state=AdminStates.ai_generate, user_id=ADMIN_ID)
async def ai_process(message: types.Message, state: FSMContext):
    prompt = message.text
    # Бұл жерге Gemini немесе ChatGPT API қосуға болады
    ai_text = f"🤖 <b>AI Жауабы:</b>\n\n'{prompt}' туралы ақпарат талдануда... Бұл өте танымал жанр. Сипаттама: Бұл кино көрермендер арасында жоғары бағаланған."
    await message.answer(ai_text)
    await state.finish()

# --- 4. РАССЫЛКА ---
@dp.callback_query_handler(lambda c: c.data == "adm_bc", user_id=ADMIN_ID)
async def broadcast_start(callback: types.CallbackQuery):
    await AdminStates.broadcast_msg.set()
    await callback.message.answer("📢 Рассылка мәтінін немесе файлын жіберіңіз:")

@dp.message_handler(state=AdminStates.broadcast_msg, content_types=['any'], user_id=ADMIN_ID)
async def broadcast_exec(message: types.Message, state: FSMContext):
    async with db_manager.conn.execute("SELECT id FROM users") as cur:
        users = await cur.fetchall()
    await state.finish()
    
    count = 0
    for u in users:
        try:
            await message.copy_to(u['id'])
            count += 1
            await asyncio.sleep(0.05)
        except: pass
    await message.answer(f"✅ Рассылка аяқталды. {count} адамға жіберілді.")

# --- STARTUP ---
async def on_startup(_):
    await db_manager.connect()
    print("--- БОТ ҚОСЫЛДЫ (V14 PRO) ---")

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup)
