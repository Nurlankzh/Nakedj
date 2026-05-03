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

# Жанрлар және бағалары
GENRES_CONFIG = {
    "🎬 Қазақша": {"price": 5, "ref_reward": 6},
    "🥵 Орысша": {"price": 4, "ref_reward": 6},
    "🤭 Балалар": {"price": 6, "ref_reward": 6},
    "😍 Американша": {"price": 3, "ref_reward": 6}
}
GENRES = list(GENRES_CONFIG.keys())

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN, parse_mode="HTML")
dp = Dispatcher(bot, storage=MemoryStorage())

# --- STATES ---
class AdminStates(StatesGroup):
    add_file = State()
    add_genre = State()
    give_coins_id = State()
    give_coins_amount = State()
    check_user_videos = State()

class UserStates(StatesGroup):
    send_video_genre = State()
    send_video_file = State()

# --- DB INIT ---
async def init_db():
    async with aiosqlite.connect(DB) as db:
        await db.execute("""CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY, balance INTEGER DEFAULT 10, 
            is_banned INTEGER DEFAULT 0, joined INTEGER)""")
        
        await db.execute("""CREATE TABLE IF NOT EXISTS content(
            id INTEGER PRIMARY KEY AUTOINCREMENT, file_id TEXT, 
            type TEXT, genre TEXT, added_by INTEGER DEFAULT 0)""")
        
        await db.execute("""CREATE TABLE IF NOT EXISTS user_submissions(
            id INTEGER PRIMARY KEY AUTOINCREMENT, file_id TEXT, 
            genre TEXT, user_id INTEGER)""")
        
        await db.execute("""CREATE TABLE IF NOT EXISTS viewed_content(
            user_id INTEGER, content_id INTEGER)""")
        await db.commit()

# --- KEYBOARDS ---
def main_kb(uid):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("🎬 Контент", "➕ Контент қосу")
    kb.row("💰 Баланс", "👥 Реферал")
    if uid == ADMIN_ID:
        kb.add("⚙️ Админ")
    return kb

def genre_kb():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    for g in GENRES: kb.add(g)
    kb.add("🔙 Артқа")
    return kb

def admin_kb():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("➕ Қосу", "💰 Монета беру")
    kb.row("📩 Келіп түскен видеолар", "📊 Стат")
    kb.add("🔙 Артқа")
    return kb

# --- MIDDLEWARE (Sub Check) ---
async def check_sub(uid):
    try:
        m = await bot.get_chat_member(CHANNEL, uid)
        return m.status != "left"
    except: return True

# --- START ---
@dp.message_handler(commands=['start'], state="*")
async def start(m: types.Message, state: FSMContext):
    await state.finish()
    uid = m.from_user.id
    args = m.get_args()
    
    async with aiosqlite.connect(DB) as db:
        user = await db.execute("SELECT id FROM users WHERE id=?", (uid,))
        if not await user.fetchone():
            await db.execute("INSERT INTO users(id, joined) VALUES (?,?)", (uid, int(time.time())))
            if args.isdigit() and int(args) != uid:
                await db.execute("UPDATE users SET balance = balance + 6 WHERE id=?", (args,))
                try: await bot.send_message(args, "🎁 Досыңыз келді! +6 монета берілді.")
                except: pass
        await db.commit()
    
    await m.answer("<b>👋 Қош келдіңіз! Жоғары сапалы контент әлеміне еніңіз.</b>", reply_markup=main_kb(uid))

# --- BACK BUTTON ---
@dp.message_handler(lambda m: m.text == "🔙 Артқа", state="*")
async def back_to_menu(m: types.Message, state: FSMContext):
    await state.finish()
    await m.answer("Бас мәзірге оралдыңыз:", reply_markup=main_kb(m.from_user.id))

# --- CONTENT LOGIC ---
@dp.message_handler(lambda m: m.text == "🎬 Контент")
async def content_menu(m: types.Message):
    if not await check_sub(m.from_user.id):
        return await m.answer(f"❌ <b>Тоқтаңыз!</b> Видео көру үшін алдымен каналымызға тіркеліңіз: {CHANNEL}")
    await m.answer("Қай жанрдағы видеоларды тамашалағыңыз келеді?", reply_markup=genre_kb())

@dp.message_handler(lambda m: m.text in GENRES)
async def show_video(m: types.Message):
    uid = m.from_user.id
    genre = m.text
    price = GENRES_CONFIG[genre]['price']
    
    async with aiosqlite.connect(DB) as db:
        u_data = await (await db.execute("SELECT balance FROM users WHERE id=?", (uid,))).fetchone()
        if u_data[0] < price:
            me = await bot.get_me()
            link = f"https://t.me/{me.username}?start={uid}"
            return await m.answer(f"⚠️ <b>Монетаңыз жеткіліксіз!</b>\n\nБұл жанр үшін {price} монета қажет. \nҚазір сізде: {u_data[0]} монета.\n\nДостарыңызды шақырып, әр дос үшін 6 монета алыңыз!\n🔗 Сілтеме: <code>{link}</code>")

        # Көрмеген видеоны табу
        res = await db.execute("""SELECT id, file_id, type FROM content 
                                WHERE genre=? AND id NOT IN (SELECT content_id FROM viewed_content WHERE user_id=?) 
                                ORDER BY id ASC LIMIT 1""", (genre, uid))
        c = await res.fetchone()
        
        if not c: # Егер бәрін көрсе, басынан бастау
            await db.execute("DELETE FROM viewed_content WHERE user_id=?", (uid,))
            res = await db.execute("SELECT id, file_id, type FROM content WHERE genre=? ORDER BY id ASC LIMIT 1", (genre,))
            c = await res.fetchone()

        if c:
            cid, fid, ftype = c
            await db.execute("UPDATE users SET balance = balance - ? WHERE id=?", (price, uid))
            await db.execute("INSERT INTO viewed_content VALUES (?,?)", (uid, cid))
            await db.commit()
            
            msg = await (bot.send_video(uid, fid) if ftype == "video" else bot.send_photo(uid, fid))
            # 30 минуттан кейін өшіру (asyncio background task)
            asyncio.create_task(delete_after_time(uid, msg.message_id, 1800))
        else:
            await m.answer("Бұл жанрда әлі видео жоқ.")

async def delete_after_time(chat_id, msg_id, delay):
    await asyncio.sleep(delay)
    try: await bot.delete_message(chat_id, msg_id)
    except: pass

# --- USER SUBMISSION ---
@dp.message_handler(lambda m: m.text == "➕ Контент қосу")
async def user_add_start(m: types.Message):
    await UserStates.send_video_genre.set()
    await m.answer("Қай жанрға видео қосқыңыз келеді?", reply_markup=genre_kb())

@dp.message_handler(state=UserStates.send_video_genre)
async def user_set_genre(m: types.Message, state: FSMContext):
    if m.text not in GENRES: return await m.answer("Тізімнен таңдаңыз")
    await state.update_data(genre=m.text)
    await UserStates.send_video_file.set()
    await m.answer("🎥 <b>Тек видео жіберіңіз!</b>\nАдмин тексеріп, видеоңыз өтсе 12 монета аласыз.", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("🔙 Артқа"))

@dp.message_handler(content_types=['any'], state=UserStates.send_video_file)
async def user_get_video(m: types.Message, state: FSMContext):
    if not m.video:
        await m.delete()
        return await m.answer("⚠️ Қате! Тек видео файл жіберу керек. Мәтін немесе фото қабылданбайды.")
    
    data = await state.get_data()
    async with aiosqlite.connect(DB) as db:
        await db.execute("INSERT INTO user_submissions(file_id, genre, user_id) VALUES (?,?,?)",
                         (m.video.file_id, data['genre'], m.from_user.id))
        await db.commit()
    
    await m.answer("✅ Видеоңыз сәтті кетті! Админ мақұлдауын күтіңіз. Тағы жібересіз бе? (немесе 'Артқа' басыңыз)")

# --- ADMIN: GIVE COINS ---
@dp.message_handler(lambda m: m.text == "💰 Монета беру", user_id=ADMIN_ID)
async def admin_give_coins(m: types.Message):
    await AdminStates.give_coins_id.set()
    await m.answer("Монета беретін қолданушының ID-ін жазыңыз:")

@dp.message_handler(state=AdminStates.give_coins_id)
async def admin_id_step(m: types.Message, state: FSMContext):
    await state.update_data(target_id=m.text)
    await AdminStates.give_coins_amount.set()
    await m.answer("Қанша монета бересіз?")

@dp.message_handler(state=AdminStates.give_coins_amount)
async def admin_amount_step(m: types.Message, state: FSMContext):
    data = await state.get_data()
    amount = m.text
    async with aiosqlite.connect(DB) as db:
        await db.execute("UPDATE users SET balance = balance + ? WHERE id=?", (amount, data['target_id']))
        await db.commit()
    await m.answer(f"✅ ID {data['target_id']}-ге {amount} монета берілді.")
    try: await bot.send_message(data['target_id'], f"🎁 Админ сізге {amount} монета сыйлады!")
    except: pass
    await state.finish()

# --- ADMIN: SUBMISSIONS CHECK ---
@dp.message_handler(lambda m: m.text == "📩 Келіп түскен видеолар", user_id=ADMIN_ID)
async def admin_check_subs(m: types.Message):
    async with aiosqlite.connect(DB) as db:
        res = await db.execute("SELECT genre, COUNT(*) FROM user_submissions GROUP BY genre")
        rows = await res.fetchall()
    
    if not rows: return await m.answer("Жаңа видеолар жоқ.")
    
    kb = types.InlineKeyboardMarkup()
    for r in rows:
        kb.add(types.InlineKeyboardButton(f"{r[0]} ({r[1]} дана)", callback_data=f"check_{r[0]}"))
    await m.answer("Тексерілетін жанрды таңдаңыз:", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data.startswith('check_'), user_id=ADMIN_ID)
async def admin_show_sub(c: types.CallbackQuery):
    genre = c.data.split('_')[1]
    async with aiosqlite.connect(DB) as db:
        res = await db.execute("SELECT id, file_id, user_id FROM user_submissions WHERE genre=? LIMIT 1", (genre,))
        row = await res.fetchone()
    
    if row:
        kb = types.InlineKeyboardMarkup()
        kb.row(types.InlineKeyboardButton("✅ Қабылдау (+12 монета)", callback_data=f"app_{row[0]}"),
               types.InlineKeyboardButton("❌ Өшіру", callback_data=f"rej_{row[0]}"))
        await bot.send_video(c.message.chat.id, row[1], caption=f"Жіберуші: {row[2]}\nЖанр: {genre}", reply_markup=kb)
    else:
        await c.answer("Бұл жанрда видео бітті.")

@dp.callback_query_handler(lambda c: c.data.startswith(('app_', 'rej_')), user_id=ADMIN_ID)
async def admin_action_sub(c: types.CallbackQuery):
    action, sid = c.data.split('_')
    async with aiosqlite.connect(DB) as db:
        res = await db.execute("SELECT * FROM user_submissions WHERE id=?", (sid,))
        data = await res.fetchone()
        if action == "app":
            await db.execute("INSERT INTO content(file_id, type, genre, added_by) VALUES (?,?,?,?)",
                             (data[1], "video", data[2], data[3]))
            await db.execute("UPDATE users SET balance = balance + 12 WHERE id=?", (data[3],))
            try: await bot.send_message(data[3], "🌟 Құттықтаймыз! Видеоңыз қабылданды, 12 монета берілді.")
            except: pass
        await db.execute("DELETE FROM user_submissions WHERE id=?", (sid,))
        await db.commit()
    await c.message.delete()
    await c.answer("Орындалды")

# --- OTHER HANDLERS (Stats, Ref, Balance) ---
@dp.message_handler(lambda m: m.text == "💰 Баланс")
async def show_balance(m: types.Message):
    async with aiosqlite.connect(DB) as db:
        u = await (await db.execute("SELECT balance FROM users WHERE id=?", (m.from_user.id,))).fetchone()
    await m.answer(f"<b>💰 Сіздің балансыңыз:</b> {u[0]} монета\n\n<i>Видео көру үшін монета жұмсалады.</i>")

@dp.message_handler(lambda m: m.text == "👥 Реферал")
async def show_ref(m: types.Message):
    me = await bot.get_me()
    link = f"https://t.me/{me.username}?start={m.from_user.id}"
    text = (
        "<b>👥 Реферал жүйесі</b>\n\n"
        "Достарыңызды шақырып, тегін видеолар көріңіз!\n"
        "Әрбір тіркелген қолданушы үшін сізге <b>6 монета</b> беріледі.\n\n"
        f"🔗 Сіздің сілтемеңіз: <code>{link}</code>"
    )
    await m.answer(text)

# --- AUTO NOTIFICATION ---
async def auto_notify():
    while True:
        await asyncio.sleep(7200) # Әр 2 сағат сайын
        async with aiosqlite.connect(DB) as db:
            users = await (await db.execute("SELECT id FROM users")).fetchall()
        for u in users:
            try: await bot.send_message(u[0], "🔞 Ең ыстық видеолар жаңартылды! Көруге асығыңыз... 🔥")
            except: pass

# --- RUN ---
if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(init_db())
    loop.create_task(auto_notify())
    executor.start_polling(dp, skip_updates=True)
