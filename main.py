import asyncio
import logging
import time
import aiosqlite
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.utils import executor
from datetime import datetime, timedelta

# --- CONFIG ---
API_TOKEN = "5973940534:AAGpT1eBaBuRImuSjpXdz2M-BnWn7Inn6Lk"
BOT_USER = "@Yummybarbot"
ADMIN_ID = 6303091468
CHANNEL_ID = "@QZQCONTENT" # Тіркелу қажет канал
CHANNEL_URL = "https://t.me/QZQCONTENT"
DB = "yummybar.db"

# Жанрлар және бағалары
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
            last_bonus TEXT, last_active TEXT, joined_at TEXT)""")
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
    kb.row("🎬 Контент", "➕ Контент қосу")
    kb.row("👥 Реферал", "💰 Монета сатып алу")
    kb.row("📊 Статистика")
    if uid == ADMIN_ID: kb.add("⚙️ Админ Панель")
    return kb

def genre_reply_kb():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    for g in GENRES: kb.add(g)
    kb.add("🔙 Артқа")
    return kb

def sub_kb():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("📢 Каналға тіркелу", url=CHANNEL_URL))
    kb.add(types.InlineKeyboardButton("✅ Тексеру", callback_data="check_sub"))
    return kb

# --- MIDDLEWARE-LIKE SUB CHECK ---
async def is_subscribed(uid):
    try:
        member = await bot.get_chat_member(CHANNEL_ID, uid)
        return member.status in ["member", "administrator", "creator"]
    except: return False

# --- START & REF SYSTEM ---
@dp.message_handler(commands=['start'], state="*")
async def start_cmd(m: types.Message, state: FSMContext):
    await state.finish()
    uid = m.from_user.id
    if not await is_subscribed(uid):
        return await m.answer(f"<b>⚠️ Тоқтаңыз!</b>\n\nБотты пайдалану үшін {CHANNEL_ID} каналына тіркелуіңіз қажет!", reply_markup=sub_kb())

    now = datetime.now().isoformat()
    ref = m.get_args()
    async with aiosqlite.connect(DB) as db:
        user = await (await db.execute("SELECT id FROM users WHERE id=?", (uid,))).fetchone()
        if not user:
            await db.execute("INSERT INTO users(id, balance, last_bonus, last_active, joined_at) VALUES (?,?,?,?,?)", 
                             (uid, 10, now, now, now))
            if ref and ref.isdigit() and int(ref) != uid:
                await db.execute("UPDATE users SET balance = balance + 6 WHERE id=?", (ref,))
                try: await bot.send_message(ref, "🎁 Сіздің сілтемеңізбен жаңа қолданушы тіркелді! <b>+6 монета</b> берілді.")
                except: pass
        else:
            await db.execute("UPDATE users SET last_active = ? WHERE id=?", (now, uid))
        await db.commit()
    
    await m.answer("<b>👋 Сәлем! Төмендегі мәзірді қолданыңыз:</b>", reply_markup=main_kb(uid))

@dp.callback_query_handler(text="check_sub")
async def check_sub_btn(c: types.CallbackQuery):
    if await is_subscribed(c.from_user.id):
        await c.answer("✅ Рахмет! Енді қолдана аласыз.")
        await start_cmd(c.message, None)
    else:
        await c.answer("❌ Әлі тіркелмедіңіз!", show_alert=True)

# --- BACK BUTTON ---
@dp.message_handler(lambda m: m.text == "🔙 Артқа", state="*")
async def back_logic(m: types.Message, state: FSMContext):
    await state.finish()
    await start_cmd(m, state)

# --- USER CONTENT LOGIC ---
@dp.message_handler(lambda m: m.text == "🎬 Контент")
async def show_genres(m: types.Message):
    if not await is_subscribed(m.from_user.id): return await start_cmd(m, None)
    await m.answer("Жанр таңдаңыз:", reply_markup=genre_kb())

def genre_kb():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    for g in GENRES: kb.add(g)
    kb.add("🔙 Артқа")
    return kb

@dp.message_handler(lambda m: m.text in GENRES)
async def get_video(m: types.Message):
    uid = m.from_user.id
    genre = m.text
    price = GENRES_CONFIG[genre]['price']
    
    async with aiosqlite.connect(DB) as db:
        u = await (await db.execute("SELECT balance FROM users WHERE id=?", (uid,))).fetchone()
        if u[0] < price:
            link = f"https://t.me/{BOT_USER.replace('@','')}?start={uid}"
            return await m.answer(f"⚠️ <b>Монета жеткіліксіз!</b>\n\nБұл видеоны көру құны: {price} монета.\n"
                                  f"Сізде: {u[0]} монета.\n\n"
                                  f"Достарыңызды шақырып 6 монета алыңыз немесе сатып алыңыз.\n"
                                  f"🔗 Сілтеме: <code>{link}</code>")

        # Кезекпен көрсету логикасы
        res = await db.execute("""SELECT id, file_id, type FROM content WHERE genre=? 
                                  AND id NOT IN (SELECT content_id FROM viewed_history WHERE user_id=?) 
                                  ORDER BY id LIMIT 1""", (genre, uid))
        v = await res.fetchone()
        
        if not v: # Егер видео бітсе басынан бастайды
            await db.execute("DELETE FROM viewed_history WHERE user_id=?", (uid,))
            res = await db.execute("SELECT id, file_id, type FROM content WHERE genre=? ORDER BY id LIMIT 1", (genre,))
            v = await res.fetchone()

        if v:
            await db.execute("UPDATE users SET balance = balance - ?, last_active = ? WHERE id=?", (price, datetime.now().isoformat(), uid))
            await db.execute("INSERT INTO viewed_history VALUES (?,?)", (uid, v[0]))
            await db.commit()
            
            sent = await bot.send_video(uid, v[1], caption="🎬 Рахаттанып көріңіз!\n⚠️ Видео 30 минуттан соң өшеді.")
            asyncio.create_task(auto_delete(uid, sent.message_id, 1800))
        else:
            await m.answer("Бұл жанрда видео әлі жоқ.")

async def auto_delete(chat_id, mid, sec):
    await asyncio.sleep(sec)
    try: await bot.delete_message(chat_id, mid)
    except: pass

# --- UPLOAD SYSTEM (USER) ---
@dp.message_handler(lambda m: m.text == "➕ Контент қосу")
async def user_upload_start(m: types.Message):
    await UserStates.upload_genre.set()
    await m.answer("Қай жанрға видео жібергіңіз келеді?", reply_markup=genre_reply_kb())

@dp.message_handler(state=UserStates.upload_genre)
async def user_upload_genre_choice(m: types.Message, state: FSMContext):
    if m.text not in GENRES: return
    await state.update_data(genre=m.text)
    await UserStates.upload_video.set()
    await m.answer("🎥 Видеоңызды жіберіңіз.\n⚠️ Ескерту: Тек видео қабылданады, сурет немесе мәтін өшіріледі.", 
                   reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("🔙 Артқа"))

@dp.message_handler(content_types=['any'], state=UserStates.upload_video)
async def user_upload_process(m: types.Message, state: FSMContext):
    if not m.video:
        try: await m.delete()
        except: pass
        return await m.answer("🚫 Қате! Тек видео формат жіберіңіз.")
    
    data = await state.get_data()
    async with aiosqlite.connect(DB) as db:
        await db.execute("INSERT INTO user_submissions(file_id, genre, user_id) VALUES (?,?,?)",
                         (m.video.file_id, data['genre'], m.from_user.id))
        await db.commit()
    
    await m.answer("✅ Видеоңыз кетті, админ жауабын күтіңіз. Тағы видео жібересіз бе?")

# --- REFERRAL & STATS ---
@dp.message_handler(lambda m: m.text == "👥 Реферал")
async def ref_info(m: types.Message):
    uid = m.from_user.id
    link = f"https://t.me/{BOT_USER.replace('@','')}?start={uid}"
    text = (f"👥 <b>Реферал жүйесі</b>\n\n"
            f"Досыңды шақырғаның үшін біз саған <b>6 монета</b> береміз!\n"
            f"Монеталар арқылы сен жабық жанрлардағы видеоларды тегін көре аласың.\n\n"
            f"🔗 Сенің сілтемең: <code>{link}</code>")
    await m.answer(text)

@dp.message_handler(lambda m: m.text == "💰 Монета сатып алу")
async def buy_coins(m: types.Message):
    await m.answer("💰 Монета сатып алу үшін админге жазыңыз: @QzqMoneta")

@dp.message_handler(lambda m: m.text == "📊 Статистика")
async def stats(m: types.Message):
    async with aiosqlite.connect(DB) as db:
        users_count = await (await db.execute("SELECT COUNT(*) FROM users")).fetchone()
        videos_count = await (await db.execute("SELECT COUNT(*) FROM content")).fetchone()
    await m.answer(f"📊 <b>Бот статистикасы:</b>\n\n👤 Қолданушылар: {users_count[0]}\n🎬 Жалпы видеолар: {videos_count[0]}")

# --- ADMIN LOGIC ---
@dp.message_handler(lambda m: m.text == "⚙️ Админ Панель", user_id=ADMIN_ID)
async def admin_main(m: types.Message):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("📥 Жүктелгендер", "➕ Видео қосу")
    kb.row("💎 Монета беру", "📢 Рассылка")
    kb.add("🔙 Артқа")
    await m.answer("👑 Админ басқару панелі:", reply_markup=kb)

@dp.message_handler(lambda m: m.text == "💎 Монета беру", user_id=ADMIN_ID)
async def adm_give_1(m: types.Message):
    await AdminStates.give_coins_id.set()
    await m.answer("Қолданушы ID-ін жіберіңіз:")

@dp.message_handler(state=AdminStates.give_coins_id)
async def adm_give_2(m: types.Message, state: FSMContext):
    await state.update_data(target_id=m.text)
    await AdminStates.give_coins_amount.set()
    await m.answer("Қанша монета береміз?")

@dp.message_handler(state=AdminStates.give_coins_amount)
async def adm_give_3(m: types.Message, state: FSMContext):
    data = await state.get_data()
    async with aiosqlite.connect(DB) as db:
        await db.execute("UPDATE users SET balance = balance + ? WHERE id=?", (m.text, data['target_id']))
        await db.commit()
    await m.answer(f"✅ {data['target_id']} қолданушысына {m.text} монета берілді.")
    try: await bot.send_message(data['target_id'], f"💎 Админ сізге {m.text} монета сыйлады!")
    except: pass
    await state.finish()

# --- TASK: 24h BONUS & AUTO NOTIFY ---
async def scheduled_tasks():
    while True:
        await asyncio.sleep(60) # Минут сайын тексеру
        now = datetime.now()
        async with aiosqlite.connect(DB) as db:
            # 24 сағаттық бонус
            users = await (await db.execute("SELECT id, last_bonus FROM users")).fetchall()
            for uid, last_b in users:
                if datetime.fromisoformat(last_b) <= now - timedelta(hours=24):
                    await db.execute("UPDATE users SET balance = balance + 3, last_bonus = ? WHERE id = ?", (now.isoformat(), uid))
                    try: await bot.send_message(uid, "🎁 Күнделікті сыйлық: <b>3 монета</b> берілді!")
                    except: pass
            
            # Авто уведомление (1 сағат кірмегендерге)
            inactive = await (await db.execute("SELECT id FROM users WHERE last_active <= ?", ( (now - timedelta(hours=1)).isoformat(), ))).fetchall()
            for (uid,) in inactive:
                try: 
                    await bot.send_message(uid, "🥵 Оу, неге кіріп жатқан жоқсың? Жаңа ыстық видеолар шықты, үлгеріп қал... 🔥")
                    await db.execute("UPDATE users SET last_active = ? WHERE id = ?", (now.isoformat(), uid))
                except: pass
            await db.commit()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(init_db())
    loop.create_task(scheduled_tasks())
    executor.start_polling(dp, skip_updates=True)
