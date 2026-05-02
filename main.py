import asyncio
import aiosqlite
import logging
import time
from aiogram import Bot, Dispatcher, types, executor
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup

# --- CONFIG ---
API_TOKEN = '6592332777:AAEGSbHq71W_X2DXwyXqrJcAqt-XSsHbqCk'
ADMIN_ID = 6303091468
CHANNEL_ID = "@QZSTOP" 
DB_PATH = "bot_pro_v2.db"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# --- STATES ---
class AdminStates(StatesGroup):
    wait_broadcast = State()
    wait_bonus_id = State()
    wait_bonus_amount = State()
    upload_content = State() # Контент жүктеу
    set_genre = State()      # Жанр таңдау

class UserStates(StatesGroup):
    choosing_genre = State()

# --- DATABASE INIT ---
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        # Users: balance, vip, referrer_id
        await db.execute('''CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY, balance INTEGER DEFAULT 0, 
            referrer INTEGER, is_vip INTEGER DEFAULT 0, 
            is_banned INTEGER DEFAULT 0, joined_at INTEGER
        )''')
        # Content: жанр және VIP статусымен
        await db.execute('''CREATE TABLE IF NOT EXISTS contents (
            id INTEGER PRIMARY KEY AUTOINCREMENT, file_id TEXT, 
            type TEXT, genre TEXT, is_premium INTEGER DEFAULT 0
        )''')
        await db.commit()

# --- KEYBOARDS ---
def main_kb(uid):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add("🎭 Жанр таңдау", "💎 VIP Сатып алу")
    kb.add("👥 Реферал", "💰 Баланс")
    if uid == ADMIN_ID:
        kb.add("⚙️ Админ Панель")
    return kb

def admin_kb():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add("📤 Контент жүктеу", "📢 Рассылка")
    kb.add("📊 Статистика", "🎁 Бонус беру")
    kb.add("🔙 Шығу")
    return kb

def genre_kb():
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(types.InlineKeyboardButton("🇰🇿 Қазақша", callback_data="genre_kaz"),
           types.InlineKeyboardButton("🇷🇺 Русский", callback_data="genre_rus"))
    return kb

# --- REFERRAL SYSTEM LOGIC ---
async def add_user(uid, ref_id=None):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT id FROM users WHERE id=?", (uid,)) as cur:
            if await cur.fetchone(): return # Бар болса тиіспейміз
        
        await db.execute("INSERT INTO users (id, referrer, joined_at) VALUES (?, ?, ?)", 
                         (uid, ref_id, int(time.time())))
        
        if ref_id and ref_id != uid:
            # Реферал үшін бонус (мысалы 10 бонус)
            await db.execute("UPDATE users SET balance = balance + 10 WHERE id=?", (ref_id,))
            try:
                await bot.send_message(ref_id, "🎁 Сіздің сілтемеңізбен жаңа адам тіркелді! +10 бонус берілді.")
            except: pass
        await db.commit()

# --- COMMANDS ---
@dp.message_handler(commands=['start'], state="*")
async def start(message: types.Message, state: FSMContext):
    await state.finish()
    args = message.get_args()
    ref_id = int(args) if args.isdigit() else None
    await add_user(message.from_user.id, ref_id)
    
    await message.answer("🔥 Ең үздік контент ботына қош келдіңіз!", reply_markup=main_kb(message.from_user.id))

# --- ADMIN: CONTENT UPLOAD SYSTEM ---
@dp.message_handler(lambda m: m.text == "📤 Контент жүктеу" and m.from_user.id == ADMIN_ID)
async def admin_upload_start(message: types.Message):
    await AdminStates.upload_content.set()
    await message.answer("Маған фото немесе видео жіберіңіз (бір файл):")

@dp.message_handler(state=AdminStates.upload_content, content_types=['photo', 'video'])
async def admin_upload_process(message: types.Message, state: FSMContext):
    f_id = message.video.file_id if message.video else message.photo[-1].file_id
    f_type = "video" if message.video else "photo"
    await state.update_data(f_id=f_id, f_type=f_type)
    
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("Қазақша", callback_data="set_kaz"),
           types.InlineKeyboardButton("Русский", callback_data="set_rus"))
    
    await AdminStates.set_genre.set()
    await message.answer("Бұл қай жанрға жатады?", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data.startswith('set_'), state=AdminStates.set_genre)
async def admin_upload_final(callback: types.CallbackQuery, state: FSMContext):
    genre = "Қазақша" if callback.data == "set_kaz" else "Русский"
    data = await state.get_data()
    
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO contents (file_id, type, genre) VALUES (?, ?, ?)",
                         (data['f_id'], data['f_type'], genre))
        await db.commit()
    
    await callback.message.answer(f"✅ Сәтті сақталды! Жанр: {genre}")
    await state.finish()

# --- USER: VIEW CONTENT BY GENRE ---
@dp.message_handler(lambda m: m.text == "🎭 Жанр таңдау")
async def user_genre_select(message: types.Message):
    await message.answer("Қай тілдегі контентті көргіңіз келеді?", reply_markup=genre_kb())

@dp.callback_query_handler(lambda c: c.data.startswith('genre_'))
async def user_show_content(callback: types.CallbackQuery):
    genre = "Қазақша" if callback.data == "genre_kaz" else "Русский"
    
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT file_id, type FROM contents WHERE genre=? ORDER BY RANDOM() LIMIT 1", (genre,)) as cur:
            item = await cur.fetchone()
            
    if not item:
        return await callback.answer("Бұл жанрда әзірге ештеңе жоқ 😔")
    
    if item[1] == "video":
        await callback.message.answer_video(item[0], caption=f"Жанр: {genre}")
    else:
        await callback.message.answer_photo(item[0], caption=f"Жанр: {genre}")
    await callback.answer()

# --- REFERRAL & BALANCE ---
@dp.message_handler(lambda m: m.text == "👥 Реферал")
async def referral_sys(message: types.Message):
    bot_name = (await bot.get_me()).username
    ref_link = f"https://t.me/{bot_name}?start={message.from_user.id}"
    await message.answer(f"🎁 Досыңды шақырып 10 бонус ал!\n\nСенің сілтемең:\n{ref_link}")

@dp.message_handler(lambda m: m.text == "💰 Баланс")
async def check_balance(message: types.Message):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT balance FROM users WHERE id=?", (message.from_user.id,)) as cur:
            row = await cur.fetchone()
    await message.answer(f"Сіздің балансыңыз: {row[0] if row else 0} бонус 💰")

# --- ADMIN: STATISTICS ---
@dp.message_handler(lambda m: m.text == "📊 Статистика" and m.from_user.id == ADMIN_ID)
async def admin_stats(message: types.Message):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM users") as cur:
            total_users = (await cur.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM contents") as cur:
            total_content = (await cur.fetchone())[0]
            
    await message.answer(f"📊 Бот статистикасы:\n\n👥 Пайдаланушылар: {total_users}\n🎬 Барлық контент: {total_content}")

# --- ADMIN: BROADCAST ---
@dp.message_handler(lambda m: m.text == "📢 Рассылка" and m.from_user.id == ADMIN_ID)
async def broadcast_init(message: types.Message):
    await AdminStates.wait_broadcast.set()
    await message.answer("Хабарламаны жіберіңіз:")

@dp.message_handler(state=AdminStates.wait_broadcast, content_types=['any'])
async def broadcast_run(message: types.Message, state: FSMContext):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT id FROM users") as cur:
            users = await cur.fetchall()
    
    count = 0
    for u in users:
        try:
            await message.copy_to(u[0])
            count += 1
            await asyncio.sleep(0.05) # Rate-limit protection
        except: pass
    
    await message.answer(f"Дайын! {count} адамға жіберілді.")
    await state.finish()

# --- RUN ---
if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True, on_startup=lambda _: init_db())
