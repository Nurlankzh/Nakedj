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
API_TOKEN = "5973940534:AAGpT1eBaBuRImuSjpXdz2M-BnWn7Inn6Lk"
ADMIN_ID = 6303091468
CHANNEL_ID = "@QZQCONTENT" # Канал юзернеймі
CHANNEL_URL = "https://t.me/QZQCONTENT"
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
    broadcast = State()

class UserStates(StatesGroup):
    upload_genre = State()
    upload_video = State()

# --- DB INIT ---
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
    kb.row("🎬 Контент", "➕ Видео жіберу")
    kb.row("💰 Баланс", "👥 Реферал")
    kb.row("💎 Монета сатып алу")
    if uid == ADMIN_ID: kb.add("⚙️ Админ")
    return kb

def genre_kb():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    for g in GENRES: kb.add(g)
    kb.add("🔙 Артқа")
    return kb

def admin_kb():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("➕ Қосу", "💰 Монета беру")
    kb.row("📩 Келіп түскендер", "📢 Рассылка")
    kb.row("📊 Статистика", "🔙 Артқа")
    return kb

def sub_kb():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("Тіркелу", url=CHANNEL_URL))
    kb.add(types.InlineKeyboardButton("Тексеру", callback_data="check_sub"))
    return kb

# --- UTILS ---
async def check_subscription(uid):
    try:
        member = await bot.get_chat_member(CHANNEL_ID, uid)
        return member.status != "left"
    except: return True

async def update_activity(uid):
    async with aiosqlite.connect(DB) as db:
        await db.execute("UPDATE users SET last_active = ? WHERE id = ?", (int(time.time()), uid))
        await db.commit()

# --- START & CALLBACKS ---
@dp.message_handler(commands=['start'], state="*")
async def start(m: types.Message, state: FSMContext):
    await state.finish()
    uid = m.from_user.id
    ref = m.get_args()
    
    async with aiosqlite.connect(DB) as db:
        user = await (await db.execute("SELECT id FROM users WHERE id=?", (uid,))).fetchone()
        if not user:
            await db.execute("INSERT INTO users(id, balance, last_active, joined) VALUES (?,?,?,?)", 
                             (uid, 10, int(time.time()), int(time.time())))
            if ref and ref.isdigit() and int(ref) != uid:
                await db.execute("UPDATE users SET balance = balance + 6 WHERE id=?", (ref,))
                try: await bot.send_message(ref, "🎁 Досыңыз қосылды! +6 монета берілді.")
                except: pass
        await db.commit()

    if not await check_subscription(uid):
        return await m.answer(f"⚠️ Ботты қолдану үшін каналға тіркеліңіз!", reply_markup=sub_kb())
    
    await m.answer("<b>👋 Қош келдіңіз! Мәзірді таңдаңыз:</b>", reply_markup=main_kb(uid))

@dp.callback_query_handler(text="check_sub")
async def check_cb(c: types.CallbackQuery):
    if await check_subscription(c.from_user.id):
        await c.message.delete()
        await c.message.answer("✅ Рахмет! Енді қолдана аласыз.", reply_markup=main_kb(c.from_user.id))
    else:
        await c.answer("❌ Әлі тіркелмедіңіз!", show_alert=True)

@dp.message_handler(lambda m: m.text == "🔙 Артқа", state="*")
async def back(m: types.Message, state: FSMContext):
    await state.finish()
    await m.answer("Бас мәзірге оралдыңыз:", reply_markup=main_kb(m.from_user.id))

# --- CONTENT LOGIC ---
@dp.message_handler(lambda m: m.text == "🎬 Контент")
async def content_menu(m: types.Message):
    if not await check_subscription(m.from_user.id):
        return await m.answer("❌ Каналға тіркелу қажет!", reply_markup=sub_kb())
    await m.answer("Жанр таңдаңыз:", reply_markup=genre_kb())

@dp.message_handler(lambda m: m.text in GENRES)
async def show_content(m: types.Message):
    uid = m.from_user.id
    genre = m.text
    price = GENRES_CONFIG[genre]['price']
    await update_activity(uid)

    async with aiosqlite.connect(DB) as db:
        user = await (await db.execute("SELECT balance FROM users WHERE id=?", (uid,))).fetchone()
        if user[0] < price:
            me = await bot.get_me()
            link = f"https://t.me/{me.username}?start={uid}"
            return await m.answer(f"⚠️ <b>Монета жеткіліксіз!</b>\n\nБұл жанр үшін {price} монета керек.\nДос шақырып 6 монета алыңыз немесе сатып алыңыз.\n🔗 Сілтеме: <code>{link}</code>")

        # Көрмеген видеоларды іздеу
        res = await db.execute("""SELECT id, file_id, type FROM content WHERE genre=? 
                                  AND id NOT IN (SELECT content_id FROM viewed_history WHERE user_id=?) 
                                  ORDER BY id LIMIT 1""", (genre, uid))
        c = await res.fetchone()
        
        if not c: # Егер бітсе, тарихты өшіріп басынан бастау
            await db.execute("DELETE FROM viewed_history WHERE user_id=?", (uid,))
            res = await db.execute("SELECT id, file_id, type FROM content WHERE genre=? ORDER BY id LIMIT 1", (genre,))
            c = await res.fetchone()

        if c:
            await db.execute("UPDATE users SET balance = balance - ? WHERE id=?", (price, uid))
            await db.execute("INSERT INTO viewed_history VALUES (?,?)", (uid, c[0]))
            await db.commit()
            
            caption = f"🎬 Жанр: {genre}\n💰 Құны: {price} монета"
            if c[2] == "video":
                msg = await bot.send_video(uid, c[1], caption=caption)
            else:
                msg = await bot.send_photo(uid, c[1], caption=caption)
            
            # 30 минуттан кейін өшіру
            asyncio.create_task(delete_msg(uid, msg.message_id, 1800))
        else:
            await m.answer("Бұл жанрда контент әлі жоқ.")

async def delete_msg(chat_id, mid, delay):
    await asyncio.sleep(delay)
    try: await bot.delete_message(chat_id, mid)
    except: pass

# --- USER SUBMISSIONS ---
@dp.message_handler(lambda m: m.text == "➕ Видео жіберу")
async def user_up(m: types.Message):
    await UserStates.upload_genre.set()
    await m.answer("Қай жанрға видео жібересіз?", reply_markup=genre_kb())

@dp.message_handler(state=UserStates.upload_genre)
async def user_up_genre(m: types.Message, state: FSMContext):
    if m.text == "🔙 Артқа": 
        await state.finish()
        return await m.answer("Бас мәзір", reply_markup=main_kb(m.from_user.id))
    if m.text not in GENRES: return
    await state.update_data(genre=m.text)
    await UserStates.upload_video.set()
    await m.answer("🎥 Тек видео жіберіңіз! (Мәтін немесе сурет жіберсеңіз өшіріледі)", 
                   reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("🔙 Артқа"))

@dp.message_handler(content_types=['any'], state=UserStates.upload_video)
async def user_up_file(m: types.Message, state: FSMContext):
    if m.text == "🔙 Артқа":
        await state.finish()
        return await m.answer("Бас мәзір", reply_markup=main_kb(m.from_user.id))
        
    if not m.video:
        await m.delete()
        return await m.answer("⚠️ Тек видео жіберуге рұқсат!")
    
    data = await state.get_data()
    async with aiosqlite.connect(DB) as db:
        await db.execute("INSERT INTO user_submissions(file_id, genre, user_id) VALUES (?,?,?)",
                         (m.video.file_id, data['genre'], m.from_user.id))
        await db.commit()
    
    await m.answer("✅ Видеоңыз кетті, админ жауабын күтіңіз. Тағы жібересіз бе?")

# --- ADMIN PANEL ---
@dp.message_handler(lambda m: m.text == "⚙️ Админ", user_id=ADMIN_ID)
async def admin_p(m: types.Message):
    await m.answer("👑 Админ панель:", reply_markup=admin_kb())

@dp.message_handler(lambda m: m.text == "➕ Қосу", user_id=ADMIN_ID)
async def admin_add_start(m: types.Message):
    await AdminStates.add_content_genre.set()
    await m.answer("Қай жанрға қосамыз?", reply_markup=genre_kb())

@dp.message_handler(state=AdminStates.add_content_genre)
async def admin_add_genre(m: types.Message, state: FSMContext):
    if m.text not in GENRES: return
    await state.update_data(genre=m.text)
    await AdminStates.add_content_files.set()
    await m.answer("Файлдарды жіберіңіз (Шексіз). Біткен соң '🔙 Артқа' басыңыз.")

@dp.message_handler(content_types=['video', 'photo'], state=AdminStates.add_content_files)
async def admin_add_files(m: types.Message, state: FSMContext):
    data = await state.get_data()
    fid = m.video.file_id if m.video else m.photo[-1].file_id
    ftype = "video" if m.video else "photo"
    async with aiosqlite.connect(DB) as db:
        await db.execute("INSERT INTO content(file_id, type, genre) VALUES (?,?,?)", (fid, ftype, data['genre']))
        await db.commit()
    await m.answer("✅ Базаға сәтті қосылды.")

# --- ADMIN: MODERATION ---
@dp.message_handler(lambda m: m.text == "📩 Келіп түскендер", user_id=ADMIN_ID)
async def admin_check(m: types.Message):
    async with aiosqlite.connect(DB) as db:
        rows = await (await db.execute("SELECT genre, COUNT(*) FROM user_submissions GROUP BY genre")).fetchall()
    if not rows: return await m.answer("Жаңа видеолар жоқ.")
    kb = types.InlineKeyboardMarkup()
    for r in rows: 
        kb.add(types.InlineKeyboardButton(f"{r[0]} ({r[1]} дана)", callback_data=f"mod_{r[0]}"))
    await m.answer("Тексеру үшін жанрды таңдаңыз:", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data.startswith('mod_'), user_id=ADMIN_ID)
async def mod_show(c: types.CallbackQuery):
    genre = c.data.split('_')[1]
    async with aiosqlite.connect(DB) as db:
        v = await (await db.execute("SELECT id, file_id, user_id FROM user_submissions WHERE genre=? LIMIT 1", (genre,))).fetchone()
    if v:
        kb = types.InlineKeyboardMarkup().row(
            types.InlineKeyboardButton("✅ Қабылдау (+12)", callback_data=f"v_acc_{v[0]}"),
            types.InlineKeyboardButton("❌ Өшіру", callback_data=f"v_rej_{v[0]}")
        )
        await bot.send_video(c.message.chat.id, v[1], caption=f"Жіберуші ID: {v[2]}", reply_markup=kb)
    else: await c.answer("Бұл жанрда видео бітті.")

@dp.callback_query_handler(lambda c: c.data.startswith(('v_acc_', 'v_rej_')), user_id=ADMIN_ID)
async def mod_action(c: types.CallbackQuery):
    action, _, vid = c.data.split('_')
    async with aiosqlite.connect(DB) as db:
        v = await (await db.execute("SELECT * FROM user_submissions WHERE id=?", (vid,))).fetchone()
        if not v: return
        if action == "acc":
            await db.execute("INSERT INTO content(file_id, type, genre) VALUES (?,?,?)", (v[1], 'video', v[2]))
            await db.execute("UPDATE users SET balance = balance + 12 WHERE id=?", (v[3],))
            try: await bot.send_message(v[3], "🌟 Видеоңыз қабылданды! Сыйлыққа 12 монета берілді.")
            except: pass
        await db.execute("DELETE FROM user_submissions WHERE id=?", (vid,))
        await db.commit()
    await c.message.delete()
    await c.answer("Дайын!")

# --- ADMIN: GIVE COINS ---
@dp.message_handler(lambda m: m.text == "💰 Монета беру", user_id=ADMIN_ID)
async def admin_give_coins(m: types.Message):
    await AdminStates.give_coins_id.set()
    await m.answer("Қолданушының ID-ін жазыңыз:")

@dp.message_handler(state=AdminStates.give_coins_id)
async def give_id(m: types.Message, state: FSMContext):
    await state.update_data(target=m.text)
    await AdminStates.give_coins_amount.set()
    await m.answer("Қанша монета береміз?")

@dp.message_handler(state=AdminStates.give_coins_amount)
async def give_amount(m: types.Message, state: FSMContext):
    data = await state.get_data()
    try:
        async with aiosqlite.connect(DB) as db:
            await db.execute("UPDATE users SET balance = balance + ? WHERE id=?", (int(m.text), data['target']))
            await db.commit()
        await m.answer("✅ Монета берілді!")
        await bot.send_message(data['target'], f"💰 Админ сізге {m.text} монета берді!")
    except: await m.answer("Қате! ID немесе сан дұрыс емес.")
    await state.finish()

# --- OTHER BUTTONS ---
@dp.message_handler(lambda m: m.text == "💰 Баланс")
async def balance_show(m: types.Message):
    async with aiosqlite.connect(DB) as db:
        u = await (await db.execute("SELECT balance FROM users WHERE id=?", (m.from_user.id,))).fetchone()
    await m.answer(f"💰 Балансыңыз: <b>{u[0]} монета</b>")

@dp.message_handler(lambda m: m.text == "👥 Реферал")
async def referral_show(m: types.Message):
    me = await bot.get_me()
    link = f"https://t.me/{me.username}?start={m.from_user.id}"
    text = (f"👥 <b>Реферал жүйесі</b>\n\n"
            f"Достарыңызды шақырып, тегін видеолар көріңіз!\n"
            f"Әр шақырылған адам үшін <b>6 монета</b> аласыз.\n\n"
            f"🔗 Сілтемеңіз: <code>{link}</code>")
    await m.answer(text)

@dp.message_handler(lambda m: m.text == "💎 Монета сатып алу")
async def buy_coins(m: types.Message):
    await m.answer("💎 Монета сатып алу үшін админге жазыңыз: @QzqMoneta")

# --- BACKGROUND TASKS ---
async def daily_bonus():
    while True:
        await asyncio.sleep(86400) # 24 сағат
        async with aiosqlite.connect(DB) as db:
            await db.execute("UPDATE users SET balance = balance + 3")
            await db.commit()
            users = await (await db.execute("SELECT id FROM users")).fetchall()
        for u in users:
            try: await bot.send_message(u[0], "🎁 Күнделікті бонус: +3 монета берілді!")
            except: pass

async def auto_notifications():
    while True:
        await asyncio.sleep(3600) # Әр сағат сайын
        now = int(time.time())
        async with aiosqlite.connect(DB) as db:
            # 1 сағат кірмегендерді табу
            users = await (await db.execute("SELECT id FROM users WHERE last_active < ?", (now - 3600,))).fetchall()
        for u in users:
            try: 
                await bot.send_message(u[0], "🔞 Ең ыстық видеоларды көрмей қалдың ба? Тез кір, сені күтіп жатыр! 🔥")
                await update_activity(u[0]) # Хабарламадан кейін уақытты жаңарту
            except: pass

# --- RUN ---
if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(init_db())
    loop.create_task(daily_bonus())
    loop.create_task(auto_notifications())
    executor.start_polling(dp, skip_updates=True)
