import asyncio
import aiosqlite
import logging
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.utils import executor

# --- CONFIG ---
API_TOKEN = '6592332777:AAEGSbHq71W_X2DXwyXqrJcAqt-XSsHbqCk'
ADMIN_ID = 6303091468
CHANNEL_ID = "@QZSTOP" 
DB_PATH = "bot_ultimate.db"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN, parse_mode="HTML")
dp = Dispatcher(bot, storage=MemoryStorage())

# --- STATES ---
class AdminStates(StatesGroup):
    wait_broadcast = State()
    upload_content = State()
    give_bonus_id = State()
    give_bonus_amount = State()
    ban_user_id = State()

class UserStates(StatesGroup):
    send_to_mod = State()

# --- DATABASE INIT ---
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY, balance INTEGER DEFAULT 20, 
            referrer INTEGER, is_banned INTEGER DEFAULT 0,
            last_bonus TEXT, joined_at TEXT
        )''')
        await db.execute('''CREATE TABLE IF NOT EXISTS contents (
            id INTEGER PRIMARY KEY AUTOINCREMENT, file_id TEXT, 
            type TEXT, genre TEXT, views INTEGER DEFAULT 0
        )''')
        await db.execute('''CREATE TABLE IF NOT EXISTS history (
            user_id INTEGER, content_id INTEGER
        )''')
        await db.commit()

# --- BACKGROUND TASK: REMINDERS ---
async def reminder_scheduler():
    """Бонус алуды ұмытқандарға 24 сағат сайын ескерту жіберу"""
    while True:
        await asyncio.sleep(3600) # Әр сағат сайын тексереді
        now = datetime.now()
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT id, last_bonus FROM users WHERE is_banned=0") as cur:
                users = await cur.fetchall()
                for u_id, l_bonus in users:
                    if l_bonus:
                        lb_dt = datetime.strptime(l_bonus, "%Y-%m-%d %H:%M:%S")
                        if now >= lb_dt + timedelta(hours=24):
                            try:
                                await bot.send_message(u_id, "🎁 <b>Ескерту!</b> Сіздің күндік бонусаңыз дайын. Ботқа кіріп, бонусты алып кетіңіз!")
                            except: pass

# --- MIDDLEWARE: ACCESS CHECK ---
async def check_access(m: types.Message):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT is_banned FROM users WHERE id=?", (m.from_user.id,)) as cur:
            user = await cur.fetchone()
            if user and user[0] == 1:
                await m.answer("🚫 Сіз бұл ботта блокталғансыз!")
                return False
    try:
        member = await bot.get_chat_member(CHANNEL_ID, m.from_user.id)
        if member.status == "left":
            await m.answer(f"❌ Жалғастыру үшін каналға тіркеліңіз: {CHANNEL_ID}")
            return False
    except: return False
    return True

# --- KEYBOARDS ---
def main_kb(uid):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add("🎭 Жанр таңдау", "💰 Баланс")
    kb.add("👥 Реферал", "🎁 Тегін бонус")
    kb.add("📤 Модерацияға жіберу")
    if uid == ADMIN_ID: kb.add("⚙️ Админ Панель")
    return kb

def admin_kb():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add("📤 Контент жүктеу", "📢 Рассылка")
    kb.add("📈 Толық статистика", "🎁 Бонус беру")
    kb.add("🚫 Бан/Разбан", "🔙 Шығу")
    return kb

# --- HANDLERS ---

@dp.message_handler(commands=['start'], state="*")
async def start(message: types.Message, state: FSMContext):
    await state.finish()
    uid = message.from_user.id
    args = message.get_args()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT id FROM users WHERE id=?", (uid,)) as cur:
            if not await cur.fetchone():
                ref_id = int(args) if args and args.isdigit() else None
                await db.execute("INSERT INTO users (id, referrer, joined_at) VALUES (?, ?, ?)", (uid, ref_id, now_str))
                if ref_id and ref_id != uid:
                    await db.execute("UPDATE users SET balance = balance + 15 WHERE id=?", (ref_id,))
                    try: await bot.send_message(ref_id, "🎁 Досыңыз қосылды! +15 бонус берілді.")
                    except: pass
                await db.commit()
    await message.answer("🔥 Қош келдіңіз! Контент көру үшін төмендегі батырмаларды қолданыңыз.", reply_markup=main_kb(uid))

# --- 1. DAILY BONUS ---
@dp.message_handler(lambda m: m.text == "🎁 Тегін бонус")
async def get_daily_bonus(message: types.Message):
    if not await check_access(message): return
    uid = message.from_user.id
    now = datetime.now()

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT last_bonus FROM users WHERE id=?", (uid,)) as cur:
            row = await cur.fetchone()
            l_bonus = row[0] if row else None

        if l_bonus:
            lb_dt = datetime.strptime(l_bonus, "%Y-%m-%d %H:%M:%S")
            if now < lb_dt + timedelta(hours=24):
                diff = (lb_dt + timedelta(hours=24)) - now
                return await message.answer(f"⏳ Келесі бонусқа дейін: {diff.seconds // 3600} сағат қалды.")

        await db.execute("UPDATE users SET balance = balance + 10, last_bonus = ? WHERE id=?", 
                         (now.strftime("%Y-%m-%d %H:%M:%S"), uid))
        await db.commit()
    await message.answer("🎁 Құттықтаймыз! Күндік бонус +10 берілді.")

# --- 2. ADMIN: ADVANCED STATS ---
@dp.message_handler(lambda m: m.text == "📈 Толық статистика" and m.from_user.id == ADMIN_ID)
async def adv_stats(message: types.Message):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT genre, COUNT(*) FROM contents GROUP BY genre ORDER BY COUNT(*) DESC LIMIT 1") as cur:
            top_g = await cur.fetchone()
            g_txt = top_g[0] if top_g else "Жоқ"
        
        async with db.execute("SELECT id, balance FROM users ORDER BY balance DESC LIMIT 3") as cur:
            top_u = await cur.fetchall()
            leaderboard = "\n".join([f"💎 ID: <code>{u[0]}</code> | {u[1]} бонус" for u in top_u])
            
        async with db.execute("SELECT COUNT(*) FROM users") as cur: total_u = (await cur.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM contents") as cur: total_c = (await cur.fetchone())[0]

    res = (f"📊 <b>Кеңейтілген статистика:</b>\n\n"
           f"👥 Жалпы юзерлер: {total_u}\n"
           f"📦 Жалпы контент: {total_c}\n"
           f"🔥 Танымал жанр: {g_txt}\n\n"
           f"🏆 <b>Үздік қолданушылар:</b>\n{leaderboard}")
    await message.answer(res)

# --- 3. CONTENT VIEW & CYCLE ---
@dp.callback_query_handler(lambda c: c.data.startswith('v_'))
async def view_engine(callback: types.CallbackQuery):
    uid = callback.from_user.id
    genre_map = {"kaz": "Қазақша", "rus": "Русский", "kids": "Детский"}
    g = genre_map[callback.data.split('_')[1]]
    
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT balance FROM users WHERE id=?", (uid,)) as cur:
            row = await cur.fetchone()
            bal = row[0] if row else 0
        
        if bal < 3: return await callback.message.answer("💰 Баланс жетпейді (мин 3 бонус).")

        query = "SELECT id, file_id, type FROM contents WHERE genre=? AND id NOT IN (SELECT content_id FROM history WHERE user_id=?) ORDER BY RANDOM() LIMIT 1"
        async with db.execute(query, (g, uid)) as cur:
            item = await cur.fetchone()

        if not item:
            await db.execute("DELETE FROM history WHERE user_id=? AND content_id IN (SELECT id FROM contents WHERE genre=?)", (uid, g))
            await db.commit()
            return await callback.answer("🔄 Бұл жанр бітті. Басынан бастап көре аласыз!", show_alert=True)

        cid, fid, ftype = item
        cost = 3 if ftype == "photo" else 2 # Фото -3, Видео -2
        await db.execute("UPDATE users SET balance = balance - ?, last_bonus = last_bonus WHERE id=?", (cost, uid))
        await db.execute("INSERT INTO history (user_id, content_id) VALUES (?, ?)", (uid, cid))
        await db.execute("UPDATE contents SET views = views + 1 WHERE id=?", (cid,))
        await db.commit()

        cap = f"🎭 Жанр: {g}\n💰 Жұмсалды: {cost} бонус"
        if ftype == "video": await bot.send_video(uid, fid, caption=cap, protect_content=True)
        else: await bot.send_photo(uid, fid, caption=cap, protect_content=True)
    await callback.answer()

# --- 4. ADMIN: BAN/UNBAN (FIXED) ---
@dp.message_handler(lambda m: m.text == "🚫 Бан/Разбан" and m.from_user.id == ADMIN_ID)
async def ban_mode(message: types.Message):
    await AdminStates.ban_user_id.set()
    await message.answer("Пайдаланушы ID-ін енгізіңіз:")

@dp.message_handler(state=AdminStates.ban_user_id)
async def ban_id_step(message: types.Message, state: FSMContext):
    if not message.text.isdigit(): return await message.answer("Тек сан жазыңыз.")
    kb = types.InlineKeyboardMarkup().add(
        types.InlineKeyboardButton("🚫 БАН", callback_data=f"b_1_{message.text}"),
        types.InlineKeyboardButton("✅ РАЗБАН", callback_data=f"b_0_{message.text}")
    )
    await message.answer(f"ID {message.text} үшін әрекет:", reply_markup=kb)
    await state.finish()

@dp.callback_query_handler(lambda c: c.data.startswith('b_') and c.from_user.id == ADMIN_ID)
async def ban_exec(callback: types.CallbackQuery):
    _, status, tid = callback.data.split('_')
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET is_banned=? WHERE id=?", (status, tid))
        await db.commit()
    await callback.message.edit_text(f"✅ Дайын! ID {tid} күйі өзгертілді.")

# --- 5. ADMIN: CONTENT UPLOAD ---
@dp.message_handler(lambda m: m.text == "📤 Контент жүктеу" and m.from_user.id == ADMIN_ID)
async def upload_init(message: types.Message):
    kb = types.InlineKeyboardMarkup().add(
        types.InlineKeyboardButton("🇰🇿 Қазақша", callback_data="u_kaz"),
        types.InlineKeyboardButton("🇷🇺 Русский", callback_data="u_rus"),
        types.InlineKeyboardButton("👶 Детский", callback_data="u_kids")
    )
    await message.answer("Жанр таңдаңыз:", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data.startswith('u_'), user_id=ADMIN_ID)
async def upload_genre(callback: types.CallbackQuery, state: FSMContext):
    g = {"u_kaz": "Қазақша", "u_rus": "Русский", "u_kids": "Детский"}[callback.data]
    await state.update_data(current_g=g)
    await AdminStates.upload_content.set()
    await callback.message.answer(f"[{g}] үшін файлдарды жіберіңіз. Тоқтату: /stop")

@dp.message_handler(state=AdminStates.upload_content, content_types=['photo', 'video'])
async def upload_bulk(message: types.Message, state: FSMContext):
    data = await state.get_data()
    fid = message.video.file_id if message.video else message.photo[-1].file_id
    ftype = "video" if message.video else "photo"
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO contents (file_id, type, genre) VALUES (?, ?, ?)", (fid, ftype, data['current_g']))
        await db.commit()

@dp.message_handler(state=AdminStates.upload_content, commands=['stop'])
async def upload_stop(message: types.Message, state: FSMContext):
    await state.finish()
    await message.answer("✅ Жүктеу аяқталды.", reply_markup=admin_kb())

# --- 6. USER HANDLERS (MODERATION, BAL, REF) ---
@dp.message_handler(lambda m: m.text == "📤 Модерацияға жіберу")
async def mod_start(message: types.Message):
    await UserStates.send_to_mod.set()
    await message.answer("Контентті жіберіңіз (Видео/Фото):")

@dp.message_handler(state=UserStates.send_to_mod, content_types=['photo', 'video'])
async def mod_process(message: types.Message, state: FSMContext):
    kb = types.InlineKeyboardMarkup().add(
        types.InlineKeyboardButton("✅ Қабылдау", callback_data=f"m_a_{message.from_user.id}"),
        types.InlineKeyboardButton("❌ Бас тарту", callback_data=f"m_d_{message.from_user.id}")
    )
    await bot.forward_message(ADMIN_ID, message.chat.id, message.message_id)
    await bot.send_message(ADMIN_ID, f"Юзер ID: {message.from_user.id}", reply_markup=kb)
    await message.answer("Жіберілді! Админ тексеріп, бонус береді.")
    await state.finish()

@dp.callback_query_handler(lambda c: c.data.startswith('m_') and c.from_user.id == ADMIN_ID)
async def mod_decision(callback: types.CallbackQuery):
    _, act, tid = callback.data.split('_')
    if act == 'a':
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE users SET balance = balance + 20 WHERE id=?", (tid,))
            await db.commit()
        await bot.send_message(tid, "✅ Құттықтаймыз! Контентіңіз қабылданды. +20 бонус!")
    else:
        await bot.send_message(tid, "❌ Өкінішке орай, контентіңіз модерациядан өтпеді.")
    await callback.message.delete()

@dp.message_handler(lambda m: m.text == "💰 Баланс")
async def check_bal(message: types.Message):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT balance FROM users WHERE id=?", (message.from_user.id,)) as cur:
            row = await cur.fetchone()
            b = row[0] if row else 0
    await message.answer(f"💰 Сіздің балансыңыз: <b>{b} бонус</b>")

@dp.message_handler(lambda m: m.text == "👥 Реферал")
async def ref_link(message: types.Message):
    me = await bot.get_me()
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM users WHERE referrer=?", (message.from_user.id,)) as cur:
            c = (await cur.fetchone())[0]
    link = f"https://t.me/{me.username}?start={message.from_user.id}"
    await message.answer(f"👥 Шақырған достар: {c}\n🎁 Әр дос үшін: 15 бонус\n\nСілтемеңіз: <code>{link}</code>")

# --- ADMIN PANEL & MISC ---
@dp.message_handler(lambda m: m.text == "⚙️ Админ Панель" and m.from_user.id == ADMIN_ID)
async def admin_p(message: types.Message):
    await message.answer("Админ панелі:", reply_markup=admin_kb())

@dp.message_handler(lambda m: m.text == "🔙 Шығу")
async def back_home(message: types.Message):
    await message.answer("Бас мәзір", reply_markup=main_kb(message.from_user.id))

# --- STARTUP ---
async def on_startup(_):
    await init_db()
    asyncio.create_task(reminder_scheduler())

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup)
