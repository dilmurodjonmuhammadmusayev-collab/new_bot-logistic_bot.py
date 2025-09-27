# main.py
# Render-da web service/worker sifatida ishlash uchun moslangan logistic bot
# Aiogram 3.13.1 + gspread (Google service account) bilan ishlaydi.

import os
import json
import asyncio
import logging
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Dict, Any

import gspread
from google.oauth2.service_account import Credentials

from aiogram import Bot, Dispatcher, F, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage

# ---------- Logging ----------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("logistic-bot")

# ---------- Env / Config ----------
# These MUST be provided as Environment Variables (Render: Environment Variables section)
BOT_TOKEN = os.getenv("BOT_TOKEN") or ""
ADMIN_IDS_ENV = os.getenv("ADMIN_IDS", "").strip()  # e.g. "12345,67890"
SPREADSHEET_URL = os.getenv("SPREADSHEET_URL") or os.getenv("API_URL")  # prefer SPREADSHEET_URL, fallback API_URL
GOOGLE_CREDENTIALS = os.getenv("GOOGLE_CREDENTIALS")  # one-line JSON with \\n in private_key

if not BOT_TOKEN:
    logger.error("BOT_TOKEN environment variable topilmadi. Iltimos BOT_TOKEN ni qo'ying.")
    raise SystemExit("BOT_TOKEN environment variable required")

if not (SPREADSHEET_URL):
    logger.error("SPREADSHEET_URL (yoki API_URL) environment variable topilmadi.")
    raise SystemExit("SPREADSHEET_URL (or API_URL) environment variable required")

# Parse admin ids into set of strings for comparison
ADMIN_IDS = {s.strip() for s in ADMIN_IDS_ENV.split(",") if s.strip()}

# ---------- Google Sheets connection helper ----------
def load_google_creds_from_env(env_value: str) -> Dict[str, Any]:
    """
    env_value expected to be a JSON string (single-line) like:
    {"type":"service_account",...,"private_key":"-----BEGIN PRIVATE KEY-----\\nMIIE...\\n-----END PRIVATE KEY-----\\n",...}
    json.loads will convert \\n into actual newline characters in the string.
    """
    if not env_value:
        raise ValueError("GOOGLE_CREDENTIALS environment variable is empty or not provided.")
    # Try load directly
    try:
        creds_dict = json.loads(env_value)
        return creds_dict
    except json.JSONDecodeError:
        # Maybe the value was pasted with surrounding quotes accidentally (") or with newlines.
        # Try some common fixes:
        cleaned = env_value.strip()
        # If value starts/ends with single quotes remove them
        if cleaned.startswith("'") and cleaned.endswith("'"):
            cleaned = cleaned[1:-1]
        if cleaned.startswith('"') and cleaned.endswith('"'):
            cleaned = cleaned[1:-1]
        # Try replace literal \n escapes (if someone turned them into actual backslashes)
        try:
            creds_dict = json.loads(cleaned)
            return creds_dict
        except json.JSONDecodeError as e:
            # As last resort try replacing actual newline characters with \n escapes then load
            # (unlikely needed). Raise informative error.
            raise ValueError(
                "GOOGLE_CREDENTIALS JSON parse failed. "
                "Ensure you pasted a valid single-line JSON with escaped newlines (\\n) in private_key."
            ) from e

def connect_sheets():
    creds_json = GOOGLE_CREDENTIALS
    if not creds_json:
        raise Exception("GOOGLE_CREDENTIALS environment variable topilmadi!")

    # Parse JSON from environment (this will convert \\n into real newline chars in private_key)
    creds_dict = load_google_creds_from_env(creds_json)

    # Required scopes for sheets + drive
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    client = gspread.authorize(creds)
    # open_by_url expects the spreadsheet URL like https://docs.google.com/spreadsheets/d/<ID>/...
    sh = client.open_by_url(SPREADSHEET_URL)
    return sh

# ---------- Initialize Google Sheets ----------

sh = connect_sheets()

# Ensure worksheets exist
def ensure_worksheets():
    try:
        parties_ws = sh.worksheet("parties")
        clients_ws = sh.worksheet("clients")
    except Exception:
        # create if not exists
        try:
            sh.add_worksheet("parties", 100, 10)
        except Exception:
            pass
        try:
            sh.add_worksheet("clients", 100, 20)
        except Exception:
            pass
        parties_ws = sh.worksheet("parties")
        clients_ws = sh.worksheet("clients")
    return parties_ws, clients_ws

parties_ws, clients_ws = ensure_worksheets()

# If header is missing, initialize headers (safe)
def ensure_headers():
    try:
        parties_data = parties_ws.get_all_records()
        clients_data = clients_ws.get_all_records()
    except Exception:
        parties_ws.clear()
        clients_ws.clear()
        parties_ws.append_row(["code", "status"])
        clients_ws.append_row(["id", "party", "mesta", "kub", "kg", "destination", "date", "image"])
        return

    # If empty or missing keys, set headers
    if not parties_data:
        # check first row values
        parties_ws.clear()
        parties_ws.append_row(["code", "status"])
    if not clients_data:
        clients_ws.clear()
        clients_ws.append_row(["id", "party", "mesta", "kub", "kg", "destination", "date", "image"])

ensure_headers()

# ---------- Data management (in-memory cache) ----------
clients = {}
parties = {}

def load_data():
    global clients, parties
    clients = {}
    parties = {}
    try:
        parties_data = parties_ws.get_all_records()
        for row in parties_data:
            key = str(row.get("code", "")).strip()
            if not key:
                continue
            parties[key] = {"status": row.get("status", "")}
    except Exception as e:
        logger.exception("Error reading parties sheet: %s", e)

    try:
        clients_data = clients_ws.get_all_records()
        for row in clients_data:
            cid = str(row.get("id", "")).strip()
            if not cid:
                continue
            clients[cid] = {
                "party": row.get("party", ""),
                "mesta": row.get("mesta", ""),
                "kub": row.get("kub", ""),
                "kg": row.get("kg", ""),
                "destination": row.get("destination", ""),
                "date": row.get("date", ""),
                "image": row.get("image", "")
            }
    except Exception as e:
        logger.exception("Error reading clients sheet: %s", e)

# Initial load
load_data()

# ---------- Sheets write helpers ----------
def save_party(code, status="Yangi"):
    try:
        parties_ws.append_row([code, status])
        load_data()
    except Exception as e:
        logger.exception("Failed to save_party: %s", e)

def delete_party(code):
    try:
        data = parties_ws.get_all_records()
        # find row index (data rows start at row 2 in sheet)
        for idx, row in enumerate(data, start=2):
            if str(row.get("code", "")) == str(code):
                parties_ws.delete_rows(idx)
                break
        load_data()
    except Exception as e:
        logger.exception("Failed to delete_party: %s", e)

def update_party_status(code, status):
    try:
        data = parties_ws.get_all_records()
        for idx, row in enumerate(data, start=2):
            if str(row.get("code", "")) == str(code):
                parties_ws.update_cell(idx, 2, status)
                break
        load_data()
    except Exception as e:
        logger.exception("Failed to update_party_status: %s", e)

def save_client(cid, data: dict):
    try:
        clients_ws.append_row([
            cid,
            data.get("party", ""),
            data.get("mesta", ""),
            data.get("kub", ""),
            data.get("kg", ""),
            data.get("destination", ""),
            data.get("date", ""),
            data.get("image", "")
        ])
        load_data()
    except Exception as e:
        logger.exception("Failed to save_client: %s", e)

def delete_client(cid):
    try:
        data = clients_ws.get_all_records()
        for idx, row in enumerate(data, start=2):
            if str(row.get("id", "")) == str(cid):
                clients_ws.delete_rows(idx)
                break
        load_data()
    except Exception as e:
        logger.exception("Failed to delete_client: %s", e)

# ---------- FSM States ----------
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

# ---------- Keyboards ----------
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

# ---------- Helper ----------
async def send_long_message(chat_id: int, text: str, bot: Bot, chunk_size: int = 3000):
    for i in range(0, len(text), chunk_size):
        await bot.send_message(chat_id, text[i:i+chunk_size])

# ---------- Bot init ----------
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# ---------- Handlers ----------
@dp.message(F.text == "/start")
async def start_cmd(message: types.Message):
    user_id_str = str(message.from_user.id)
    if user_id_str in ADMIN_IDS:
        await message.answer("👋 Admin panelga xush kelibsiz!", reply_markup=admin_menu())
    else:
        await message.answer("👋 Xush kelibsiz!\nLogistika botga hush kelibsiz!", reply_markup=client_menu())

# Client handlers
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
    text = f"📦 Partiya: {code}\n📍 Status: {p.get('status','')}"
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
    party = c.get("party")
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
        try:
            await message.answer_photo(c.get("image"), caption=text)
        except Exception:
            await message.answer(text)
    else:
        await message.answer(text)
    await state.clear()

@dp.message(F.text == "📞 Admin bilan bog'lanish")
async def contact_admin(message: types.Message):
    # show admin contact. if you want username, set ADMIN_IDS env to include it or hardcode
    await message.answer("📩 Admin bilan bog‘lanish uchun adminga murojaat qiling.")

@dp.message(F.text == "ℹ️ Yordam")
async def help_info(message: types.Message):
    await message.answer(
        "ℹ️ Yordam:\n\n"
        "🔍 Partiya bo‘yicha qidirish — partiya kodini kiriting\n"
        "🔍 Mijoz yukini tekshirish — mijoz kodini kiriting\n"
        "📞 Admin bilan bog'lanish — admin bilan aloqa\n"
    )

# Admin handlers
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
        text += f"- {code}: {data.get('status','')}\n"
    await send_long_message(message.chat.id, text, bot)

@dp.message(F.text == "📋 Barcha mijozlar")
async def list_clients(message: types.Message):
    if not clients:
        await message.answer("❌ Mijozlar mavjud emas")
        return
    text = "📋 Mijozlar:\n"
    for cid, c in clients.items():
        text += f"- {cid}: {c.get('party','')}, {c.get('mesta','')}mesta, {c.get('kg','')}kg\n"
    await send_long_message(message.chat.id, text, bot)

# Run bot + http server for Render ping
async def run_bot():
    logger.info("Starting aiogram polling")
    await dp.start_polling(bot)

async def run_server():
    PORT = int(os.environ.get("PORT", "10000"))
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Bot is running on Render!")
    server = HTTPServer(("0.0.0.0", PORT), Handler)
    loop = asyncio.get_event_loop()
    # run server forever in threadpool
    await loop.run_in_executor(None, server.serve_forever)

async def main():
    # reload data from sheets periodically in background
    async def reload_loop():
        while True:
            try:
                load_data()
            except Exception as e:
                logger.exception("Error loading data: %s", e)
            await asyncio.sleep(60)  # reload each 60 seconds

    await asyncio.gather(run_bot(), run_server(), reload_loop())

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Shutting down")

