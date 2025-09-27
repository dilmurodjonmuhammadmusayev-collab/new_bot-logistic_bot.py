import json
import asyncio
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

import gspread
from google.oauth2.service_account import Credentials

from aiogram import Bot, Dispatcher, F, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage

# ======================
# Config
# ======================
BOT_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"   # <-- Tokeningizni yozing
ADMIN_ID = 7514656282                   # <-- O'zingizning ID
ADMIN_USERNAME = "vodiylg"

SPREADSHEET_URL = "YOUR_SHEET_URL"      # <-- Google Sheet URL

# ======================
# Google Sheets setup
# ======================
def connect_sheets():
    creds_json = os.environ.get("GOOGLE_CREDENTIALS")
    if not creds_json:
        raise Exception("GOOGLE_CREDENTIALS environment variable topilmadi!")
    creds_dict = json.loads(creds_json)

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    client = gspread.authorize(creds)
    return client.open_by_url(SPREADSHEET_URL)

sh = connect_sheets()
try:
    parties_ws = sh.worksheet("parties")
    clients_ws = sh.worksheet("clients")
except:
    sh.add_worksheet("parties", 1, 5)
    sh.add_worksheet("clients", 1, 10)
    parties_ws = sh.worksheet("parties")
    clients_ws = sh.worksheet("clients")
    parties_ws.append_row(["code", "status"])
    clients_ws.append_row(["id", "party", "mesta", "kub", "kg", "destination", "date", "image"])

# ======================
# Data management
# ======================
def load_data():
    global clients, parties
    clients, parties = {}, {}

    parties_data = parties_ws.get_all_records()
    for row in parties_data:
        parties[row["code"]] = {"status": row["status"]}

    clients_data = clients_ws.get_all_records()
    for row in clients_data:
        clients[row["id"]] = {
            "party": row["party"],
            "mesta": row["mesta"],
            "kub": row["kub"],
            "kg": row["kg"],
            "destination": row["destination"],
            "date": row["date"],
            "image": row["image"]
        }

def save_party(code, status="Yangi"):
    parties_ws.append_row([code, status])
    load_data()

def delete_party(code):
    data = parties_ws.get_all_records()
    for idx, row in enumerate(data, start=2):
        if row["code"] == code:
            parties_ws.delete_rows(idx)
            break
    load_data()

def update_party_status(code, status):
    data = parties_ws.get_all_records()
    for idx, row in enumerate(data, start=2):
        if row["code"] == code:
            parties_ws.update_cell(idx, 2, status)
            break
    load_data()

def save_client(cid, data):
    clients_ws.append_row([
        cid, data["party"], data["mesta"], data["kub"], data["kg"],
        data["destination"], data["date"], data["image"]
    ])
    load_data()

def delete_client(cid):
    data = clients_ws.get_all_records()
    for idx, row in enumerate(data, start=2):
        if str(row["id"]) == str(cid):
            clients_ws.delete_rows(idx)
            break
    load_data()

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
    waiting_party = State()
    waiting_mesta = State()
    waiting_kub = State()
    waiting_kg = State()
    waiting_destination = State()
    waiting_date = State()
    waiting_image = State()

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
# Handlers
# ======================
@dp.message(F.text == "/start")
async def start_cmd(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        await message.answer("👋 Admin panelga xush kelibsiz!", reply_markup=admin_menu())
    else:
        await message.answer("👋 Xush kelibsiz!\nLogistika botga hush kelibsiz!", reply_markup=client_menu())

# -------- Client functions --------
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

# -------- Admin functions --------
@dp.message(F.text == "➕ Partiya qo'shish")
async def add_party_start(message: types.Message, state: FSMContext):
    await message.answer("✍️ Yangi partiya kodini kiriting:")
    await state.set_state(AddParty.waiting_code)

@dp.message(AddParty.waiting_code)
async def add_party_code(message: types.Message, state: FSMContext):
    code = message.text.strip()
    save_party(code)
    await message.answer(f"✅ Partiya qo‘shildi: {code}", reply_markup=admin_menu())
    await state.clear()

@dp.message(F.text == "➖ Partiya o'chirish")
async def delete_party_start(message: types.Message, state: FSMContext):
    await message.answer("✍️ O‘chiriladigan partiya kodini kiriting:")
    await state.set_state(DeleteParty.waiting_code)

@dp.message(DeleteParty.waiting_code)
async def delete_party_code(message: types.Message, state: FSMContext):
    code = message.text.strip()
    if code in parties:
        delete_party(code)
        await message.answer(f"✅ Partiya o‘chirildi: {code}", reply_markup=admin_menu())
    else:
        await message.answer("❌ Bunday partiya topilmadi")
    await state.clear()

@dp.message(F.text == "✏️ Partiya statusini yangilash")
async def update_status_start(message: types.Message, state: FSMContext):
    await message.answer("✍️ Statusini yangilash uchun partiya kodini kiriting:")
    await state.set_state(UpdatePartyStatus.waiting_code)

@dp.message(UpdatePartyStatus.waiting_code)
async def update_status_code(message: types.Message, state: FSMContext):
    await state.update_data(code=message.text.strip())
    await message.answer("✍️ Yangi statusni kiriting:")
    await state.set_state(UpdatePartyStatus.waiting_status)

@dp.message(UpdatePartyStatus.waiting_status)
async def update_status_finish(message: types.Message, state: FSMContext):
    data = await state.get_data()
    code = data["code"]
    status = message.text.strip()
    if code in parties:
        update_party_status(code, status)
        await message.answer(f"✅ {code} status yangilandi: {status}", reply_markup=admin_menu())
    else:
        await message.answer("❌ Bunday partiya topilmadi")
    await state.clear()

@dp.message(F.text == "👤 Mijoz qo'shish")
async def add_client_start(message: types.Message, state: FSMContext):
    await message.answer("✍️ Mijoz ID sini kiriting:")
    await state.set_state(AddClient.waiting_id)

@dp.message(AddClient.waiting_id)
async def add_client_id(message: types.Message, state: FSMContext):
    await state.update_data(id=message.text.strip())
    await message.answer("✍️ Partiya kodini kiriting:")
    await state.set_state(AddClient.waiting_party)

@dp.message(AddClient.waiting_party)
async def add_client_party(message: types.Message, state: FSMContext):
    await state.update_data(party=message.text.strip())
    await message.answer("✍️ Mesta sonini kiriting:")
    await state.set_state(AddClient.waiting_mesta)

@dp.message(AddClient.waiting_mesta)
async def add_client_mesta(message: types.Message, state: FSMContext):
    await state.update_data(mesta=message.text.strip())
    await message.answer("✍️ Kub hajmini kiriting:")
    await state.set_state(AddClient.waiting_kub)

@dp.message(AddClient.waiting_kub)
async def add_client_kub(message: types.Message, state: FSMContext):
    await state.update_data(kub=message.text.strip())
    await message.answer("✍️ Og‘irligini (kg) kiriting:")
    await state.set_state(AddClient.waiting_kg)

@dp.message(AddClient.waiting_kg)
async def add_client_kg(message: types.Message, state: FSMContext):
    await state.update_data(kg=message.text.strip())
    await message.answer("✍️ Manzilini kiriting:")
    await state.set_state(AddClient.waiting_destination)

@dp.message(AddClient.waiting_destination)
async def add_client_destination(message: types.Message, state: FSMContext):
    await state.update_data(destination=message.text.strip())
    await message.answer("✍️ Sanasini kiriting:")
    await state.set_state(AddClient.waiting_date)

@dp.message(AddClient.waiting_date)
async def add_client_date(message: types.Message, state: FSMContext):
    await state.update_data(date=message.text.strip())
    await message.answer("✍️ Yuk rasmi (URL) kiriting yoki o'tkazib yuboring:")
    await state.set_state(AddClient.waiting_image)

@dp.message(AddClient.waiting_image)
async def add_client_image(message: types.Message, state: FSMContext):
    data = await state.get_data()
    cid = data["id"]
    new_data = {
        "party": data["party"],
        "mesta": data["mesta"],
        "kub": data["kub"],
        "kg": data["kg"],
        "destination": data["destination"],
        "date": data["date"],
        "image": message.text.strip() if message.text else ""
    }
    save_client(cid, new_data)
    await message.answer(f"✅ Mijoz qo‘shildi: {cid}", reply_markup=admin_menu())
    await state.clear()

@dp.message(F.text == "➖ Mijozni o'chirish")
async def delete_client_start(message: types.Message, state: FSMContext):
    await message.answer("✍️ O‘chiriladigan mijoz ID sini kiriting:")
    await state.set_state(DeleteClient.waiting_code)

@dp.message(DeleteClient.waiting_code)
async def delete_client_code(message: types.Message, state: FSMContext):
    cid = message.text.strip()
    if cid in clients:
        delete_client(cid)
        await message.answer(f"✅ Mijoz o‘chirildi: {cid}", reply_markup=admin_menu())
    else:
        await message.answer("❌ Bunday mijoz topilmadi")
    await state.clear()

@dp.message(F.text == "📋 Barcha partiyalar")
async def list_parties(message: types.Message):
    if not parties:
        await message.answer("❌ Partiyalar mavjud emas")
        return
    text = "📋 Partiyalar:\n"
    for code, data in parties.items():
        text += f"- {code}: {data['status']}\n"
    await send_long_message(message.chat.id, text, bot)

@dp.message(F.text == "📋 Barcha mijozlar")
async def list_clients(message: types.Message):
    if not clients:
        await message.answer("❌ Mijozlar mavjud emas")
        return
    text = "📋 Mijozlar:\n"
    for cid, c in clients.items():
        text += f"- {cid}: {c['party']}, {c['mesta']}mesta, {c['kg']}kg\n"
    await send_long_message(message.chat.id, text, bot)

# ======================
# Run bot + dummy server (Render)
# ======================
async def run_bot():
    await dp.start_polling(bot)

async def run_server():
    PORT = int(os.environ.get("PORT", 10000))
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Bot is running on Render!")
    server = HTTPServer(("0.0.0.0", PORT), Handler)
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, server.serve_forever)

async def main():
    await asyncio.gather(run_bot(), run_server())

if __name__ == "__main__":
    asyncio.run(main())
