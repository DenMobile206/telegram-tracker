import asyncio
from datetime import datetime

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from telethon import TelegramClient, events
from telethon.tl.functions.users import GetUsersRequest
from telethon.tl.types import InputUser, UpdateUserStatus, UserStatusOnline, UserStatusOffline

# ========================
# Настройки
# ========================
API_ID = 12345678              # Получить на my.telegram.org
API_HASH = 'your_api_hash'    # Получить на my.telegram.org
BOT_TOKEN = '7123456789:AAH1bGc_someRandomString123'  # От @BotFather
MY_CHAT_ID = 123456789         # Узнать через @userinfobot
TRACK_USERS = ['username1', 'username2']  # Юзернеймы без @

# ========================
# Инициализация
# ========================
client = TelegramClient('tracker_session', API_ID, API_HASH)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Состояние
last_status: dict[str, bool | None] = {}  # username -> True (онлайн) / False (оффлайн) / None (неизвестно)
tracking_users: list[str] = list(TRACK_USERS)
paused = False


def now_time() -> str:
    return datetime.now().strftime('%H:%M:%S')


# ========================
# Telethon: отслеживание статусов
# ========================
@client.on(events.UserUpdate)
async def user_update_handler(event):
    if paused:
        return

    # event.online может быть True, False или None
    if event.online is None:
        return

    try:
        user = await event.get_user()
    except Exception:
        return

    username = (user.username or '').lower()
    if username not in [u.lower() for u in tracking_users]:
        return

    name = user.first_name or username
    is_online = event.online

    prev = last_status.get(username)
    if prev == is_online:
        return

    last_status[username] = is_online

    if is_online:
        text = f'✅ {name} — зашёл в сеть 🕐 {now_time()}'
    else:
        text = f'⛔ {name} — вышел из сети 🕐 {now_time()}'

    await bot.send_message(MY_CHAT_ID, text)


@client.on(events.Raw(types=[UpdateUserStatus]))
async def raw_status_handler(update):
    if paused:
        return

    user_id = update.user_id
    status = update.status

    try:
        user = await client.get_entity(user_id)
    except Exception:
        return

    username = (user.username or '').lower()
    if username not in [u.lower() for u in tracking_users]:
        return

    name = user.first_name or username

    if isinstance(status, UserStatusOnline):
        is_online = True
    elif isinstance(status, UserStatusOffline):
        is_online = False
    else:
        return

    prev = last_status.get(username)
    if prev == is_online:
        return

    last_status[username] = is_online

    if is_online:
        text = f'✅ {name} — зашёл в сеть 🕐 {now_time()}'
    else:
        text = f'⛔ {name} — вышел из сети 🕐 {now_time()}'

    await bot.send_message(MY_CHAT_ID, text)


# ========================
# Вспомогательная функция: получить текущий статус пользователя
# ========================
async def get_user_status(username: str) -> str:
    try:
        entity = await client.get_entity(username)
        # Принудительно запросить свежий статус
        result = await client(GetUsersRequest(id=[entity.id]))
        if not result:
            return f'❓ @{username} — не удалось получить данные'
        user = result[0]
        name = user.first_name or username
        status = user.status
        if isinstance(status, UserStatusOnline):
            return f'🟢 {name} (@{username}) — онлайн'
        elif isinstance(status, UserStatusOffline):
            last_seen = status.was_online.strftime('%d.%m.%Y %H:%M:%S') if status.was_online else 'неизвестно'
            return f'🔴 {name} (@{username}) — оффлайн (был(а) в сети: {last_seen})'
        else:
            return f'⚪ {name} (@{username}) — статус скрыт или неизвестен'
    except Exception as e:
        return f'❓ @{username} — ошибка: {e}'


# ========================
# Фильтр: только владелец
# ========================
def owner_only(message: types.Message) -> bool:
    return message.chat.id == MY_CHAT_ID


# ========================
# Команды бота
# ========================
@dp.message(Command('start'))
async def cmd_start(message: types.Message):
    if not owner_only(message):
        return
    text = (
        '🤖 <b>Telegram Online Tracker Bot</b>\n\n'
        'Доступные команды:\n'
        '/status — текущий статус всех отслеживаемых\n'
        '/list — список отслеживаемых пользователей\n'
        '/add username — добавить пользователя\n'
        '/remove username — убрать пользователя\n'
        '/pause — приостановить мониторинг\n'
        '/resume — возобновить мониторинг'
    )
    await message.answer(text, parse_mode='HTML')


@dp.message(Command('status'))
async def cmd_status(message: types.Message):
    if not owner_only(message):
        return
    if not tracking_users:
        await message.answer('📋 Список отслеживаемых пуст.')
        return
    lines = await asyncio.gather(*[get_user_status(u) for u in tracking_users])
    await message.answer('\n'.join(lines))


@dp.message(Command('list'))
async def cmd_list(message: types.Message):
    if not owner_only(message):
        return
    if not tracking_users:
        await message.answer('📋 Список отслеживаемых пуст.')
        return
    users_list = '\n'.join(f'• @{u}' for u in tracking_users)
    await message.answer(f'📋 Отслеживаемые пользователи:\n{users_list}')


@dp.message(Command('add'))
async def cmd_add(message: types.Message):
    if not owner_only(message):
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer('⚠️ Укажите юзернейм: /add username')
        return
    username = parts[1].lstrip('@').lower()
    if username in [u.lower() for u in tracking_users]:
        await message.answer(f'ℹ️ @{username} уже в списке.')
        return
    tracking_users.append(username)
    last_status[username] = None
    await message.answer(f'✅ @{username} добавлен в список отслеживания.')


@dp.message(Command('remove'))
async def cmd_remove(message: types.Message):
    if not owner_only(message):
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer('⚠️ Укажите юзернейм: /remove username')
        return
    username = parts[1].lstrip('@').lower()
    matched = [u for u in tracking_users if u.lower() == username]
    if not matched:
        await message.answer(f'ℹ️ @{username} не найден в списке.')
        return
    for u in matched:
        tracking_users.remove(u)
    last_status.pop(username, None)
    await message.answer(f'🗑️ @{username} удалён из списка отслеживания.')


@dp.message(Command('pause'))
async def cmd_pause(message: types.Message):
    if not owner_only(message):
        return
    global paused
    paused = True
    await message.answer('⏸️ Мониторинг приостановлен.')


@dp.message(Command('resume'))
async def cmd_resume(message: types.Message):
    if not owner_only(message):
        return
    global paused
    paused = False
    await message.answer('▶️ Мониторинг возобновлён.')


# ========================
# Запуск
# ========================
async def main():
    await client.start()

    # Подгрузить пользователей чтобы Telethon получал их обновления
    for username in tracking_users:
        try:
            entity = await client.get_entity(username)
            # Принудительно запросить свежие данные
            result = await client(GetUsersRequest(id=[entity.id]))
            if result:
                user = result[0]
                name = user.first_name or username
                status = user.status
                if isinstance(status, UserStatusOnline):
                    last_status[username.lower()] = True
                elif isinstance(status, UserStatusOffline):
                    last_status[username.lower()] = False
                else:
                    last_status[username.lower()] = None
                print(f'👤 {name} (@{username}) загружен')
            else:
                last_status[username.lower()] = None
        except Exception as e:
            print(f'❌ @{username}: {e}')
            last_status[username.lower()] = None

    # Уведомить владельца о запуске
    await bot.send_message(MY_CHAT_ID, f'🚀 Трекер запущен! Отслеживаю: {len(tracking_users)} чел.')

    # Запустить polling бота и Telethon параллельно
    await asyncio.gather(
        dp.start_polling(bot),
        client.run_until_disconnected(),
    )


if __name__ == '__main__':
    asyncio.run(main())
