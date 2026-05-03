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
API_TOKEN = "TOKEN_HERE"
ADMIN_ID = 6303091468
CHANNEL = "@QZSTOP"
DB = "enterprise.db"

# Жанрлар және олардың бағалары
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

class UserStates(StatesGroup):
    upload_genre = State()
    upload_video = State()

# --- DB INIT ---
async def init_db():
    async with aiosqlite.connect(DB) as db:
        await db.execute("""CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY, balance INTEGER DEFAULT 10, joined INTEGER)""")
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
    kb.row("🎬 Контент", "➕ Контент жіберу")
    kb.row("💰 Баланс", "👥 Реферал")
    if uid == ADMIN_ID: kb.add("⚙️ Админ")
    return kb

def genre_kb():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    for g in GENRES: kb.add(g)
    kb.add("🔙 Артқа")
    return kb

def admin_kb():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("➕ Видео қосу", "💰 Монета беру")
    kb.row("📩 Келіп түскендер", "🔙 Артқа")
    return kb

# --- UTILS ---
async def check_sub(uid):
    try:
        m = await bot.get_chat_member(CHANNEL, uid)
        return m.status != "left"
    except: return True

# --- START & BACK ---
@dp.message_handler(commands=['start'], state="*")
async def start(m: types.Message, state: FSMContext):
    await state.finish()
    uid = m.from_user.id
    ref = m.get_args()
    async with aiosqlite.connect(DB) as db:
        user = await (await db.execute("SELECT id FROM users WHERE id=?", (uid,))).fetchone()
        if not user:
            await db.execute("INSERT INTO users(id, joined) VALUES (?,?)", (uid, int(time.time())))
            if ref and ref.isdigit() and int(ref) != uid:
                await db.execute("UPDATE users SET balance = balance + 6 WHERE id=?", (ref,))
                try: await bot.send_message(ref, "🎁 Сіздің сілтемеңізбен адам тіркелді! +6 монета берілді.")
                except: pass
        await db.commit()
    await m.answer("<b>👋 Қош келдіңіз!</b>\nЕң қызықты контент осында.", reply_markup=main_kb(uid))

@dp.message_handler(lambda m: m.text == "🔙 Артқа", state="*")
async def back(m: types.Message, state: FSMContext):
    await state.finish()
    await m.answer("Бас мәзірге оралдыңыз:", reply_markup=main_kb(m.from_user.id))

# --- CONTENT LOGIC ---
@dp.message_handler(lambda m: m.text == "🎬 Контент")
async def content_menu(m: types.Message):
    if not await check_sub(m.from_user.id):
        return await m.answer(f"❌ Каналға тіркелмегенсіз: {CHANNEL}")
    await m.answer("Жанр таңдаңыз:", reply_markup=genre_kb())

@dp.message_handler(lambda m: m.text in GENRES)
async def show_content(m: types.Message):
    uid = m.from_user.id
    genre = m.text
    price = GENRES_CONFIG[genre]['price']
    
    async with aiosqlite.connect(DB) as db:
        user = await (await db.execute("SELECT balance FROM users WHERE id=?", (uid,))).fetchone()
        if user[0] < price:
            me = await bot.get_me()
            link = f"https://t.me/{me.username}?start={uid}"
            return await m.answer(f"⚠️ <b>Баланс жеткіліксіз!</b>\n\nБұл жанрды көру үшін {price} монета керек.\nДос шақырып 6 монета алыңыз.\n🔗 Сілтеме: <code>{link}</code>")

        res = await db.execute("""SELECT id, file_id, type FROM content WHERE genre=? 
                                  AND id NOT IN (SELECT content_id FROM viewed_history WHERE user_id=?) 
                                  ORDER BY id LIMIT 1""", (genre, uid))
        c = await res.fetchone()
        
        if not c: # Егер бәрін көрсе, басынан бастайды
            await db.execute("DELETE FROM viewed_history WHERE user_id=?", (uid,))
            res = await db.execute("SELECT id, file_id, type FROM content WHERE genre=? ORDER BY id LIMIT 1", (genre,))
            c = await res.fetchone()

        if c:
            await db.execute("UPDATE users SET balance = balance - ? WHERE id=?", (price, uid))
            await db.execute("INSERT INTO viewed_history VALUES (?,?)", (uid, c[0]))
            await db.commit()
            
            msg = await (bot.send_video(uid, c[1]) if c[2] == "video" else bot.send_photo(uid, c[1]))
            # 30 минуттан кейін өшіру (30 * 60 = 1800 секунд)
            asyncio.create_task(delete_msg(uid, msg.message_id, 1800))
        else:
            await m.answer("Бұл жанрда әлі контент жоқ.")

async def delete_msg(chat_id, mid, delay):
    await asyncio.sleep(delay)
    try: await bot.delete_message(chat_id, mid)
    except: pass

# --- USER UPLOAD ---
@dp.message_handler(lambda m: m.text == "➕ Контент жіберу")
async def user_up(m: types.Message):
    await UserStates.upload_genre.set()
    await m.answer("Қай жанрға видео жібересіз?", reply_markup=genre_kb())

@dp.message_handler(state=UserStates.upload_genre)
async def user_up_genre(m: types.Message, state: FSMContext):
    if m.text not in GENRES: return
    await state.update_data(genre=m.text)
    await UserStates.upload_video.set()
    await m.answer("🎥 Тек видео жіберіңіз! (Мәтін немесе сурет қабылданбайды)", 
                   reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("🔙 Артқа"))

@dp.message_handler(content_types=['any'], state=UserStates.upload_video)
async def user_up_file(m: types.Message, state: FSMContext):
    if not m.video:
        await m.delete()
        return await m.answer("⚠️ Қате! Тек видео жіберуіңіз керек.")
    
    data = await state.get_data()
    async with aiosqlite.connect(DB) as db:
        await db.execute("INSERT INTO user_submissions(file_id, genre, user_id) VALUES (?,?,?)",
                         (m.video.file_id, data['genre'], m.from_user.id))
        await db.commit()
    
    await m.answer("✅ Видеоңыз кетті, админ жауабын күтіңіз. Тағы жібересіз бе?")

# --- ADMIN PANEL ---
@dp.message_handler(lambda m: m.text == "⚙️ Админ", user_id=ADMIN_ID)
async def admin_panel(m: types.Message):
    await m.answer("👑 Админ панеліне қош келдіңіз:", reply_markup=admin_kb())

@dp.message_handler(lambda m: m.text == "➕ Видео қосу", user_id=ADMIN_ID)
async def admin_add_start(m: types.Message):
    await AdminStates.add_content_genre.set()
    await m.answer("Қай жанрға қосасыз?", reply_markup=genre_kb())

@dp.message_handler(state=AdminStates.add_content_genre)
async def admin_add_genre(m: types.Message, state: FSMContext):
    if m.text not in GENRES: return
    await state.update_data(genre=m.text)
    await AdminStates.add_content_files.set()
    await m.answer("Файлдарды жіберіңіз (Шексіз жіберуге болады, соңында '🔙 Артқа' басыңыз)")

@dp.message_handler(content_types=['video', 'photo'], state=AdminStates.add_content_files)
async def admin_add_files(m: types.Message, state: FSMContext):
    data = await state.get_data()
    fid = m.video.file_id if m.video else m.photo[-1].file_id
    ftype = "video" if m.video else "photo"
    async with aiosqlite.connect(DB) as db:
        await db.execute("INSERT INTO content(file_id, type, genre) VALUES (?,?,?)", (fid, ftype, data['genre']))
        await db.commit()
    await m.answer("✅ Базаға қосылды. Келесі файлды жіберіңіз немесе артқа қайтыңыз.")

# --- ADMIN: GIVE COINS ---
@dp.message_handler(lambda m: m.text == "💰 Монета беру", user_id=ADMIN_ID)
async def give_coins_start(m: types.Message):
    await AdminStates.give_coins_id.set()
    await m.answer("Қолданушы ID-ін жазыңыз:")

@dp.message_handler(state=AdminStates.give_coins_id)
async def give_coins_id(m: types.Message, state: FSMContext):
    await state.update_data(target=m.text)
    await AdminStates.give_coins_amount.set()
    await m.answer("Қанша монета бересіз?")

@dp.message_handler(state=AdminStates.give_coins_amount)
async def give_coins_done(m: types.Message, state: FSMContext):
    data = await state.get_data()
    async with aiosqlite.connect(DB) as db:
        await db.execute("UPDATE users SET balance = balance + ? WHERE id=?", (m.text, data['target']))
        await db.commit()
    await m.answer("✅ Монета берілді!")
    try: await bot.send_message(data['target'], f"💰 Админ сізге {m.text} монета берді!")
    except: pass
    await state.finish()

# --- ADMIN: CHECK SUBMISSIONS ---
@dp.message_handler(lambda m: m.text == "📩 Келіп түскендер", user_id=ADMIN_ID)
async def check_subs(m: types.Message):
    async with aiosqlite.connect(DB) as db:
        rows = await (await db.execute("SELECT genre, COUNT(*) FROM user_submissions GROUP BY genre")).fetchall()
    if not rows: return await m.answer("Жаңа видеолар жоқ.")
    kb = types.InlineKeyboardMarkup()
    for r in rows: kb.add(types.InlineKeyboardButton(f"{r[0]} ({r[1]} дана)", callback_data=f"check_{r[0]}"))
    await m.answer("Тексерілетін жанрды таңдаңыз:", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data.startswith('check_'), user_id=ADMIN_ID)
async def check_sub_show(c: types.CallbackQuery):
    genre = c.data.split('_')[1]
    async with aiosqlite.connect(DB) as db:
        v = await (await db.execute("SELECT id, file_id, user_id FROM user_submissions WHERE genre=? LIMIT 1", (genre,))).fetchone()
    if v:
        kb = types.InlineKeyboardMarkup().row(
            types.InlineKeyboardButton("✅ Қабылдау", callback_data=f"acc_{v[0]}"),
            types.InlineKeyboardButton("❌ Өшіру", callback_data=f"rej_{v[0]}")
        )
        await bot.send_video(c.message.chat.id, v[1], caption=f"Жіберуші: {v[2]}", reply_markup=kb)
    else: await c.answer("Видео бітті")

@dp.callback_query_handler(lambda c: c.data.startswith(('acc_', 'rej_')), user_id=ADMIN_ID)
async def check_sub_action(c: types.CallbackQuery):
    action, vid = c.data.split('_')
    async with aiosqlite.connect(DB) as db:
        v = await (await db.execute("SELECT * FROM user_submissions WHERE id=?", (vid,))).fetchone()
        if action == "acc":
            await db.execute("INSERT INTO content(file_id, type, genre) VALUES (?,?,?)", (v[1], 'video', v[2]))
            await db.execute("UPDATE users SET balance = balance + 12 WHERE id=?", (v[3],))
            try: await bot.send_message(v[3], "🌟 Видеоңыз қабылданды! +12 монета берілді.")
            except: pass
        await db.execute("DELETE FROM user_submissions WHERE id=?", (vid,))
        await db.commit()
    await c.message.delete()
    await c.answer("Орындалды")

# --- OTHER ---
@dp.message_handler(lambda m: m.text == "💰 Баланс")
async def bal(m: types.Message):
    async with aiosqlite.connect(DB) as db:
        u = await (await db.execute("SELECT balance FROM users WHERE id=?", (m.from_user.id,))).fetchone()
    await m.answer(f"💰 Сіздің балансыңыз: <b>{u[0]}</b> монета.")

@dp.message_handler(lambda m: m.text == "👥 Реферал")
async def ref_link(m: types.Message):
    me = await bot.get_me()
    link = f"https://t.me/{me.username}?start={m.from_user.id}"
    await m.answer(f"👥 <b>Реферал жүйесі</b>\n\nСілтеме арқылы шақырылған әр адам үшін 6 монета аласыз.\n🔗 Сілтеме: <code>{link}</code>")

async def auto_notify():
    while True:
        await asyncio.sleep(7200)
        async with aiosqlite.connect(DB) as db:
            users = await (await db.execute("SELECT id FROM users")).fetchall()
        for u in users:
            try: await bot.send_message(u[0], "🔞 Ең ыстық видеолар жаңартылды! Көруге асығыңыз... 🔥")
            except: pass

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(init_db())
    loop.create_task(auto_notify())
    executor.start_polling(dp, skip_updates=True)
