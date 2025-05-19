import os
import json
import asyncio
import logging
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Файл для хранения данных пользователей
DATA_FILE = 'user_data.json'

# Определение состояний для FSM (Finite State Machine)
class UserStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_birthday = State()
    waiting_for_expense_name = State()
    waiting_for_expense_amount = State()
    waiting_for_income_amount = State()

# Загрузка данных из файла
def load_data():
    logger.info("Загрузка данных из файла")
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    return {}

# Сохранение данных в файл
def save_data(data):
    logger.info("Сохранение данных в файл")
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)

# Создание клавиатуры профиля
def get_profile_keyboard():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить трату", callback_data='add_expense')],
        [InlineKeyboardButton(text="💵 Добавить поступление", callback_data='add_income')],
        [InlineKeyboardButton(text="📊 Посмотреть траты за все время", callback_data='view_expenses')],
        [InlineKeyboardButton(text="ℹ️ About", callback_data='about')],
    ])
    return keyboard

# Показать профиль пользователя
async def show_profile(message_or_query: types.Message | types.CallbackQuery, user_id: str):
    logger.info(f"Показ профиля для user_id: {user_id}")
    data = load_data()
    user_data = data.get(user_id, {})
    
    if not user_data:
        if isinstance(message_or_query, types.Message):
            await message_or_query.answer("Произошла ошибка. Попробуйте снова /start")
        else:
            await message_or_query.message.edit_text("Произошла ошибка. Попробуйте снова /start")
        return
    
    # Рассчитываем дни до дня рождения
    try:
        birth_date = datetime.strptime(user_data['birthday'], '%d-%m-%y')
        now = datetime.now()
        next_birthday = birth_date.replace(year=now.year)
        if next_birthday < now:
            next_birthday = next_birthday.replace(year=now.year + 1)
        days_to_birthday = (next_birthday - now).days
    except:
        days_to_birthday = "неизвестно"
    
    # Рассчитываем расходы за месяц
    current_month = datetime.now().month
    current_year = datetime.now().year
    monthly_expenses = sum(
        exp['amount'] for exp in user_data.get('expenses', [])
        if datetime.strptime(exp['date'], '%Y-%m-%d %H:%M:%S').month == current_month
        and datetime.strptime(exp['date'], '%Y-%m-%d %H:%M:%S').year == current_year
    )
    
    # Формируем сообщение
    message = (
        f"👤 {user_data['name']}\n"
        f"💰 Актуальный баланс: {user_data['balance']} ₽\n"
        f"💸 Траты за месяц: {monthly_expenses} ₽\n"
        f"🎂 До дня рождения: {days_to_birthday} дней\n"
    )
    
    if isinstance(message_or_query, types.Message):
        await message_or_query.answer(message, reply_markup=get_profile_keyboard())
    else:
        await message_or_query.message.edit_text(message, reply_markup=get_profile_keyboard())

# Обработчик команды /start
async def start(message: types.Message, state: FSMContext):
    logger.info("Обработка команды /start")
    user_id = str(message.from_user.id)
    data = load_data()
    
    if user_id in data:
        await show_profile(message, user_id)
    else:
        await message.answer("Привет! Давай познакомимся. Как тебя зовут?")
        await state.set_state(UserStates.waiting_for_name)

# Обработчик текстовых сообщений
async def handle_message(message: types.Message, state: FSMContext):
    logger.info("Обработка текстового сообщения")
    user_id = str(message.from_user.id)
    data = load_data()
    current_state = await state.get_state()
    
    # Игнорируем команды
    if message.text and message.text.startswith('/'):
        return
    
    if current_state == UserStates.waiting_for_name.state:
        await state.update_data(name=message.text)
        await message.answer("Отлично! Теперь введи свою дату рождения в формате ДД-ММ-ГГ (например, 01-01-90)")
        await state.set_state(UserStates.waiting_for_birthday)
    
    elif current_state == UserStates.waiting_for_birthday.state:
        try:
            birthday = datetime.strptime(message.text, '%d-%m-%y')
            user_data = await state.get_data()
            data[user_id] = {
                'name': user_data['name'],
                'birthday': message.text,
                'balance': 0,
                'expenses': [],
                'incomes': [],
                'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            save_data(data)
            await state.clear()
            await show_profile(message, user_id)
        except ValueError:
            await message.answer("Неправильный формат даты. Пожалуйста, введи дату в формате ДД-ММ-ГГ (например, 01-01-90)")
    
    elif current_state == UserStates.waiting_for_expense_name.state:
        await state.update_data(expense_name=message.text)
        await message.answer("За сколько вы это купили? (Введите число)")
        await state.set_state(UserStates.waiting_for_expense_amount)
    
    elif current_state == UserStates.waiting_for_expense_amount.state:
        try:
            amount = float(message.text)
            user_data = data.get(user_id, {})
            expense_data = await state.get_data()
            
            new_expense = {
                'name': expense_data['expense_name'],
                'amount': amount,
                'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            
            user_data.setdefault('expenses', []).append(new_expense)
            user_data['balance'] = user_data.get('balance', 0) - amount
            data[user_id] = user_data
            save_data(data)
            
            await state.clear()
            await message.answer("Расход успешно добавлен!")
            await show_profile(message, user_id)
        except ValueError:
            await message.answer("Пожалуйста, введите корректную сумму (число)")
    
    elif current_state == UserStates.waiting_for_income_amount.state:
        try:
            amount = float(message.text)
            user_data = data.get(user_id, {})
            
            new_income = {
                'amount': amount,
                'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            
            user_data.setdefault('incomes', []).append(new_income)
            user_data['balance'] = user_data.get('balance', 0) + amount
            data[user_id] = user_data
            save_data(data)
            
            await state.clear()
            await message.answer("Доход успешно добавлен!")
            await show_profile(message, user_id)
        except ValueError:
            await message.answer("Пожалуйста, введите корректную сумму (число)")

# Обработчик нажатий на кнопки
async def button_handler(callback_query: types.CallbackQuery, state: FSMContext):
    logger.info("Обработка нажатия кнопки")
    user_id = str(callback_query.from_user.id)
    data = callback_query.data
    
    if data == 'add_expense':
        await callback_query.message.edit_text("Что вы купили?")
        await state.set_state(UserStates.waiting_for_expense_name)
    
    elif data == 'add_income':
        await callback_query.message.edit_text("Какая сумма поступила?")
        await state.set_state(UserStates.waiting_for_income_amount)
    
    elif data == 'view_expenses':
        await show_all_expenses(callback_query, user_id)
    
    elif data == 'about':
        await show_about(callback_query)
    
    elif data == 'back_to_profile':
        await show_profile(callback_query, user_id)
    
    elif data.startswith('expense_'):
        expense_id = int(data.split('_')[1])
        await show_expense_details(callback_query, user_id, expense_id)

# Показать все расходы
async def show_all_expenses(callback_query: types.CallbackQuery, user_id: str):
    logger.info(f"Показ всех расходов для user_id: {user_id}")
    data = load_data()
    user_data = data.get(user_id, {})
    expenses = user_data.get('expenses', [])
    
    if not expenses:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data='back_to_profile')]
        ])
        await callback_query.message.edit_text("У вас пока нет расходов.", reply_markup=keyboard)
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"{expense['name']} - {expense['amount']} ₽ ({datetime.strptime(expense['date'], '%Y-%m-%d %H:%M:%S').strftime('%d.%m.%Y')})",
            callback_data=f'expense_{i}'
        )] for i, expense in enumerate(expenses)
    ])
    keyboard.inline_keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data='back_to_profile')])
    
    await callback_query.message.edit_text("Ваши расходы:", reply_markup=keyboard)

# Показать детали расхода
async def show_expense_details(callback_query: types.CallbackQuery, user_id: str, expense_id: int):
    logger.info(f"Показ деталей расхода для user_id: {user_id}, expense_id: {expense_id}")
    data = load_data()
    user_data = data.get(user_id, {})
    expenses = user_data.get('expenses', [])
    
    if expense_id >= len(expenses):
        await callback_query.message.edit_text("Ошибка: расход не найден.")
        return
    
    expense = expenses[expense_id]
    date = datetime.strptime(expense['date'], '%Y-%m-%d %H:%M:%S').strftime('%d.%m.%Y %H:%M')
    message = (
        f"🛒 Покупка: {expense['name']}\n"
        f"💸 Сумма: {expense['amount']} ₽\n"
        f"📅 Дата: {date}\n"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data='view_expenses')]
    ])
    
    await callback_query.message.edit_text(message, reply_markup=keyboard)

# Показать информацию о разработчике
async def show_about(callback_query: types.CallbackQuery):
    logger.info("Показ информации о боте")
    message = (
        "ℹ️ О боте:\n"
        "Этот бот помогает отслеживать ваши расходы и доходы.\n\n"
        "Разработчик: @BPOTEBAL\n"
        "Версия: 1.0\n"
        "Дата создания: 2025"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data='back_to_profile')]
    ])
    
    await callback_query.message.edit_text(message, reply_markup=keyboard)

async def main():
    logger.info("Запуск бота")
    # Замените 'YOUR_TOKEN' на токен вашего бота
    bot = Bot(token="7781361742:AAGUG7mDjjr5iCV14Q-jwA6IUAjMmiEJXk8")
    dp = Dispatcher()
    
    # Регистрация обработчиков
    dp.message.register(start, CommandStart())
    dp.message.register(handle_message)  # Обрабатываем все сообщения
    dp.callback_query.register(button_handler)
    
    try:
        logger.info("Начало поллинга")
        await dp.start_polling(bot, allowed_updates=["message", "callback_query"])
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"Ошибка: {e}", exc_info=True)
    finally:
        logger.info("Завершение работы бота")
        await bot.session.close()

if __name__ == '__main__':
    asyncio.run(main())