import asyncio
import logging
import time
import aiosqlite
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.utils import executor

# --- CONFIG ---
API_TOKEN = "6592332777:AAEGSbHq71W_X2DXwyXqrJcAqt-XSsHbqCk"
ADMIN_ID = 6303091468
CHANNEL_URL = "https://t.me/QZQCONTENT"
CHANNEL_ID = "@QZQCONTENT" # Каналға ботты админ қылып қосу керек
DB = "main_bot.db"

# Жанрлардың жаңа атаулары мен бағалары
GENRES_CONFIG = {
    "🎬 Қазақша": {"price": 5},
    "🥵 Орысша": {"price": 4},
    "🤭 Балалар": {"price": 6},
    "😍 Американша": {"price": 3}
}
GENRES = list(GENRES_CONFIG.keys())

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN, parse_mode="HTML")
dp = Dispatcher(bot, storage=MemoryStorage())

# --- STATES ---
class AdminStates(StatesGroup):
    add_content_genre = State()
    add_content_files = State()
    give_coins_id = State()
    give_coins_amount = State()
    broadcast = State()

class UserStates(StatesGroup):
    upload_genre = State()
    upload_video = State()

# --- DATABASE ---
async def init_db():
    async with aiosqlite.connect(DB) as db:
        await db.execute("""CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY, balance INTEGER DEFAULT 10, 
            last_active INTEGER, joined INTEGER)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS content(
            id INTEGER PRIMARY KEY AUTOINCREMENT, file_id TEXT, 
            type TEXT, genre TEXT)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS user_submissions(
            id INTEGER PRIMARY KEY AUTOINCREMENT, file_id TEXT, 
            genre TEXT, user_id INTEGER)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS viewed_history(
            user_id INTEGER, content_id INTEGER)""")
        await db.commit()

# --- KEYBOARDS ---
def main_kb(uid):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("🎬 Кино көру", "➕ Контент қосу")
    kb.row("👥 Реферал", "💰 Монета сатып алу")
    if uid == ADMIN_ID: kb.row("⚙️ Админ Панель")
    return kb

def genre_kb():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    for g in GENRES: kb.add(g)
    kb.add("🔙 Артқа")
    return kb

def sub_kb():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("Тіркелу", url=CHANNEL_URL))
    return kb

# --- CHECK SUBSCRIPTION ---
async def check_sub(uid):
    try:
        member = await bot.get_chat_member(CHANNEL_ID, uid)
        return member.status != "left"
    except: return True

# --- START ---
@dp.message_handler(commands=['start'], state="*")
async def start_cmd(m: types.Message, state: FSMContext):
    await state.finish()
    uid = m.from_user.id
    ref = m.get_args()
    
    if not await check_sub(uid):
        return await m.answer(f"⚠️ Жалғастыру үшін каналға тіркеліңіз!\nШығып кетсеңіз, қайта тіркелуіңіз керек.", reply_markup=sub_kb())

    async with aiosqlite.connect(DB) as db:
        user = await (await db.execute("SELECT id FROM users WHERE id=?", (uid,))).fetchone()
        if not user:
            await db.execute("INSERT INTO users(id, balance, last_active, joined) VALUES (?,?,?,?)", 
                             (uid, 10, int(time.time()), int(time.time())))
            if ref and ref.isdigit() and int(ref) != uid:
                await db.execute("UPDATE users SET balance = balance + 6 WHERE id=?", (ref,))
                try: await bot.send_message(ref, "🎁 Досыңыз келді! Сыйлыққа 6 монета берілді.")
                except: pass
        await db.commit()
    
    await m.answer("🤩 Сәлем! Керемет видеолар әлеміне қош келдіңіз!", reply_markup=main_kb(uid))

# --- BACK BUTTON ---
@dp.message_handler(lambda m: m.text == "🔙 Артқа", state="*")
async def back_handler(m: types.Message, state: FSMContext):
    await state.finish()
    await m.answer("Бас мәзірге оралдыңыз:", reply_markup=main_kb(m.from_user.id))

# --- VIEW CONTENT ---
@dp.message_handler(lambda m: m.text == "🎬 Кино көру")
async def content_genres(m: types.Message):
    if not await check_sub(m.from_user.id):
        return await m.answer("❌ Каналдан шығып кетіпсіз, қайта тіркеліңіз!", reply_markup=sub_kb())
    await m.answer("Қай жанрды көргіңіз келеді?", reply_markup=genre_kb())

@dp.message_handler(lambda m: m.text in GENRES)
async def show_video(m: types.Message):
    uid = m.from_user.id
    genre = m.text
    price = GENRES_CONFIG[genre]['price']
    
    async with aiosqlite.connect(DB) as db:
        u = await (await db.execute("SELECT balance FROM users WHERE id=?", (uid,))).fetchone()
        if u[0] < price:
            me = await bot.get_me()
            ref_link = f"https://t.me/{me.username}?start={uid}"
            return await m.answer(f"⚠️ <b>Монетаңыз жеткіліксіз!</b>\n\n{genre} үшін {price} монета қажет.\nБаланс: {u[0]}\n\nДос шақырып 6 монета алыңыз немесе сатып алыңыз.\n🔗 Сілтеме: <code>{ref_link}</code>")

        # Көрмеген видеосын іздеу
        res = await db.execute("""SELECT id, file_id FROM content WHERE genre=? 
                                  AND id NOT IN (SELECT content_id FROM viewed_history WHERE user_id=?) 
                                  ORDER BY id LIMIT 1""", (genre, uid))
        video = await res.fetchone()
        
        if not video: # Барлығын көріп қойса басынан бастайды
            await db.execute("DELETE FROM viewed_history WHERE user_id=?", (uid,))
            res = await db.execute("SELECT id, file_id FROM content WHERE genre=? ORDER BY id LIMIT 1", (genre,))
            video = await res.fetchone()

        if video:
            await db.execute("UPDATE users SET balance = balance - ?, last_active = ? WHERE id=?", (price, int(time.time()), uid))
            await db.execute("INSERT INTO viewed_history VALUES (?,?)", (uid, video[0]))
            await db.commit()
            
            sent = await bot.send_video(uid, video[1], caption=f"✅ Көру құны: {price} монета")
            # 30 минуттан соң өшіру
            asyncio.create_task(delete_after(uid, sent.message_id, 1800))
        else:
            await m.answer("Бұл жанрда әзірге видео жоқ.")

async def delete_after(chat_id, mid, delay):
    await asyncio.sleep(delay)
    try: await bot.delete_message(chat_id, mid)
    except: pass

# --- USER UPLOAD ---
@dp.message_handler(lambda m: m.text == "➕ Контент қосу")
async def user_upload_start(m: types.Message):
    await UserStates.upload_genre.set()
    await m.answer("Қай жанрға видео жібергіңіз келеді?", reply_markup=genre_kb())

@dp.message_handler(state=UserStates.upload_genre)
async def user_upload_genre(m: types.Message, state: FSMContext):
    if m.text not in GENRES: return
    await state.update_data(genre=m.text)
    await UserStates.upload_video.set()
    await m.answer("🎥 Тек видео жіберіңіз! Фото немесе мәтін өшіріледі.", 
                   reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("🔙 Артқа"))

@dp.message_handler(content_types=['any'], state=UserStates.upload_video)
async def user_upload_process(m: types.Message, state: FSMContext):
    if not m.video:
        await m.delete()
        return await m.answer("❌ Қате! Тек видео файл жіберуіңіз керек.")
    
    data = await state.get_data()
    async with aiosqlite.connect(DB) as db:
        await db.execute("INSERT INTO user_submissions(file_id, genre, user_id) VALUES (?,?,?)",
                         (m.video.file_id, data['genre'], m.from_user.id))
        await db.commit()
    
    await m.answer("✅ Видеоңыз кетті, админ жауабын күтіңіз.\nТағы жібересіз бе? (Немесе артқа басыңыз)")

# --- ADMIN FUNCTIONS ---
@dp.message_handler(lambda m: m.text == "⚙️ Админ Панель", user_id=ADMIN_ID)
async def admin_main(m: types.Message):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("➕ Видео қосу", "📩 Жаңа видеолар")
    kb.row("💰 Монета беру", "📊 Статистика")
    kb.row("📢 Рассылка", "🔙 Артқа")
    await m.answer("👑 Басқару панелі:", reply_markup=kb)

@dp.message_handler(lambda m: m.text == "📊 Статистика", user_id=ADMIN_ID)
async def stats(m: types.Message):
    async with aiosqlite.connect(DB) as db:
        users_count = await (await db.execute("SELECT COUNT(*) FROM users")).fetchone()
        content_count = await (await db.execute("SELECT genre, COUNT(*) FROM content GROUP BY genre")).fetchall()
    
    txt = f"👥 Жалпы қолданушылар: {users_count[0]}\n\n📚 Жанрлар бойынша:\n"
    for c in content_count:
        txt += f"- {c[0]}: {c[1]} видео\n"
    await m.answer(txt)

@dp.message_handler(lambda m: m.text == "📩 Жаңа видеолар", user_id=ADMIN_ID)
async def check_submissions(m: types.Message):
    async with aiosqlite.connect(DB) as db:
        rows = await (await db.execute("SELECT genre, COUNT(*) FROM user_submissions GROUP BY genre")).fetchall()
    if not rows: return await m.answer("Әзірге бос.")
    
    kb = types.InlineKeyboardMarkup()
    for r in rows:
        kb.add(types.InlineKeyboardButton(f"{r[0]} ({r[1]})", callback_data=f"adm_{r[0]}"))
    await m.answer("Тексерілетін жанрды таңдаңыз:", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data.startswith('adm_'), user_id=ADMIN_ID)
async def admin_review(c: types.CallbackQuery):
    genre = c.data.split('_')[1]
    async with aiosqlite.connect(DB) as db:
        v = await (await db.execute("SELECT id, file_id, user_id FROM user_submissions WHERE genre=? LIMIT 1", (genre,))).fetchone()
    if v:
        kb = types.InlineKeyboardMarkup().row(
            types.InlineKeyboardButton("✅ Қабылдау (+12)", callback_data=f"app_{v[0]}"),
            types.InlineKeyboardButton("❌ Бас тарту", callback_data=f"rej_{v[0]}")
        )
        await bot.send_video(c.message.chat.id, v[1], caption=f"ID: {v[2]}\nЖанр: {genre}", reply_markup=kb)
    else: await c.answer("Видеолар бітті")

@dp.callback_query_handler(lambda c: c.data.startswith(('app_', 'rej_')), user_id=ADMIN_ID)
async def admin_action(c: types.CallbackQuery):
    act, vid = c.data.split('_')
    async with aiosqlite.connect(DB) as db:
        v = await (await db.execute("SELECT * FROM user_submissions WHERE id=?", (vid,))).fetchone()
        if act == "app":
            await db.execute("INSERT INTO content(file_id, type, genre) VALUES (?,?,?)", (v[1], 'video', v[2]))
            await db.execute("UPDATE users SET balance = balance + 12 WHERE id=?", (v[3],))
            try: await bot.send_message(v[3], "🌟 Сіз жіберген видео қабылданды! +12 монета берілді.")
            except: pass
        await db.execute("DELETE FROM user_submissions WHERE id=?", (vid,))
        await db.commit()
    await c.message.delete()
    await c.answer("Орындалды")

# --- AUTO TASKS ---
async def daily_bonus():
    while True:
        await asyncio.sleep(86400) # 24 сағат
        async with aiosqlite.connect(DB) as db:
            await db.execute("UPDATE users SET balance = balance + 3")
            await db.commit()

async def inactivity_checker():
    while True:
        await asyncio.sleep(3600) # Сағат сайын тексереді
        now = int(time.time())
        async with aiosqlite.connect(DB) as db:
            users = await (await db.execute("SELECT id FROM users WHERE ? - last_active >= 3600", (now,))).fetchall()
        for u in users:
            try: await bot.send_message(u[0], "🔞 Жаңа ләззат видеолары шықты! Неге кірмей кеттіңіз? 🔥")
            except: pass

# --- OTHER HANDLERS ---
@dp.message_handler(lambda m: m.text == "👥 Реферал")
async def ref_info(m: types.Message):
    me = await bot.get_me()
    link = f"https://t.me/{me.username}?start={m.from_user.id}"
    await m.answer(f"👥 <b>Реферал жүйесі</b>\n\nБұл жерде сіз достарыңызды шақырып, тегін монета жинай аласыз.\n\n"
                   f"🎁 Әр шақырылған дос үшін: <b>6 монета</b>.\n"
                   f"🔗 Сілтемеңіз: <code>{link}</code>")

@dp.message_handler(lambda m: m.text == "💰 Монета сатып алу")
async def buy_coins(m: types.Message):
    await m.answer("💰 Монетаны сатып алу үшін @QzqMoneta админіне жазыңыз.")

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(init_db())
    loop.create_task(daily_bonus())
    loop.create_task(inactivity_checker())
    executor.start_polling(dp, skip_updates=True)
