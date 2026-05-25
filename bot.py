from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils import executor
import sqlite3

TOKEN = "8761056338:AAENOb7yKPi79LaD5-bYrI0AHQBK4gVZfJA"
ADMIN_ID = 7351788975

bot = Bot(token=TOKEN)
dp = Dispatcher(bot)

db = sqlite3.connect("bot.db")
cursor = db.cursor()

cursor.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, referrer INTEGER, balance INTEGER DEFAULT 0)")
cursor.execute("CREATE TABLE IF NOT EXISTS tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, channel TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS completed (user_id INTEGER, task_id INTEGER)")
cursor.execute("CREATE TABLE IF NOT EXISTS forced_channels (channel TEXT)")
db.commit()

user_states = {}

# ===== КНОПКИ =====

def main_menu():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("💰 Баланс", "👥 Рефералы")
    kb.add("📋 Задания", "💸 Вывод")
    kb.add("👤 Пользователи")
    return kb


def task_keyboard(channel, task_id):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("📢 Перейти", url=f"https://t.me/{channel[1:]}"),
        InlineKeyboardButton("⏭ Пропустить", callback_data="skip")
    )
    kb.add(
        InlineKeyboardButton("✅ Подтвердить", callback_data=f"check_task_{task_id}")
    )
    return kb


def force_keyboard(channels):
    kb = InlineKeyboardMarkup()
    for ch in channels:
        kb.add(InlineKeyboardButton(f"📢 {ch}", url=f"https://t.me/{ch[1:]}"))
    kb.add(InlineKeyboardButton("✅ Проверить", callback_data="check_sub"))
    return kb


def delete_force_keyboard(channels):
    kb = InlineKeyboardMarkup()
    for ch in channels:
        kb.add(InlineKeyboardButton(f"🗑 {ch}", callback_data=f"del_force_{ch}"))
    kb.add(InlineKeyboardButton("❌ Отмена", callback_data="admin_cancel"))
    return kb


def delete_task_keyboard(tasks):
    kb = InlineKeyboardMarkup()
    for task_id, channel in tasks:
        kb.add(InlineKeyboardButton(f"🗑 #{task_id} {channel}", callback_data=f"del_task_{task_id}"))
    kb.add(InlineKeyboardButton("❌ Отмена", callback_data="admin_cancel"))
    return kb


# ===== ПРОВЕРКА ПОДПИСКИ =====

async def check_sub(user_id):
    cursor.execute("SELECT channel FROM forced_channels")
    channels = cursor.fetchall()

    for ch in channels:
        try:
            member = await bot.get_chat_member(ch[0], user_id)
            if member.status == "left":
                return False
        except:
            continue
    return True


# ===== СТАТИСТИКА =====

@dp.message_handler(lambda m: m.text == "👤 Пользователи")
async def users_count(msg: types.Message):
    cursor.execute("SELECT COUNT(*) FROM users")
    count = cursor.fetchone()[0]
    await msg.answer(f"👤 Всего пользователей: {count}")


# ===== СТАРТ =====

@dp.message_handler(commands=['start'])
async def start(msg: types.Message):
    user_id = msg.from_user.id
    args = msg.get_args()

    cursor.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    existing = cursor.fetchone()

    if not existing:
        ref = int(args) if args.isdigit() else None
        if ref == user_id:
            ref = None

        cursor.execute("INSERT INTO users (user_id, referrer) VALUES (?, ?)", (user_id, ref))
        db.commit()

        if ref:
            cursor.execute("UPDATE users SET balance = balance + 3 WHERE user_id=?", (ref,))
            db.commit()

            cursor.execute("SELECT balance FROM users WHERE user_id=?", (ref,))
            ref_balance = cursor.fetchone()
            ref_balance = ref_balance[0] if ref_balance else 0

            new_user_name = msg.from_user.first_name or "Пользователь"
            try:
                await bot.send_message(
                    ref,
                    f"🎉 По вашей реферальной ссылке зарегистрировался новый пользователь!\n\n"
                    f"👤 {new_user_name}\n"
                    f"💰 +3 ⭐ зачислено на ваш баланс\n"
                    f"💼 Ваш баланс: {ref_balance} ⭐"
                )
            except:
                pass

    if not await check_sub(user_id):
        cursor.execute("SELECT channel FROM forced_channels")
        channels = [c[0] for c in cursor.fetchall()]
        await msg.answer("❗ Подпишись", reply_markup=force_keyboard(channels))
        return

    await msg.answer("✅ Добро пожаловать!", reply_markup=main_menu())


# ===== ПРОВЕРКА ПОДПИСКИ =====

@dp.callback_query_handler(lambda c: c.data == "check_sub")
async def check_sub_btn(callback: types.CallbackQuery):
    if await check_sub(callback.from_user.id):
        await callback.message.answer("✅ Доступ открыт", reply_markup=main_menu())
    else:
        await callback.answer("❌ Подпишись", show_alert=True)


# ===== БАЛАНС =====

@dp.message_handler(lambda m: m.text == "💰 Баланс")
async def balance(msg: types.Message):
    cursor.execute("SELECT balance FROM users WHERE user_id=?", (msg.from_user.id,))
    await msg.answer(f"💰 Баланс: {cursor.fetchone()[0]} ⭐")


# ===== РЕФЕРАЛЫ =====

@dp.message_handler(lambda m: m.text == "👥 Рефералы")
async def refs(msg: types.Message):
    user_id = msg.from_user.id

    cursor.execute("SELECT COUNT(*) FROM users WHERE referrer=?", (user_id,))
    count = cursor.fetchone()[0]

    bot_username = (await bot.get_me()).username
    link = f"https://t.me/{bot_username}?start={user_id}"

    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🚀 Пригласить друга", url=link))

    await msg.answer(
        f"👥 Твои приглашённые: {count}\n\n"
        f"💰 За каждого друга: +3 ⭐\n\n"
        f"🔗 {link}",
        reply_markup=kb
    )


# ===== ЗАДАНИЯ =====

@dp.message_handler(lambda m: m.text == "📋 Задания")
async def tasks_list(msg: types.Message):
    user_id = msg.from_user.id

    cursor.execute("SELECT id, channel FROM tasks")
    all_tasks = cursor.fetchall()

    if not all_tasks:
        await msg.answer("❌ Сейчас нет доступных заданий")
        return

    shown = 0
    for task in all_tasks:
        task_id, channel = task
        cursor.execute("SELECT * FROM completed WHERE user_id=? AND task_id=?", (user_id, task_id))
        if cursor.fetchone():
            continue

        await msg.answer(
            f"📢 {channel}\n💰 5 ⭐",
            reply_markup=task_keyboard(channel, task_id)
        )
        shown += 1

    if shown == 0:
        await msg.answer("✅ Все задания выполнены!")


# ===== ПРОВЕРКА ЗАДАНИЯ =====

@dp.callback_query_handler(lambda c: c.data.startswith("check_task_"))
async def check_task(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    task_id = int(callback.data.split("_")[2])

    cursor.execute("SELECT channel FROM tasks WHERE id=?", (task_id,))
    task = cursor.fetchone()

    if not task:
        await callback.answer("❌ Задание не найдено", show_alert=True)
        return

    cursor.execute("SELECT * FROM completed WHERE user_id=? AND task_id=?", (user_id, task_id))
    if cursor.fetchone():
        await callback.answer("❌ Уже выполнено", show_alert=True)
        return

    member = await bot.get_chat_member(task[0], user_id)

    if member.status != "left":
        cursor.execute("UPDATE users SET balance = balance + 5 WHERE user_id=?", (user_id,))
        cursor.execute("INSERT INTO completed VALUES (?, ?)", (user_id, task_id))
        db.commit()

        cursor.execute("SELECT balance FROM users WHERE user_id=?", (user_id,))
        new_balance = cursor.fetchone()[0]

        await callback.answer("✅ +5 ⭐", show_alert=True)

        await callback.message.answer(
            f"✅ Задание выполнено!\n\n"
            f"📢 Канал: {task[0]}\n"
            f"💰 Начислено: +5 ⭐\n"
            f"💼 Ваш баланс: {new_balance} ⭐"
        )
    else:
        await callback.answer("❌ Подпишись на канал", show_alert=True)


# ===== ВЫВОД =====

@dp.message_handler(lambda m: m.text == "💸 Вывод")
async def withdraw(msg: types.Message):
    cursor.execute("SELECT balance FROM users WHERE user_id=?", (msg.from_user.id,))
    bal = cursor.fetchone()[0]

    if bal >= 100:
        await msg.answer("💸 Заявка отправлена")
    else:
        await msg.answer("❌ Минимум 100 ⭐")


# ===== АДМИН =====

@dp.message_handler(commands=['admin'])
async def admin_panel(msg: types.Message):
    if msg.from_user.id != ADMIN_ID:
        return

    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("➕ Добавить задание", "🗑 Удалить задание")
    kb.add("📢 Рассылка", "➕ Обяз канал")
    kb.add("🗑 Удалить обяз канал")

    await msg.answer("👑 Админ панель", reply_markup=kb)


# ===== ШАГИ АДМИНА =====

@dp.message_handler(lambda m: m.text == "➕ Добавить задание")
async def add_task(msg: types.Message):
    user_states[msg.from_user.id] = "add_task"
    await msg.answer("Отправь канал (например @channel)")


@dp.message_handler(lambda m: m.text == "🗑 Удалить задание")
async def delete_task_menu(msg: types.Message):
    if msg.from_user.id != ADMIN_ID:
        return

    cursor.execute("SELECT id, channel FROM tasks")
    tasks = cursor.fetchall()

    if not tasks:
        await msg.answer("❌ Нет доступных заданий")
        return

    await msg.answer("Выбери задание для удаления:", reply_markup=delete_task_keyboard(tasks))


@dp.message_handler(lambda m: m.text == "📢 Рассылка")
async def broadcast_start(msg: types.Message):
    user_states[msg.from_user.id] = "broadcast"
    await msg.answer("Отправь сообщение")


@dp.message_handler(lambda m: m.text == "➕ Обяз канал")
async def add_force(msg: types.Message):
    user_states[msg.from_user.id] = "force"
    await msg.answer("Отправь канал (например @channel)")


@dp.message_handler(lambda m: m.text == "🗑 Удалить обяз канал")
async def delete_force_menu(msg: types.Message):
    if msg.from_user.id != ADMIN_ID:
        return

    cursor.execute("SELECT channel FROM forced_channels")
    channels = [c[0] for c in cursor.fetchall()]

    if not channels:
        await msg.answer("❌ Нет обязательных каналов")
        return

    await msg.answer("Выбери канал для удаления:", reply_markup=delete_force_keyboard(channels))


# ===== КОЛЛБЭКИ УДАЛЕНИЯ =====

@dp.callback_query_handler(lambda c: c.data.startswith("del_force_"))
async def confirm_delete_force(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return

    channel = callback.data[len("del_force_"):]

    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("✅ Да, удалить", callback_data=f"confirm_force_{channel}"),
        InlineKeyboardButton("❌ Отмена", callback_data="admin_cancel")
    )

    await callback.message.edit_text(
        f"Удалить канал {channel}?",
        reply_markup=kb
    )


@dp.callback_query_handler(lambda c: c.data.startswith("confirm_force_"))
async def do_delete_force(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return

    channel = callback.data[len("confirm_force_"):]
    cursor.execute("DELETE FROM forced_channels WHERE channel=?", (channel,))
    db.commit()

    await callback.message.edit_text(f"✅ Канал {channel} удалён")


@dp.callback_query_handler(lambda c: c.data.startswith("del_task_"))
async def confirm_delete_task(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return

    task_id = callback.data[len("del_task_"):]

    cursor.execute("SELECT channel FROM tasks WHERE id=?", (task_id,))
    task = cursor.fetchone()
    if not task:
        await callback.answer("❌ Задание не найдено", show_alert=True)
        return

    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("✅ Да, удалить", callback_data=f"confirm_task_{task_id}"),
        InlineKeyboardButton("❌ Отмена", callback_data="admin_cancel")
    )

    await callback.message.edit_text(
        f"Удалить задание #{task_id} ({task[0]})?",
        reply_markup=kb
    )


@dp.callback_query_handler(lambda c: c.data.startswith("confirm_task_"))
async def do_delete_task(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return

    task_id = callback.data[len("confirm_task_"):]
    cursor.execute("DELETE FROM tasks WHERE id=?", (task_id,))
    cursor.execute("DELETE FROM completed WHERE task_id=?", (task_id,))
    db.commit()

    await callback.message.edit_text(f"✅ Задание #{task_id} удалено")


@dp.callback_query_handler(lambda c: c.data == "admin_cancel")
async def admin_cancel(callback: types.CallbackQuery):
    await callback.message.edit_text("❌ Отменено")


# ===== ОБРАБОТКА ТЕКСТА ОТ АДМИНА =====

@dp.message_handler(lambda m: m.from_user.id == ADMIN_ID)
async def admin_steps(msg: types.Message):
    state = user_states.get(msg.from_user.id)

    if state == "add_task":
        cursor.execute("INSERT INTO tasks (channel) VALUES (?)", (msg.text,))
        db.commit()
        task_id = cursor.lastrowid  # ID только что добавленного задания
        await msg.answer("✅ Добавлено. Рассылаю пользователям...")

        # Рассылка нового задания всем пользователям
        cursor.execute("SELECT user_id FROM users")
        users = cursor.fetchall()
        sent = 0
        for user in users:
            try:
                await bot.send_message(
                    user[0],
                    f"🆕 Новое задание!\n\n📢 {msg.text}\n💰 5 ⭐",
                    reply_markup=task_keyboard(msg.text, task_id)
                )
                sent += 1
            except:
                pass
        await msg.answer(f"📣 Задание разослано {sent} пользователям")

    elif state == "broadcast":
        cursor.execute("SELECT user_id FROM users")
        for user in cursor.fetchall():
            try:
                await bot.send_message(user[0], msg.text)
            except:
                pass
        await msg.answer("✅ Разослано")

    elif state == "force":
        cursor.execute("INSERT INTO forced_channels (channel) VALUES (?)", (msg.text,))
        db.commit()
        await msg.answer("✅ Добавлен")

    user_states.pop(msg.from_user.id, None)


# ===== ЗАПУСК =====

if __name__ == "__main__":
    executor.start_polling(dp)