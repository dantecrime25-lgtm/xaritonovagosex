import asyncio
import json
import os
from typing import Optional, List, Dict

from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.enums import ChatType

DATA_FILE = "data.json"
BOT_TOKEN = os.getenv("BOT_TOKEN")  # укажи BOT_TOKEN в Secrets
OWNER_ID = 7322925570  # твой owner id

default_data = {
    "message": "Привет! Это автосообщение.",
    "interval_min": 10,
    "running": False,
    "chats": []  # [{"chat_id": int, "topic_id": Optional[int]}]
}


def load_data() -> Dict:
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    else:
        save_data(default_data)
        return default_data.copy()


def save_data(data: Dict):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


data = load_data()

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ----------------- УТИЛИТЫ -----------------
def owner_only(func):
    async def wrapper(message: Message):
        if message.from_user is None or message.from_user.id != OWNER_ID:
            return await message.answer("⛔ Доступ запрещён (только владелец).")
        return await func(message)
    return wrapper


def chat_repr(c: Dict) -> str:
    if c.get("topic_id"):
        return f"chat_id={c['chat_id']}, topic_id={c['topic_id']}"
    return f"chat_id={c['chat_id']} (без topic_id)"


# ----------------- ОТПРАВКА -----------------
sender_task: Optional[asyncio.Task] = None


async def sender_loop():
    try:
        while data.get("running"):
            interval = max(1, min(60, int(data.get("interval_min", 10))))
            text = data.get("message", "")
            chats: List[Dict] = data.get("chats", [])
            if text and chats:
                for c in chats:
                    try:
                        if c.get("topic_id"):
                            await bot.send_message(c["chat_id"], text, message_thread_id=c["topic_id"])
                        else:
                            await bot.send_message(c["chat_id"], text)
                    except Exception as e:
                        print(f"❌ Ошибка в {chat_repr(c)}: {e}")
            await asyncio.sleep(interval * 60)
    except asyncio.CancelledError:
        pass


async def start_sender():
    global sender_task
    if data.get("running") and (sender_task is None or sender_task.done()):
        sender_task = asyncio.create_task(sender_loop())


async def stop_sender():
    global sender_task
    if sender_task and not sender_task.done():
        sender_task.cancel()
        try:
            await sender_task
        except asyncio.CancelledError:
            pass
        sender_task = None


# ----------------- КОМАНДЫ -----------------
@dp.message(Command("start"))
async def cmd_start(message: Message):
    if message.chat.type == ChatType.PRIVATE and message.from_user.id != OWNER_ID:
        return
    await message.reply(
        "🤖 Я бот-автопостер.\n"
        "/setmessage <текст>\n"
        "/setinterval <1-60>\n"
        "/addchat <chat_id> [topic_id]\n"
        "/removechat <chat_id> [topic_id]\n"
        "/list — список чатов\n"
        "/startautopost — включить авторассылку\n"
        "/stopautopost — выключить авторассылку\n"
        "/sendnow — отправить сразу"
    )


@dp.message(Command("setmessage"))
@owner_only
async def cmd_setmessage(message: Message):
    args = message.get_args()
    if not args:
        return await message.reply("Использование: /setmessage <текст>")
    data["message"] = args
    save_data(data)
    await message.reply("✅ Текст обновлён.")


@dp.message(Command("setinterval"))
@owner_only
async def cmd_setinterval(message: Message):
    try:
        m = int(message.get_args())
        if not (1 <= m <= 60):
            raise ValueError
    except:
        return await message.reply("Интервал должен быть числом от 1 до 60.")
    data["interval_min"] = m
    save_data(data)
    await stop_sender()
    if data.get("running"):
        await start_sender()
    await message.reply(f"✅ Интервал установлен: {m} мин.")


@dp.message(Command("addchat"))
@owner_only
async def cmd_addchat(message: Message):
    args = message.get_args().split()
    if not args:
        return await message.reply("Использование: /addchat <chat_id> [topic_id]")
    chat_id = int(args[0])
    topic_id = int(args[1]) if len(args) > 1 else None
    entry = {"chat_id": chat_id, "topic_id": topic_id}
    if entry not in data["chats"]:
        data["chats"].append(entry)
        save_data(data)
        await message.reply(f"✅ Добавлен {chat_repr(entry)}")
    else:
        await message.reply("⚠️ Уже есть.")


@dp.message(Command("removechat"))
@owner_only
async def cmd_removechat(message: Message):
    args = message.get_args().split()
    if not args:
        return await message.reply("Использование: /removechat <chat_id> [topic_id]")
    chat_id = int(args[0])
    topic_id = int(args[1]) if len(args) > 1 else None
    before = len(data["chats"])
    data["chats"] = [c for c in data["chats"] if not (c["chat_id"] == chat_id and c.get("topic_id") == topic_id)]
    save_data(data)
    if len(data["chats"]) < before:
        await message.reply("✅ Удалён.")
    else:
        await message.reply("⚠️ Не найден.")


@dp.message(Command("list"))
@owner_only
async def cmd_list(message: Message):
    if not data["chats"]:
        return await message.reply("⚠️ Список пуст.")
    txt = "\n".join(f"- {chat_repr(c)}" for c in data["chats"])
    await message.reply(f"📋 Список чатов:\n{txt}")


@dp.message(Command("startautopost"))
@owner_only
async def cmd_startautopost(message: Message):
    data["running"] = True
    save_data(data)
    await start_sender()
    await message.reply("▶️ Авторассылка включена.")


@dp.message(Command("stopautopost"))
@owner_only
async def cmd_stopautopost(message: Message):
    data["running"] = False
    save_data(data)
    await stop_sender()
    await message.reply("⏹ Авторассылка выключена.")


@dp.message(Command("sendnow"))
@owner_only
async def cmd_sendnow(message: Message):
    text = data.get("message", "")
    chats: List[Dict] = data.get("chats", [])
    if not text or not chats:
        return await message.reply("⚠️ Нет текста или чатов.")
    for c in chats:
        try:
            if c.get("topic_id"):
                await bot.send_message(c["chat_id"], text, message_thread_id=c["topic_id"])
            else:
                await bot.send_message(c["chat_id"], text)
        except Exception as e:
            await message.reply(f"❌ Ошибка {chat_repr(c)}: {e}")
    await message.reply("✅ Сообщения отправлены.")


# ----------------- MAIN -----------------
async def main():
    print("🚀 Бот запущен")
    if data.get("running"):
        await start_sender()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
