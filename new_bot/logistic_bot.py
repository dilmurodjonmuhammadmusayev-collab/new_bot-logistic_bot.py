import json
import asyncio
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from aiogram import Bot, Dispatcher, F, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage

# ======================
# Config
# ======================
BOT_TOKEN = "8383894727:AAEM1-Z3LYhYFMUjTtMDk13F_NHyewDdKIA"
ADMIN_ID = 7514656282
ADMIN_USERNAME = "vodiylg"  # username, @ belgisiz

DATA_FILE = "data.json"

# ======================
# Data management
# ======================
def save_data():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump({"clients": clients, "parties": parties}, f, ensure_ascii=False, indent=4)

def load_data():
    global clients, parties
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            clients = data.get("clients", {})
            parties = data.get("parties", {})
    except FileNotFoundError:
        clients = {}
        parties = {}

clients = {}
parties = {}
load_data()

# ======================
# FSM States
# ======================
class ClientState(StatesGroup):
    waiting_party_code = State()
    waiting_client_code = State()

class AddClient(StatesGroup):
    waiting_id = State()
    waiting_mesta = State()
    waiting_kub = State()
    waiting_kg = State()
    waiting_destination = State()
    waiting_date = State()
    waiting_image = State()
    waiting_party = State()

class AddParty(StatesGroup):
    waiting_code = State()

class DeleteParty(StatesGroup):
    waiting_code = State()

class DeleteClient(StatesGroup):
    waiting_code = State()

class UpdatePartyStatus(StatesGroup):
    waiting_code = State()
    waiting_status = State()

# ======================
# Keyboards
# ======================
def client_menu():
    kb = [
        [KeyboardButton(text="🔍 Partiya bo‘yicha qidirish")],
        [KeyboardButton(text="🔍 Mijoz yukini tekshirish")],
        [KeyboardButton(text="📞 Admin bilan bog'lanish")],
        [KeyboardButton(text="ℹ️ Yordam")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def admin_menu():
    kb = [
        [KeyboardButton(text="➕ Partiya qo'shish"), KeyboardButton(text="➖ Partiya o'chirish")],
        [KeyboardButton(text="👤 Mijoz qo'shish"), KeyboardButton(text="➖ Mijozni o'chirish")],
        [KeyboardButton(text="✏️ Partiya statusini yangilash")],
        [KeyboardButton(text="📋 Barcha partiyalar"), KeyboardButton(text="📋 Barcha mijozlar")],
        [KeyboardButton(text="⬅️ Ortga")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

# ======================
# Helper
# ======================
async def send_long_message(chat_id: int, text: str, bot: Bot, chunk_size: int = 3000):
    for i in range(0, len(text), chunk_size):
        await bot.send_message(chat_id, text[i:i+chunk_size])

# ======================
# Bot & Dispatcher
# ======================
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# ======================
# Start
# ======================
@dp.message(F.text == "/start")
async def start_cmd(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        await message.answer("👋 Admin panelga xush kelibsiz!", reply_markup=admin_menu())
    else:
        await message.answer("👋 Xush kelibsiz!\nLogistika botga hush kelibsiz!", reply_markup=client_menu())

# ======================
# Client functions
# ======================
@dp.message(F.text == "🔍 Partiya bo‘yicha qidirish")
async def ask_party_code(message: types.Message, state: FSMContext):
    await message.answer("✍️ Partiya kodini kiriting (masalan: PP111):")
    await state.set_state(ClientState.waiting_party_code)

@dp.message(ClientState.waiting_party_code)
async def show_party_info(message: types.Message, state: FSMContext):
    code = message.text.strip()
    if code not in parties:
        await message.answer("❌ Bunday partiya topilmadi.\n✍️ Qayta urinib ko‘ring:")
        return
    p = parties[code]
    text = f"📦 Partiya: {code}\n📍 Status: {p['status']}"
    await message.answer(text, reply_markup=client_menu())
    await state.clear()

@dp.message(F.text == "🔍 Mijoz yukini tekshirish")
async def ask_client_code(message: types.Message, state: FSMContext):
    await message.answer("🔑 Mijoz kodini kiriting (masalan: 1111):")
    await state.set_state(ClientState.waiting_client_code)

@dp.message(ClientState.waiting_client_code)
async def show_client_info(message: types.Message, state: FSMContext):
    code = message.text.strip()
    if code not in clients:
        await message.answer("❌ Bunday mijoz topilmadi.")
        await state.clear()
        return

    c = clients[code]
    party = c["party"]
    status = parties.get(party, {}).get("status", "Noma’lum")
    text = (
        f"🆔 Kod: {code}\n"
        f"📦 Partiya: {party}\n"
        f"📍 Status: {status}\n"
        f"📦 Mesta: {c.get('mesta')}\n"
        f"📦 Kub: {c.get('kub')}\n"
        f"⚖️ Kg: {c.get('kg')}\n"
        f"🛣 Joy: {c.get('destination')}\n"
        f"📅 Vaqt: {c.get('date')}\n"
    )
    if c.get("image"):
        await message.answer_photo(c["image"], caption=text)
    else:
        await message.answer(text)
    await state.clear()

@dp.message(F.text == "📞 Admin bilan bog'lanish")
async def contact_admin(message: types.Message):
    await message.answer(f"📩 Admin bilan bog‘lanish uchun 👉 @{ADMIN_USERNAME}")

@dp.message(F.text == "ℹ️ Yordam")
async def help_info(message: types.Message):
    await message.answer(
        "ℹ️ Yordam:\n\n"
        "🔍 Partiya bo‘yicha qidirish — partiya kodini kiriting\n"
        "🔍 Mijoz yukini tekshirish — mijoz kodini kiriting\n"
        "📞 Admin bilan bog'lanish — admin bilan aloqa\n"
    )

# ======================
# Admin functions
# ======================
@dp.message(F.text == "➕ Partiya qo'shish")
async def add_party_start(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await message.answer("✍️ Yangi partiya kodini kiriting:")
    await state.set_state(AddParty.waiting_code)

@dp.message(AddParty.waiting_code)
async def add_party_save(message: types.Message, state: FSMContext):
    code = message.text.strip()
    if code in parties:
        await message.answer("❌ Bu partiya allaqachon mavjud.")
    else:
        parties[code] = {"status": "Yangi"}
        save_data()
        await message.answer(f"✅ Partiya {code} qo‘shildi.")
    await state.clear()

@dp.message(F.text == "➖ Partiya o'chirish")
async def delete_party_start(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await message.answer("🗑 Partiya kodini kiriting:")
    await state.set_state(DeleteParty.waiting_code)

@dp.message(DeleteParty.waiting_code)
async def delete_party_save(message: types.Message, state: FSMContext):
    code = message.text.strip()
    if code in parties:
        del parties[code]
        save_data()
        await message.answer(f"✅ Partiya {code} o‘chirildi.")
    else:
        await message.answer("❌ Bunday partiya topilmadi.")
    await state.clear()

@dp.message(F.text == "✏️ Partiya statusini yangilash")
async def update_party_status_start(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await message.answer("✍️ Partiya kodini kiriting:")
    await state.set_state(UpdatePartyStatus.waiting_code)

@dp.message(UpdatePartyStatus.waiting_code)
async def update_party_status_code(message: types.Message, state: FSMContext):
    code = message.text.strip()
    if code not in parties:
        await message.answer("❌ Bunday partiya topilmadi.")
        await state.clear()
        return
    await state.update_data(code=code)
    await message.answer("✍️ Yangi statusni kiriting:")
    await state.set_state(UpdatePartyStatus.waiting_status)

@dp.message(UpdatePartyStatus.waiting_status)
async def update_party_status_save(message: types.Message, state: FSMContext):
    data = await state.get_data()
    code = data["code"]
    status = message.text.strip()
    parties[code]["status"] = status
    save_data()
    await message.answer(f"✅ {code} partiya statusi yangilandi: {status}")
    await state.clear()

# --- Add Client ---
@dp.message(F.text == "👤 Mijoz qo'shish")
async def add_client_id(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await message.answer("🆔 Mijoz kodini kiriting:")
    await state.set_state(AddClient.waiting_id)

@dp.message(AddClient.waiting_id)
async def add_client_mesta(message: types.Message, state: FSMContext):
    await state.update_data(client_id=message.text.strip())
    await message.answer("📦 Mesta sonini kiriting:")
    await state.set_state(AddClient.waiting_mesta)

@dp.message(AddClient.waiting_mesta)
async def add_client_kub(message: types.Message, state: FSMContext):
    await state.update_data(mesta=message.text.strip())
    await message.answer("📦 Kub hajmini kiriting:")
    await state.set_state(AddClient.waiting_kub)

@dp.message(AddClient.waiting_kub)
async def add_client_kg(message: types.Message, state: FSMContext):
    await state.update_data(kub=message.text.strip())
    await message.answer("⚖️ Kg ni kiriting:")
    await state.set_state(AddClient.waiting_kg)

@dp.message(AddClient.waiting_kg)
async def add_client_destination(message: types.Message, state: FSMContext):
    await state.update_data(kg=message.text.strip())
    await message.answer("🛣 Boradigan joyini kiriting:")
    await state.set_state(AddClient.waiting_destination)

@dp.message(AddClient.waiting_destination)
async def add_client_date(message: types.Message, state: FSMContext):
    await state.update_data(destination=message.text.strip())
    await message.answer("📅 Vaqtni kiriting:")
    await state.set_state(AddClient.waiting_date)

@dp.message(AddClient.waiting_date)
async def add_client_image(message: types.Message, state: FSMContext):
    await state.update_data(date=message.text.strip())
    await message.answer("🖼 Yuk rasmini yuboring:")
    await state.set_state(AddClient.waiting_image)

@dp.message(AddClient.waiting_image, F.photo)
async def add_client_party(message: types.Message, state: FSMContext):
    await state.update_data(image=message.photo[-1].file_id)
    await message.answer("✍️ Qaysi partiyaga qo‘shiladi? Kodini kiriting:")
    await state.set_state(AddClient.waiting_party)

@dp.message(AddClient.waiting_party)
async def add_client_save(message: types.Message, state: FSMContext):
    data = await state.get_data()
    code = data["client_id"]

    clients[code] = {
        "party": message.text.strip(),
        "mesta": data["mesta"],
        "kub": data["kub"],
        "kg": data["kg"],
        "destination": data["destination"],
        "date": data["date"],
        "image": data["image"],
    }
    save_data()
    await message.answer(f"✅ Mijoz {code} qo‘shildi.", reply_markup=admin_menu())
    await state.clear()

# --- Delete Client ---
@dp.message(F.text == "➖ Mijozni o'chirish")
async def delete_client_start(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await message.answer("🗑 Mijoz kodini kiriting:")
    await state.set_state(DeleteClient.waiting_code)

@dp.message(DeleteClient.waiting_code)
async def delete_client_save(message: types.Message, state: FSMContext):
    code = message.text.strip()
    if code in clients:
        del clients[code]
        save_data()
        await message.answer(f"✅ Mijoz {code} o‘chirildi.")
    else:
        await message.answer("❌ Bunday mijoz topilmadi.")
    await state.clear()

# --- Show all ---
@dp.message(F.text == "📋 Barcha partiyalar")
async def all_parties_admin(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    if not parties:
        await message.answer("📦 Partiyalar mavjud emas.")
        return
    text = "📋 Barcha partiyalar:\n\n"
    for p, pdata in parties.items():
        text += f"▫️ {p} — {pdata['status']}\n"
    await message.answer(text)

@dp.message(F.text == "📋 Barcha mijozlar")
async def all_clients_admin(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    if not clients:
        await message.answer("👤 Mijozlar mavjud emas.")
        return

    text = "📋 Barcha mijozlar:\n\n"
    for c, cdata in clients.items():
        text += (
            f"🆔 Kod: {c}\n"
            f"📦 Partiya: {cdata.get('party')}\n"
            f"📦 Mesta: {cdata.get('mesta')}\n"
            f"📦 Kub: {cdata.get('kub')}\n"
            f"⚖️ Kg: {cdata.get('kg')}\n"
            f"🛣 Joy: {cdata.get('destination')}\n"
            f"📅 Vaqt: {cdata.get('date')}\n\n"
        )

    await send_long_message(message.chat.id, text, bot)

# ======================
# Run
# ======================
async def main():
    await dp.start_polling(bot)

def run_bot():
    asyncio.run(main())

# Botni alohida oqimda ishga tushiramiz
threading.Thread(target=run_bot).start()

# Render uchun dummy web server
PORT = int(os.environ.get("PORT", 10000))

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running on Render!")

server = HTTPServer(("0.0.0.0", PORT), Handler)
print(f"Starting dummy server on port {PORT}...")
server.serve_forever()
