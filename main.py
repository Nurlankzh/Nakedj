import asyncio
import logging
import aiosqlite
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.utils import executor
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.exceptions import BotBlocked, UserDeactivated, RetryAfter, TelegramAPIError

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
    "😍 Американша": {"price": 3},
    "😈 VIP Видео": {"price": 22}
}
GENRES = list(GENRES_CONFIG.keys())

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN, parse_mode="HTML")
dp = Dispatcher(bot, storage=MemoryStorage())

# --- STATES ---
class AdminStates(StatesGroup):
    give_id = State()
    give_amount = State()
    give_all_amount = State()
    broadcast_msg = State()
    add_v_genre = State()
    add_v_file = State()

class UserStates(StatesGroup):
    upload_genre = State()
    upload_video = State()

# --- DATABASE ---
async def init_db():
    async with aiosqlite.connect(DB) as db:
        await db.execute("""CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY, balance INTEGER DEFAULT 10, 
            last_bonus TEXT, last_active TEXT, vip_until TEXT)""")
        
        await db.execute("""CREATE TABLE IF NOT EXISTS content(
            id INTEGER PRIMARY KEY AUTOINCREMENT, file_id TEXT, 
            type TEXT, genre TEXT)""")
        
        await db.execute("""CREATE TABLE IF NOT EXISTS submissions(
            id INTEGER PRIMARY KEY AUTOINCREMENT, file_id TEXT, 
            genre TEXT, user_id INTEGER)""")
            
        await db.execute("""CREATE TABLE IF NOT EXISTS history(
            user_id INTEGER, content_id INTEGER)""")
            
        # Қайталанбас ID бағанын қосу (Дерекқор жаңаруы)
        try: await db.execute("ALTER TABLE content ADD COLUMN file_unique_id TEXT")
        except: pass
        try: await db.execute("ALTER TABLE submissions ADD COLUMN file_unique_id TEXT")
        except: pass
        
        # Іздеуді жылдамдату үшін индекс жасау
        await db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_content_uniq ON content(file_unique_id)")
        await db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_subs_uniq ON submissions(file_unique_id)")
        
        await db.commit()

# --- UTILS ---
async def check_sub(uid):
    try:
        member = await bot.get_chat_member(CHANNEL_ID, uid)
        return member.status != "left"
    except: return True

def sub_kb():
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("Тіркелу 🚀", url=CHANNEL_URL))
    kb.add(InlineKeyboardButton("Тіркелдім ✅", callback_data="check_subscription"))
    return kb

def main_kb(uid):
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add("🎬 Контент", "➕ Видео жіберу")
    kb.add("💰 Баланс", "👥 Реферал")
    kb.add("💎 Монета сатып алу", "🔐 VIP контент")
    if uid == ADMIN_ID: kb.add("⚙️ Админ")
    return kb

# --- GLOBAL BACK AND FINISH HANDLERS ---
@dp.message_handler(lambda m: m.text == "🔙 Артқа", state="*")
async def global_back(m: types.Message, state: FSMContext):
    await state.finish()
    await m.answer("Басты мәзірге қайттыңыз:", reply_markup=main_kb(m.from_user.id))

@dp.message_handler(lambda m: m.text == "✅ Аяқтау", state=[AdminStates.add_v_file, UserStates.upload_video])
async def finish_upload(m: types.Message, state: FSMContext):
    data = await state.get_data()
    added = data.get('added', 0)
    dupes = data.get('dupes', 0)
    
    msg = f"📊 <b>Жүктеу нәтижесі:</b>\n✅ Қабылданды: {added} видео\n❌ Қайталанған (өшірілді): {dupes} видео"
    if await state.get_state() == "UserStates:upload_video":
        msg += "\n\n<i>Видеолар админ мақұлдаған соң монета әкеледі.</i>"
        
    await m.answer(msg, reply_markup=main_kb(m.from_user.id))
    await state.finish()

# --- START ---
@dp.message_handler(commands=['start'], state="*")
async def start(m: types.Message, state: FSMContext):
    await state.finish()
    uid = m.from_user.id
    ref = m.get_args()
    
    async with aiosqlite.connect(DB) as db:
        user = await (await db.execute("SELECT id FROM users WHERE id=?", (uid,))).fetchone()
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        if not user:
            await db.execute("INSERT INTO users(id, balance, last_bonus, last_active, vip_until) VALUES (?,?,?,?,?)", 
                             (uid, 10, now, now, "None"))
            if ref and ref.isdigit() and int(ref) != uid:
                await db.execute("UPDATE users SET balance = balance + 6 WHERE id=?", (ref,))
                try: await bot.send_message(ref, "🔔 Реферал үшін +6 монета берілді!")
                except: pass
        await db.commit()

    if not await check_sub(uid):
        return await m.answer(f"👋 Сәлем! Ботты қолдану үшін каналға тіркеліңіз!", reply_markup=sub_kb())
    
    await m.answer("✅ Рұқсат берілді! Мәзірді қолданыңыз:", reply_markup=main_kb(uid))

@dp.callback_query_handler(lambda c: c.data == "check_subscription")
async def check_subscription_callback(c: types.CallbackQuery):
    if await check_sub(c.from_user.id):
        await c.message.delete()
        await bot.send_message(c.from_user.id, "✅ Тіркелу сәтті өтті!", reply_markup=main_kb(c.from_user.id))
    else:
        await c.answer("❌ Каналға тіркелмедіңіз!", show_alert=True)

# --- ADMIN: BULK ADD VIDEO ---
@dp.message_handler(lambda m: m.text == "➕ Видео қосу", user_id=ADMIN_ID)
async def add_v_start(m: types.Message):
    await AdminStates.add_v_genre.set()
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    for g in GENRES: kb.add(g)
    kb.add("🔙 Артқа")
    await m.answer("Қай жанрға видео қосасыз?", reply_markup=kb)

@dp.message_handler(state=AdminStates.add_v_genre, user_id=ADMIN_ID)
async def add_v_genre_pick(m: types.Message, state: FSMContext):
    if m.text not in GENRES: return await m.answer("Мәзірден таңдаңыз!")
    await state.update_data(genre=m.text, added=0, dupes=0)
    await AdminStates.add_v_file.set()
    kb = ReplyKeyboardMarkup(resize_keyboard=True).add("✅ Аяқтау").add("🔙 Артқа")
    await m.answer(f"[{m.text}] жанрына видеоларды жібере беріңіз (100-200 видео бірден жіберуге болады):", reply_markup=kb)

@dp.message_handler(state=AdminStates.add_v_file, content_types=['video'], user_id=ADMIN_ID)
async def add_v_file_save(m: types.Message, state: FSMContext):
    data = await state.get_data()
    uid = m.video.file_unique_id
    
    async with aiosqlite.connect(DB) as db:
        # Дубликат тексеру
        exists = await (await db.execute("SELECT id FROM content WHERE file_unique_id=?", (uid,))).fetchone()
        if exists:
            await state.update_data(dupes=data.get('dupes', 0) + 1)
            try: await m.delete()
            except: pass
            return
            
        await db.execute("INSERT INTO content(file_id, file_unique_id, type, genre) VALUES (?,?,?,?)", 
                         (m.video.file_id, uid, 'video', data['genre']))
        await db.commit()
    await state.update_data(added=data.get('added', 0) + 1)

# --- USER: BULK UPLOAD ---
@dp.message_handler(lambda m: m.text == "➕ Видео жіберу")
async def user_up_start(m: types.Message):
    await UserStates.upload_genre.set()
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    for g in GENRES:
        if "VIP" not in g: kb.add(g)
    kb.add("🔙 Артқа")
    await m.answer("Қай жанрға жібересіз?", reply_markup=kb)

@dp.message_handler(state=UserStates.upload_genre)
async def user_up_genre(m: types.Message, state: FSMContext):
    if m.text not in GENRES: return await m.answer("Мәзірден таңдаңыз!")
    await state.update_data(g=m.text, added=0, dupes=0)
    await UserStates.upload_video.set()
    kb = ReplyKeyboardMarkup(resize_keyboard=True).add("✅ Аяқтау").add("🔙 Артқа")
    await m.answer("🎥 Видеоларды жібере беріңіз (бірнешеуін бірден салуға болады):", reply_markup=kb)

@dp.message_handler(state=UserStates.upload_video, content_types=['video'])
async def user_up_file(m: types.Message, state: FSMContext):
    data = await state.get_data()
    uid = m.video.file_unique_id
    
    async with aiosqlite.connect(DB) as db:
        # Базада немесе кезекте бар-жоғын тексеру
        c1 = await (await db.execute("SELECT id FROM content WHERE file_unique_id=?", (uid,))).fetchone()
        c2 = await (await db.execute("SELECT id FROM submissions WHERE file_unique_id=?", (uid,))).fetchone()
        
        if c1 or c2:
            await state.update_data(dupes=data.get('dupes', 0) + 1)
            try: await m.delete()
            except: pass
            return
            
        await db.execute("INSERT INTO submissions(file_id, file_unique_id, genre, user_id) VALUES (?,?,?,?)",
                         (m.video.file_id, uid, data['g'], m.from_user.id))
        await db.commit()
    await state.update_data(added=data.get('added', 0) + 1)

# --- ADMIN: SUBMISSIONS ---
@dp.message_handler(lambda m: m.text == "📩 Жіберілгендер", user_id=ADMIN_ID)
async def adm_view_submissions(m: types.Message):
    async with aiosqlite.connect(DB) as db:
        rows = await (await db.execute("SELECT id, file_id, file_unique_id, genre, user_id FROM submissions")).fetchall()
    
    if not rows: return await m.answer("Жіберілген видеолар жоқ.")
    
    for row in rows:
        sid, fid, uniq_id, genre, uid = row
        kb = InlineKeyboardMarkup().row(
            InlineKeyboardButton("✅ Мақұлдау", callback_data=f"sub_ok_{sid}"),
            InlineKeyboardButton("❌ Өшіру", callback_data=f"sub_no_{sid}")
        )
        try:
            await bot.send_video(m.chat.id, fid, caption=f"👤 Кімнен: <code>{uid}</code>\n📂 Жанр: {genre}", reply_markup=kb)
        except: pass
        await asyncio.sleep(0.1)

@dp.callback_query_handler(lambda c: c.data.startswith(('sub_ok_', 'sub_no_')), user_id=ADMIN_ID)
async def sub_decision(c: types.CallbackQuery):
    action = c.data.split('_')[1]
    sid = c.data.split('_')[2]
    
    async with aiosqlite.connect(DB) as db:
        data = await (await db.execute("SELECT file_id, file_unique_id, genre, user_id FROM submissions WHERE id=?", (sid,))).fetchone()
        if not data: return await c.answer("Видео өңделіп қойған немесе табылмады", show_alert=True)
        
        fid, uniq_id, genre, uid = data[0], data[1], data[2], data[3]
        
        if action == "ok":
            await db.execute("INSERT OR IGNORE INTO content(file_id, file_unique_id, type, genre) VALUES (?,?,?,?)", 
                             (fid, uniq_id, 'video', genre))
            await db.execute("UPDATE users SET balance = balance + 12 WHERE id=?", (uid,))
            try: await bot.send_message(uid, "🌟 Видеоңыз мақұлданды! +12 монета берілді.")
            except: pass
        
        await db.execute("DELETE FROM submissions WHERE id=?", (sid,))
        await db.commit()
    await c.message.delete()
    await c.answer("Орындалды")

# --- ADMIN: BROADCAST (ANTI-BAN) ---
@dp.message_handler(lambda m: m.text == "📢 Рассылка", user_id=ADMIN_ID)
async def adm_broadcast_start(m: types.Message):
    await AdminStates.broadcast_msg.set()
    await m.answer("Жіберілетін текст немесе файлды жіберіңіз:", reply_markup=ReplyKeyboardMarkup(resize_keyboard=True).add("🔙 Артқа"))

@dp.message_handler(state=AdminStates.broadcast_msg, content_types=['any'], user_id=ADMIN_ID)
async def adm_broadcast_process(m: types.Message, state: FSMContext):
    async with aiosqlite.connect(DB) as db:
        users = await (await db.execute("SELECT id FROM users")).fetchall()
    
    count = 0
    await m.answer(f"Рассылка басталды... {len(users)} адамға.")
    for u in users:
        try:
            await m.copy_to(u[0])
            count += 1
            await asyncio.sleep(0.05) # Лимиттен аспау үшін
        except RetryAfter as e:
            await asyncio.sleep(e.timeout)
            try: await m.copy_to(u[0])
            except: pass
        except (BotBlocked, UserDeactivated):
            # Қалауыңызша мұнда блокқа салған адамдарды базадан өшіру логикасын қосуға болады
            pass
        except TelegramAPIError:
            pass
            
    await m.answer(f"✅ Рассылка {count} адамға сәтті жетті.", reply_markup=main_kb(m.from_user.id))
    await state.finish()

# --- ADMIN: OTHER TOOLS ---
@dp.message_handler(lambda m: m.text == "💰 Монета беру", user_id=ADMIN_ID)
async def adm_give_start(m: types.Message):
    await AdminStates.give_id.set()
    await m.answer("Пайдаланушының <b>ID</b> нөмірін жазыңыз:", reply_markup=ReplyKeyboardMarkup(resize_keyboard=True).add("🔙 Артқа"))

@dp.message_handler(state=AdminStates.give_id, user_id=ADMIN_ID)
async def adm_give_id(m: types.Message, state: FSMContext):
    if not m.text.isdigit(): return await m.answer("ID тек сандардан тұруы керек!")
    await state.update_data(target_id=m.text)
    await AdminStates.give_amount.set()
    await m.answer("Қанша монета бересіз?")

@dp.message_handler(state=AdminStates.give_amount, user_id=ADMIN_ID)
async def adm_give_amount(m: types.Message, state: FSMContext):
    if not m.text.isdigit(): return await m.answer("Сома тек сандардан тұруы керек!")
    data = await state.get_data()
    uid, amount = data['target_id'], int(m.text)
    
    async with aiosqlite.connect(DB) as db:
        await db.execute("UPDATE users SET balance = balance + ? WHERE id=?", (amount, uid))
        await db.commit()
    
    await m.answer(f"✅ ID: {uid} пайдаланушысына {amount} монета берілді!", reply_markup=main_kb(m.from_user.id))
    try: await bot.send_message(uid, f"🎁 Админ сізге {amount} монета берді!")
    except: pass
    await state.finish()

@dp.message_handler(lambda m: m.text == "🌍 Барлығына монета", user_id=ADMIN_ID)
async def adm_give_all_start(m: types.Message):
    await AdminStates.give_all_amount.set()
    await m.answer("Барлық адамға қанша монетадан бересіз?", reply_markup=ReplyKeyboardMarkup(resize_keyboard=True).add("🔙 Артқа"))

@dp.message_handler(state=AdminStates.give_all_amount, user_id=ADMIN_ID)
async def adm_give_all_process(m: types.Message, state: FSMContext):
    if not m.text.isdigit(): return await m.answer("Тек сан жазыңыз!")
    amount = int(m.text)
    async with aiosqlite.connect(DB) as db:
        await db.execute("UPDATE users SET balance = balance + ?", (amount,))
        await db.commit()
    await m.answer(f"✅ Барлық пайдаланушыларға {amount} монета берілді!", reply_markup=main_kb(m.from_user.id))
    await state.finish()

# --- VIP CONTENT ---
@dp.message_handler(lambda m: m.text == "🔐 VIP контент")
async def vip_access(m: types.Message):
    uid = m.from_user.id
    async with aiosqlite.connect(DB) as db:
        user = await (await db.execute("SELECT balance, vip_until FROM users WHERE id=?", (uid,))).fetchone()
    
    now = datetime.now()
    is_vip = False
    if user[1] != "None":
        if datetime.strptime(user[1], "%Y-%m-%d %H:%M") > now:
            is_vip = True
    
    if is_vip:
        kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
        kb.add("😈 VIP видео 😈", "🔙 Артқа")
        await m.answer(f"😈 <b>VIP МӘЗІР</b>\n\nСіздің VIP рұқсатыңыз белсенді!\nМерзімі: {user[1]} дейін.\n\n"
                       f"Бұл бөлімдегі видеоларды көру: 22 монета.", reply_markup=kb)
    else:
        kb = InlineKeyboardMarkup().add(InlineKeyboardButton("🔐 VIP Рұқсат сатып алу (50 монета)", callback_data="buy_vip"))
        text = (
            "🔐 <b>VIP КОНТЕНТКЕ КІРУ</b>\n\n"
            "Ереже: VIP бөлімге кіру үшін <b>50 монета</b> төлейсіз. Рұқсат <b>24 сағатқа</b> беріледі.\n"
            "24 сағаттан соң рұқсат автоматты түрде жойылады.\n\n"
            "😈 VIP ішіндегі видеолар құны: <b>22 монета</b>.\n\n"
            "🇷🇺 Самые горячие видео только здесь! Доступ на 24 часа.\n"
            "🇰🇿 Ең ыстық және эксклюзивті контенттер тек осында!"
        )
        await m.answer(text, reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data == "buy_vip")
async def buy_vip_callback(c: types.CallbackQuery):
    uid = c.from_user.id
    async with aiosqlite.connect(DB) as db:
        user = await (await db.execute("SELECT balance FROM users WHERE id=?", (uid,))).fetchone()
        if user[0] < 50:
            return await c.answer("❌ Баланста монета жеткіліксіз!", show_alert=True)
        
        vip_time = (datetime.now() + timedelta(hours=24)).strftime("%Y-%m-%d %H:%M")
        await db.execute("UPDATE users SET balance = balance - 50, vip_until = ? WHERE id=?", (vip_time, uid))
        await db.commit()
    
    await c.message.delete()
    await bot.send_message(uid, "✅ VIP рұқсат алынды! 24 сағатқа есік ашылды.", reply_markup=main_kb(uid))

# --- CONTENT SHOW ---
@dp.message_handler(lambda m: m.text in ["🎬 Контент", "😈 VIP видео 😈"])
async def content_menu(m: types.Message):
    if m.text == "😈 VIP видео 😈":
        m.text = "😈 VIP Видео"
        return await get_video(m)
        
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    for g in GENRES:
        if "VIP" not in g: kb.add(g)
    kb.add("🔙 Артқа")
    await m.answer("Жанр таңдаңыз:", reply_markup=kb)

@dp.message_handler(lambda m: m.text in GENRES)
async def get_video(m: types.Message):
    uid = m.from_user.id
    genre = m.text
    config = GENRES_CONFIG[genre]
    
    async with aiosqlite.connect(DB) as db:
        user = await (await db.execute("SELECT balance, vip_until FROM users WHERE id=?", (uid,))).fetchone()
        
        if "VIP" in genre:
            if user[1] == "None" or datetime.strptime(user[1], "%Y-%m-%d %H:%M") < datetime.now():
                return await m.answer("❌ VIP уақытыңыз біткен немесе сатып алмағансыз!")

        if user[0] < config['price']:
            return await m.answer(f"⚠️ Баланс жеткіліксіз! Құны: {config['price']} монета.")

        res = await db.execute("""SELECT id, file_id FROM content WHERE genre=? AND id NOT IN 
                                 (SELECT content_id FROM history WHERE user_id=?) ORDER BY RANDOM() LIMIT 1""", (genre, uid))
        video = await res.fetchone()

        if not video:
            await db.execute("DELETE FROM history WHERE user_id=?", (uid,))
            res = await db.execute("SELECT id, file_id FROM content WHERE genre=? ORDER BY RANDOM() LIMIT 1", (genre,))
            video = await res.fetchone()

        if video:
            await db.execute("UPDATE users SET balance = balance - ?, last_active = ? WHERE id=?", 
                             (config['price'], datetime.now().strftime("%Y-%m-%d %H:%M"), uid))
            await db.execute("INSERT INTO history VALUES (?,?)", (uid, video[0]))
            await db.commit()
            
            kb = InlineKeyboardMarkup().add(InlineKeyboardButton("Көру 😈 смотреть", callback_data="ignore"))
            sent = await bot.send_video(uid, video[1], caption=f"💰 Көру құны: {config['price']} монета", reply_markup=kb)
            asyncio.create_task(auto_delete(uid, sent.message_id, 1800))
        else:
            await m.answer("Бұл бөлімде видео жоқ.")

async def auto_delete(chat_id, msg_id, sec):
    await asyncio.sleep(sec)
    try: await bot.delete_message(chat_id, msg_id)
    except: pass

# --- ADMIN PANEL ---
@dp.message_handler(lambda m: m.text == "⚙️ Админ", user_id=ADMIN_ID)
async def admin_panel(m: types.Message):
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add("➕ Видео қосу", "📩 Жіберілгендер")
    kb.add("💰 Монета беру", "🌍 Барлығына монета")
    kb.add("📢 Рассылка", "📊 Статистика")
    kb.add("🔙 Артқа")
    await m.answer("👑 Админ панелі:", reply_markup=kb)

@dp.message_handler(lambda m: m.text == "📊 Статистика", user_id=ADMIN_ID)
async def stat_view(m: types.Message):
    async with aiosqlite.connect(DB) as db:
        uc = await (await db.execute("SELECT COUNT(*) FROM users")).fetchone()
        vc = await (await db.execute("SELECT genre, COUNT(*) FROM content GROUP BY genre")).fetchall()
    res = f"👥 Қолданушылар: {uc[0]}\n\n🎬 Видеолар:\n"
    for v in vc: res += f"- {v[0]}: {v[1]} дана\n"
    await m.answer(res)

# --- OTHER BUTTONS ---
@dp.message_handler(lambda m: m.text == "💰 Баланс")
async def show_balance(m: types.Message):
    async with aiosqlite.connect(DB) as db:
        u = await (await db.execute("SELECT balance FROM users WHERE id=?", (m.from_user.id,))).fetchone()
    await m.answer(f"💰 Сіздің балансыңыз: <b>{u[0]}</b> монета.")

@dp.message_handler(lambda m: m.text == "💎 Монета сатып алу")
async def buy_moneta_info(m: types.Message):
    await m.answer("💎 Монета сатып алу үшін: @QzqMoneta")

@dp.message_handler(lambda m: m.text == "👥 Реферал")
async def ref_info(m: types.Message):
    link = f"https://t.me/{BOT_USER.replace('@','')}/?start={m.from_user.id}"
    await m.answer(f"👥 Реферал жүйесі:\n\nДосыңыз сіздің сілтемеңізбен кірсе: <b>+6 монета</b> аласыз.\n\n🔗 Сілтемеңізіз:\n<code>{link}</code>")

# --- AUTO DELETE UNKNOWN TEXT ---
@dp.message_handler(content_types=['text'], state="*")
async def clean_chat(m: types.Message, state: FSMContext):
    curr_state = await state.get_state()
    if curr_state is not None: return
    
    buttons = ["🎬 Контент", "➕ Видео жіберу", "💰 Баланс", "👥 Реферал", "💎 Монета сатып алу", "⚙️ Админ", "🔐 VIP контент", "🔙 Артқа", "😈 VIP видео 😈", "✅ Аяқтау"]
    if m.text not in buttons and not m.text.startswith('/'):
        try: await m.delete()
        except: pass

# --- RUN ---
async def scheduler():
    while True:
        await asyncio.sleep(60)
        now = datetime.now()
        async with aiosqlite.connect(DB) as db:
            async with db.execute("SELECT id, last_bonus FROM users") as cur:
                async for row in cur:
                    uid, l_bonus = row
                    lb_dt = datetime.strptime(l_bonus, "%Y-%m-%d %H:%M")
                    if now - lb_dt >= timedelta(hours=24):
                        await db.execute("UPDATE users SET balance = balance + 3, last_bonus = ? WHERE id = ?", 
                                         (now.strftime("%Y-%m-%d %H:%M"), uid))
                        try: await bot.send_message(uid, "🎁 Күнделікті бонус: +3 монета берілді!")
                        except: pass
            await db.commit()

async def on_startup(dp):
    await init_db()
    asyncio.create_task(scheduler())
    print("Бот іске қосылды!")

if __name__ == "__main__":
    executor.start_polling(dp, on_startup=on_startup, skip_updates=True)
