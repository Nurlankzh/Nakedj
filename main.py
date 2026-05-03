import asyncio
import logging
import time
import aiosqlite
import random
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.utils import executor
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# --- CONFIG ---
API_TOKEN = "5973940534:AAGpT1eBaBuRImuSjpXdz2M-BnWn7Inn6Lk"
ADMIN_ID = 6303091468
CHANNEL_URL = "https://t.me/QZQCONTENT"
CHANNEL_ID = "@QZQCONTENT"
BOT_USER = "@Yummybarbot"
DB = "enterprise.db"

# Жанрлар және бағалар
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
    add_genre = State()
    add_files = State()
    give_id = State()
    give_amount = State()
    broadcast = State()

class UserStates(StatesGroup):
    upload_genre = State()
    upload_video = State()

# --- DATABASE ---
async def init_db():
    async with aiosqlite.connect(DB) as db:
        await db.execute("""CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY, balance INTEGER DEFAULT 10, 
            last_bonus TEXT, last_active TEXT)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS content(
            id INTEGER PRIMARY KEY AUTOINCREMENT, file_id TEXT, 
            type TEXT, genre TEXT)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS submissions(
            id INTEGER PRIMARY KEY AUTOINCREMENT, file_id TEXT, 
            genre TEXT, user_id INTEGER)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS history(
            user_id INTEGER, content_id INTEGER)""")
        await db.commit()

# --- MIDDLEWARE & UTILS ---
async def check_sub(uid):
    try:
        member = await bot.get_chat_member(CHANNEL_ID, uid)
        return member.status != "left"
    except: return True

def sub_kb():
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("Тіркелу 🚀", url=CHANNEL_URL))
    kb.add(InlineKeyboardButton("Тіркелдім ✅", callback_data="check_subscription"))
    return kb

def main_kb(uid):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("🎬 Контент", "➕ Видео жіберу")
    kb.row("💰 Баланс", "👥 Реферал")
    kb.row("💎 Монета сатып алу")
    if uid == ADMIN_ID: kb.add("⚙️ Админ")
    return kb

# --- START & AUTO BONUS ---
@dp.message_handler(commands=['start'], state="*")
async def start(m: types.Message, state: FSMContext):
    await state.finish()
    uid = m.from_user.id
    ref = m.get_args()
    
    async with aiosqlite.connect(DB) as db:
        user = await (await db.execute("SELECT id FROM users WHERE id=?", (uid,))).fetchone()
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        if not user:
            await db.execute("INSERT INTO users(id, balance, last_bonus, last_active) VALUES (?,?,?,?)", 
                             (uid, 10, now, now))
            if ref and ref.isdigit() and int(ref) != uid:
                await db.execute("UPDATE users SET balance = balance + 6 WHERE id=?", (ref,))
                try: await bot.send_message(ref, "🔔 Реферал үшін +6 монета берілді!")
                except: pass
        await db.commit()

    if not await check_sub(uid):
        return await m.answer(f"👋 Сәлем! Ботты қолдану үшін каналға тіркеліңіз!", reply_markup=sub_kb())
    
    await m.answer("✅ Рұқсат берілді! Төмендегі мәзірді қолданыңыз:", reply_markup=main_kb(uid))

# --- AUTO NOTIFY & 24H BONUS (BACKGROUND TASK) ---
async def background_scheduler():
    while True:
        await asyncio.sleep(60) # Әр минут сайын тексеру
        now = datetime.now()
        async with aiosqlite.connect(DB) as db:
            async with db.execute("SELECT id, last_bonus, last_active FROM users") as cur:
                async for row in cur:
                    uid, l_bonus, l_active = row
                    
                    # 24 сағаттық бонус
                    lb_dt = datetime.strptime(l_bonus, "%Y-%m-%d %H:%M")
                    if now - lb_dt >= timedelta(hours=24):
                        await db.execute("UPDATE users SET balance = balance + 3, last_bonus = ? WHERE id = ?", 
                                         (now.strftime("%Y-%m-%d %H:%M"), uid))
                        try: await bot.send_message(uid, "🎁 Күнделікті бонус: +3 монета берілді!")
                        except: pass
                    
                    # 1 сағаттық ұятсыз уведомление
                    la_dt = datetime.strptime(l_active, "%Y-%m-%d %H:%M")
                    if now - la_dt >= timedelta(hours=1):
                        texts = ["🔥 Жаңа ыстық видеолар шықты, кіріп үлгер!", "🍌 Сенің жанрыңда жаңа нәрсе бар... Көргің келе ме?", "😏 Монеталарыңды босқа сақтама, нағыз қызық осында!"]
                        try: await bot.send_message(uid, random.choice(texts))
                        except: pass
                        await db.execute("UPDATE users SET last_active = ? WHERE id = ?", (now.strftime("%Y-%m-%d %H:%M"), uid))
            await db.commit()

# --- CONTENT SHOW ---
@dp.message_handler(lambda m: m.text == "🎬 Контент")
async def content_menu(m: types.Message):
    if not await check_sub(m.from_user.id): return await m.answer("❌ Тіркелу керек!", reply_markup=sub_kb())
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    for g in GENRES: kb.add(g)
    kb.add("🔙 Артқа")
    await m.answer("Жанр таңдаңыз:", reply_markup=kb)

@dp.message_handler(lambda m: m.text in GENRES)
async def get_video(m: types.Message):
    uid = m.from_user.id
    genre = m.text
    config = GENRES_CONFIG[genre]
    
    async with aiosqlite.connect(DB) as db:
        user = await (await db.execute("SELECT balance FROM users WHERE id=?", (uid,))).fetchone()
        if user[0] < config['price']:
            link = f"https://t.me/{BOT_USER.replace('@','')}/?start={uid}"
            return await m.answer(f"⚠️ Баланс жеткіліксіз!\n\nКөру құны: {config['price']} монета.\n"
                                f"Дос шақырып 6 монета ал немесе сатып ал.\n"
                                f"Сілтемең: <code>{link}</code>")

        # Көрмеген видеоны табу
        res = await db.execute("""SELECT id, file_id FROM content WHERE genre=? AND id NOT IN 
                                 (SELECT content_id FROM history WHERE user_id=?) ORDER BY id LIMIT 1""", (genre, uid))
        video = await res.fetchone()

        if not video: # Видео бітсе басынан бастау
            await db.execute("DELETE FROM history WHERE user_id=?", (uid,))
            res = await db.execute("SELECT id, file_id FROM content WHERE genre=? ORDER BY id LIMIT 1", (genre,))
            video = await res.fetchone()

        if video:
            await db.execute("UPDATE users SET balance = balance - ?, last_active = ? WHERE id=?", 
                             (config['price'], datetime.now().strftime("%Y-%m-%d %H:%M"), uid))
            await db.execute("INSERT INTO history VALUES (?,?)", (uid, video[0]))
            await db.commit()
            
            sent = await bot.send_video(uid, video[1], caption=f"Көру құны: {config['price']} монета")
            # 30 минуттан кейін өшіру
            asyncio.create_task(auto_delete(uid, sent.message_id, 1800))
        else:
            await m.answer("Бұл бөлімде әлі видео жоқ.")

async def auto_delete(chat_id, msg_id, sec):
    await asyncio.sleep(sec)
    try: await bot.delete_message(chat_id, msg_id)
    except: pass

# --- USER UPLOAD ---
@dp.message_handler(lambda m: m.text == "➕ Видео жіберу")
async def user_upload(m: types.Message):
    await UserStates.upload_genre.set()
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    for g in GENRES: kb.add(g)
    kb.add("🔙 Артқа")
    await m.answer("Қай жанрға видео жібересіз?", reply_markup=kb)

@dp.message_handler(state=UserStates.upload_genre)
async def user_up_g(m: types.Message, state: FSMContext):
    if m.text == "🔙 Артқа": 
        await state.finish()
        return await m.answer("Бас мәзір", reply_markup=main_kb(m.from_user.id))
    await state.update_data(g=m.text)
    await UserStates.upload_video.set()
    await m.answer("🎥 Видеоңызды жіберіңіз (Тек видео!):", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("🔙 Артқа"))

@dp.message_handler(content_types=['any'], state=UserStates.upload_video)
async def user_up_v(m: types.Message, state: FSMContext):
    if m.text == "🔙 Артқа": 
        await state.finish()
        return await m.answer("Бас мәзір", reply_markup=main_kb(m.from_user.id))
    if not m.video:
        await m.delete()
        return await m.answer("❌ Қате! Тек видео жіберу керек.")
    
    data = await state.get_data()
    async with aiosqlite.connect(DB) as db:
        await db.execute("INSERT INTO submissions(file_id, genre, user_id) VALUES (?,?,?)",
                         (m.video.file_id, data['g'], m.from_user.id))
        await db.commit()
    
    await m.answer("✅ Видеоңыз кетті, админ жауабын күтіңіз. Тағы жібересіз бе?")
    await m.delete() # Қолданушы жіберген видеоны өшіру

# --- ADMIN PANEL ---
@dp.message_handler(lambda m: m.text == "⚙️ Админ", user_id=ADMIN_ID)
async def admin_main(m: types.Message):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("➕ Видео қосу", "📩 Жіберілгендер")
    kb.row("💰 Монета беру", "📢 Рассылка")
    kb.row("📊 Статистика", "🔙 Артқа")
    await m.answer("👑 Админ панелі:", reply_markup=kb)

@dp.message_handler(lambda m: m.text == "📊 Статистика", user_id=ADMIN_ID)
async def admin_stat(m: types.Message):
    async with aiosqlite.connect(DB) as db:
        users_count = await (await db.execute("SELECT COUNT(*) FROM users")).fetchone()
        video_count = await (await db.execute("SELECT genre, COUNT(*) FROM content GROUP BY genre")).fetchall()
    
    txt = f"👥 Жалпы қолданушылар: {users_count[0]}\n\n🎬 Видеолар:\n"
    for v in video_count:
        txt += f"- {v[0]}: {v[1]} дана\n"
    await m.answer(txt)

@dp.message_handler(lambda m: m.text == "📩 Жіберілгендер", user_id=ADMIN_ID)
async def admin_subs(m: types.Message):
    async with aiosqlite.connect(DB) as db:
        rows = await (await db.execute("SELECT genre, COUNT(*), user_id FROM submissions GROUP BY genre")).fetchall()
    if not rows: return await m.answer("Бос...")
    
    kb = InlineKeyboardMarkup()
    for r in rows:
        kb.add(InlineKeyboardButton(f"{r[0]} ({r[1]}) | ID: {r[2]}", callback_data=f"adm_check_{r[0]}"))
    await m.answer("Жанр таңдап видеоларды көріңіз:", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data.startswith('adm_check_'), user_id=ADMIN_ID)
async def adm_v_show(c: types.CallbackQuery):
    genre = c.data.replace("adm_check_", "")
    async with aiosqlite.connect(DB) as db:
        v = await (await db.execute("SELECT id, file_id, user_id FROM submissions WHERE genre=? LIMIT 1", (genre,))).fetchone()
    if v:
        kb = InlineKeyboardMarkup().row(
            InlineKeyboardButton("✅ Қабылдау (+12)", callback_data=f"approve_{v[0]}"),
            InlineKeyboardButton("❌ Өшіру", callback_data=f"decline_{v[0]}")
        )
        await bot.send_video(c.message.chat.id, v[1], caption=f"Жанр: {genre}\nID: {v[2]}", reply_markup=kb)
    else: await c.answer("Видео таусылды")

@dp.callback_query_handler(lambda c: c.data.startswith(('approve_', 'decline_')), user_id=ADMIN_ID)
async def adm_v_action(c: types.CallbackQuery):
    action, sid = c.data.split('_')
    async with aiosqlite.connect(DB) as db:
        v = await (await db.execute("SELECT * FROM submissions WHERE id=?", (sid,))).fetchone()
        if action == "approve":
            await db.execute("INSERT INTO content(file_id, type, genre) VALUES (?,?,?)", (v[1], 'video', v[2]))
            await db.execute("UPDATE users SET balance = balance + 12 WHERE id=?", (v[3],))
            try: await bot.send_message(v[3], "🌟 Видеоңыз мақұлданды! Сізге +12 монета берілді.")
            except: pass
        await db.execute("DELETE FROM submissions WHERE id=?", (sid,))
        await db.commit()
    await c.message.delete()
    await c.answer("Орындалды")

# --- OTHER BUTTONS ---
@dp.message_handler(lambda m: m.text == "💰 Баланс")
async def show_bal(m: types.Message):
    async with aiosqlite.connect(DB) as db:
        u = await (await db.execute("SELECT balance FROM users WHERE id=?", (m.from_user.id,))).fetchone()
    await m.answer(f"💰 Сенің балансың: <b>{u[0]}</b> монета.\n\n"
                 f"24 сағат сайын +3 монета бонус беріледі! ✨")

@dp.message_handler(lambda m: m.text == "💎 Монета сатып алу")
async def buy_moneta(m: types.Message):
    await m.answer("💎 Монета сатып алу үшін администраторға жазыңыз:\n\n👉 @QzqMoneta")

@dp.message_handler(lambda m: m.text == "👥 Реферал")
async def show_ref(m: types.Message):
    link = f"https://t.me/{BOT_USER.replace('@','')}/?start={m.from_user.id}"
    await m.answer(f"👥 <b>Реферал жүйесі:</b>\n\nСенің сілтемеңмен тіркелген әр дос үшін <b>+6 монета</b> аласың!\n\n"
                 f"🔗 Сілтемең:\n<code>{link}</code>")

@dp.message_handler(lambda m: m.text == "🔙 Артқа", state="*")
async def back_to_main(m: types.Message, state: FSMContext):
    await state.finish()
    await m.answer("Бас мәзір", reply_markup=main_kb(m.from_user.id))

# --- RUN ---
if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(init_db())
    loop.create_task(background_scheduler())
    executor.start_polling(dp, skip_updates=True)
