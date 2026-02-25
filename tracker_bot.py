import asyncio
from datetime import datetime

from aiogram import Bot, Dispatcher, Router
from aiogram.filters import Command
from aiogram.types import Message
from telethon import TelegramClient, events
from telethon.tl.types import UserStatusOnline, UserStatusOffline

# ─── Настройки ────────────────────────────────────────────────────────────────
# Получить на https://my.telegram.org (раздел API development tools)
API_ID = 0            # Вставьте ваш api_id (число)
API_HASH = ""         # Вставьте ваш api_hash (строка)

# Токен бота от @BotFather
BOT_TOKEN = ""

# Ваш Telegram Chat ID (узнать через @userinfobot)
MY_CHAT_ID = 0

# Список юзернеймов для отслеживания (без @)
TRACK_USERS = ["username1", "username2"]
# ──────────────────────────────────────────────────────────────────────────────

# Хранение состояния
last_status: dict[str, bool | None] = {}   # username -> True=online, False=offline, None=unknown
tracking_paused = False

# Telethon клиент (сессия сохраняется в tracker.session)
client = TelegramClient("tracker", API_ID, API_HASH)

# aiogram бот
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)


# ─── Вспомогательные функции ──────────────────────────────────────────────────

def _now() -> str:
    """Текущее время в формате HH:MM:SS."""
    return datetime.now().strftime("%H:%M:%S")


async def _get_display_name(username: str) -> str:
    """Возвращает имя пользователя для уведомления."""
    try:
        entity = await client.get_entity(username)
        parts = [entity.first_name or "", entity.last_name or ""]
        name = " ".join(p for p in parts if p).strip()
        return name or username
    except Exception:
        return username


async def _check_access(message: Message) -> bool:
    """Проверяет, что сообщение от владельца бота."""
    if message.from_user.id != MY_CHAT_ID:
        return False
    return True


# ─── Telethon: обработчик событий ─────────────────────────────────────────────

@client.on(events.UserUpdate)
async def on_user_update(event: events.UserUpdate.Event) -> None:
    if tracking_paused:
        return

    try:
        user = await event.get_user()
    except Exception:
        return

    if user is None or not user.username:
        return

    username = user.username.lower()
    tracked = {u.lower() for u in TRACK_USERS}
    if username not in tracked:
        return

    status = event.status
    if isinstance(status, UserStatusOnline):
        is_online = True
    elif isinstance(status, UserStatusOffline):
        is_online = False
    else:
        return

    # Не дублировать уведомления
    if last_status.get(username) == is_online:
        return
    last_status[username] = is_online

    name = await _get_display_name(username)
    time_str = _now()
    if is_online:
        text = f"✅ {name} — зашёл в сеть 🕐 {time_str}"
    else:
        text = f"⛔ {name} — вышел из сети 🕐 {time_str}"

    await bot.send_message(MY_CHAT_ID, text)


# ─── aiogram: команды ─────────────────────────────────────────────────────────

@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    if not await _check_access(message):
        return
    await message.answer(
        "👋 Привет! Я трекер онлайн-статусов Telegram.\n\n"
        "📋 Команды:\n"
        "/status — текущий статус всех отслеживаемых\n"
        "/list — список отслеживаемых пользователей\n"
        "/add username — добавить пользователя\n"
        "/remove username — убрать пользователя\n"
        "/pause — приостановить мониторинг\n"
        "/resume — возобновить мониторинг"
    )


@router.message(Command("status"))
async def cmd_status(message: Message) -> None:
    if not await _check_access(message):
        return
    if not TRACK_USERS:
        await message.answer("📭 Список отслеживаемых пуст.")
        return
    lines = []
    for username in TRACK_USERS:
        state = last_status.get(username.lower())
        if state is True:
            icon = "🟢 онлайн"
        elif state is False:
            icon = "🔴 оффлайн"
        else:
            icon = "⚪ неизвестно"
        lines.append(f"@{username} — {icon}")
    pause_note = "\n\n⏸ Мониторинг приостановлен." if tracking_paused else ""
    await message.answer("📊 Текущий статус:\n" + "\n".join(lines) + pause_note)


@router.message(Command("list"))
async def cmd_list(message: Message) -> None:
    if not await _check_access(message):
        return
    if not TRACK_USERS:
        await message.answer("📭 Список отслеживаемых пуст.")
        return
    users = "\n".join(f"• @{u}" for u in TRACK_USERS)
    await message.answer(f"👥 Отслеживаемые пользователи ({len(TRACK_USERS)}):\n{users}")


@router.message(Command("add"))
async def cmd_add(message: Message) -> None:
    if not await _check_access(message):
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("❗ Использование: /add username")
        return
    username = parts[1].lstrip("@").strip()
    if not username:
        await message.answer("❗ Укажите юзернейм.")
        return
    if username.lower() in {u.lower() for u in TRACK_USERS}:
        await message.answer(f"ℹ️ @{username} уже в списке.")
        return
    TRACK_USERS.append(username)
    await message.answer(f"✅ @{username} добавлен в отслеживание.")


@router.message(Command("remove"))
async def cmd_remove(message: Message) -> None:
    if not await _check_access(message):
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("❗ Использование: /remove username")
        return
    username = parts[1].lstrip("@").strip()
    if not username:
        await message.answer("❗ Укажите юзернейм.")
        return
    lower = username.lower()
    match = next((u for u in TRACK_USERS if u.lower() == lower), None)
    if match is None:
        await message.answer(f"ℹ️ @{username} не найден в списке.")
        return
    TRACK_USERS.remove(match)
    last_status.pop(lower, None)
    await message.answer(f"✅ @{username} удалён из отслеживания.")


@router.message(Command("pause"))
async def cmd_pause(message: Message) -> None:
    if not await _check_access(message):
        return
    global tracking_paused
    tracking_paused = True
    await message.answer("⏸ Мониторинг приостановлен.")


@router.message(Command("resume"))
async def cmd_resume(message: Message) -> None:
    if not await _check_access(message):
        return
    global tracking_paused
    tracking_paused = False
    await message.answer("▶️ Мониторинг возобновлён.")


# ─── Точка входа ──────────────────────────────────────────────────────────────

async def main() -> None:
    # Подключить Telethon клиент
    await client.start()

    # Инициализировать статусы отслеживаемых пользователей
    for username in TRACK_USERS:
        last_status[username.lower()] = None

    # Уведомить владельца о запуске
    await bot.send_message(
        MY_CHAT_ID,
        f"🚀 Трекер запущен! Отслеживаю: {len(TRACK_USERS)} чел."
    )

    # Запустить polling бота и Telethon клиент параллельно
    await asyncio.gather(
        dp.start_polling(bot),
        client.run_until_disconnected(),
    )


if __name__ == "__main__":
    asyncio.run(main())
