import os
import json
from datetime import datetime, timedelta
import asyncio
import g4f
import logging
import re
import sqlite3
import pytz
import shutil
import tempfile
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.tl.functions.messages import GetHistoryRequest
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.errors import ChannelPrivateError, UsernameNotOccupiedError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import random
from fpdf import FPDF
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.pagesizes import A4
from transliterate import translit
import platform

# Настраиваем логирование
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Загружаем переменные окружения
logger.info("Загружаем .env файл...")
load_dotenv()
token = os.getenv('BOT_TOKEN')
logger.info(f"Токен: {token}")

if not token:
    raise ValueError("BOT_TOKEN не найден в .env файле!")

# Инициализируем SQLite
def init_db():
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    
    # Таблица для отчетов
    c.execute('''CREATE TABLE IF NOT EXISTS reports
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  folder TEXT,
                  content TEXT,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    # Таблица для расписания
    c.execute('''CREATE TABLE IF NOT EXISTS schedules
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  folder TEXT,
                  time TEXT,
                  is_active BOOLEAN DEFAULT 1)''')
    
    conn.commit()
    conn.close()

init_db()

# Создаем планировщик (но не запускаем)
scheduler = AsyncIOScheduler(timezone=pytz.UTC)

# Конфигурация провайдеров и моделей
PROVIDER_HIERARCHY = [
    {
        'provider': g4f.Provider.DDG,
        'models': ['gpt-4', 'gpt-4o-mini', 'claude-3-haiku', 'llama-3.1-70b', 'mixtral-8x7b']
    },
    {
        'provider': g4f.Provider.Blackbox,
        'models': ['blackboxai', 'gpt-4', 'gpt-4o', 'o3-mini', 'gemini-1.5-flash', 'gemini-1.5-pro', 
                  'blackboxai-pro', 'llama-3.1-8b', 'llama-3.1-70b', 'llama-3.1-405b', 'llama-3.3-70b', 
                  'mixtral-small-28b', 'deepseek-chat', 'dbrx-instruct', 'qwq-32b', 'hermes-2-dpo', 'deepseek-r1']
    },
    {
        'provider': g4f.Provider.DeepInfraChat,
        'models': ['llama-3.1-8b', 'llama-3.2-90b', 'llama-3.3-70b', 'deepseek-v3', 'mixtral-small-28b',
                  'deepseek-r1', 'phi-4', 'wizardlm-2-8x22b', 'qwen-2.5-72b', 'yi-34b', 'qwen-2-72b',
                  'dolphin-2.6', 'dolphin-2.9', 'dbrx-instruct', 'airoboros-70b', 'lzlv-70b', 'wizardlm-2-7b']
    },
    {
        'provider': g4f.Provider.ChatGptEs,
        'models': ['gpt-4', 'gpt-4o', 'gpt-4o-mini']
    },
    {
        'provider': g4f.Provider.Liaobots,
        'models': ['grok-2', 'gpt-4o-mini', 'gpt-4o', 'gpt-4', 'o1-preview', 'o1-mini', 'deepseek-r1',
                  'deepseek-v3', 'claude-3-opus', 'claude-3.5-sonnet', 'claude-3-sonnet', 'gemini-1.5-flash',
                  'gemini-1.5-pro', 'gemini-2.0-flash', 'gemini-2.0-flash-thinking']
    },
    {
        'provider': g4f.Provider.Jmuz,
        'models': ['gpt-4', 'gpt-4o', 'gpt-4o-mini', 'llama-3-8b', 'llama-3-70b', 'llama-3.1-8b', 
                  'llama-3.1-70b', 'llama-3.1-405b', 'llama-3.2-11b', 'llama-3.2-90b', 'llama-3.3-70b',
                  'claude-3-haiku', 'claude-3-sonnet', 'claude-3-opus', 'claude-3.5-sonnet', 
                  'gemini-1.5-flash', 'gemini-1.5-pro', 'gemini-exp', 'deepseek-chat', 'deepseek-r1', 'qwq-32b']
    },
    {
        'provider': g4f.Provider.Glider,
        'models': ['llama-3.1-8b', 'llama-3.1-70b', 'llama-3.2-3b', 'deepseek-r1']
    },
    {
        'provider': g4f.Provider.PollinationsAI,
        'models': ['gpt-4o', 'gpt-4o-mini', 'llama-3.1-8b', 'llama-3.3-70b', 'deepseek-chat', 
                  'deepseek-r1', 'qwen-2.5-coder-32b', 'gemini-2.0-flash', 'evil', 'flux-pro']
    },
    {
        'provider': g4f.Provider.HuggingChat,
        'models': ['llama-3.2-11b', 'llama-3.3-70b', 'mistral-nemo', 'phi-3.5-mini', 'deepseek-r1',
                  'qwen-2.5-coder-32b', 'qwq-32b', 'nemotron-70b']
    },
    {
        'provider': g4f.Provider.HuggingFace,
        'models': ['llama-3.2-11b', 'llama-3.3-70b', 'mistral-nemo', 'deepseek-r1', 
                  'qwen-2.5-coder-32b', 'qwq-32b', 'nemotron-70b']
    },
    {
        'provider': g4f.Provider.HuggingSpace,
        'models': ['command-r', 'command-r-plus', 'command-r7b', 'qwen-2-72b', 'qwen-2.5-1m', 
                  'qvq-72b', 'sd-3.5', 'flux-dev', 'flux-schnell']
    },
    {
        'provider': g4f.Provider.Cloudflare,
        'models': ['llama-2-7b', 'llama-3-8b', 'llama-3.1-8b', 'qwen-1.5-7b']
    },
    {
        'provider': g4f.Provider.ChatGLM,
        'models': ['glm-4']
    },
    {
        'provider': g4f.Provider.GigaChat,
        'models': ['GigaChat:latest']
    },
    {
        'provider': g4f.Provider.Gemini,
        'models': ['gemini', 'gemini-1.5-flash', 'gemini-1.5-pro']
    },
    {
        'provider': g4f.Provider.GeminiPro,
        'models': ['gemini-1.5-flash', 'gemini-1.5-pro', 'gemini-2.0-flash']
    },
    {
        'provider': g4f.Provider.Pi,
        'models': ['pi']
    },
    {
        'provider': g4f.Provider.PerplexityLabs,
        'models': ['sonar', 'sonar-pro', 'sonar-reasoning', 'sonar-reasoning-pro']
    }
]

# Инициализируем клиенты
bot = Bot(token=token)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# Инициализируем клиент Telethon
client = TelegramClient('telegram_session', int(os.getenv('API_ID')), os.getenv('API_HASH'))

# Структура для хранения данных
class UserData:
    def __init__(self):
        self.users = {}  # {user_id: {'folders': {}, 'prompts': {}, 'ai_settings': {}}}
        
    def get_user_data(self, user_id: int) -> dict:
        """Получаем или создаем данные пользователя"""
        if str(user_id) not in self.users:
            self.users[str(user_id)] = {
                'folders': {},
                'prompts': {},
                'ai_settings': {
                    'provider_index': 0,
                    'model': PROVIDER_HIERARCHY[0]['models'][0]
                }
            }
        return self.users[str(user_id)]
        
    def save(self):
        with open('user_data.json', 'w', encoding='utf-8') as f:
            json.dump({'users': self.users}, f, ensure_ascii=False)
    
    @classmethod
    def load(cls):
        instance = cls()
        try:
            with open('user_data.json', 'r', encoding='utf-8') as f:
                data = json.load(f)
                instance.users = data.get('users', {})
        except FileNotFoundError:
            pass
        return instance

user_data = UserData.load()

# Состояния для FSM
class BotStates(StatesGroup):
    waiting_for_folder_name = State()
    waiting_for_channels = State()
    waiting_for_prompt = State()
    waiting_for_folder_to_edit = State()
    waiting_for_model_selection = State()
    waiting_for_schedule_folder = State()
    waiting_for_schedule_time = State()

def save_report(user_id: int, folder: str, content: str):
    """Сохраняем отчет в БД"""
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    c.execute('INSERT INTO reports (user_id, folder, content) VALUES (?, ?, ?)',
              (user_id, folder, content))
    conn.commit()
    conn.close()

def get_user_reports(user_id: int, limit: int = 10) -> list:
    """Получаем последние отчеты пользователя"""
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    c.execute('SELECT folder, content, created_at FROM reports WHERE user_id = ? ORDER BY created_at DESC LIMIT ?',
              (user_id, limit))
    reports = c.fetchall()
    conn.close()
    return reports

def save_schedule(user_id: int, folder: str, time: str):
    """Сохраняем расписание в БД"""
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    c.execute('INSERT INTO schedules (user_id, folder, time) VALUES (?, ?, ?)',
              (user_id, folder, time))
    conn.commit()
    conn.close()

def get_active_schedules() -> list:
    """Получаем все активные расписания"""
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    c.execute('SELECT user_id, folder, time FROM schedules WHERE is_active = 1')
    schedules = c.fetchall()
    conn.close()
    return schedules

def generate_txt_report(content: str, folder: str) -> str:
    """Генерирует отчет в формате TXT"""
    filename = f"analysis_{folder}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(content)
    return filename

# Определяем путь к шрифту в зависимости от ОС
def get_font_path():
    os_type = platform.system().lower()
    if os_type == 'linux':
        paths = [
            "/usr/share/fonts/dejavu-sans-fonts/DejaVuSans.ttf",
            "/usr/share/fonts/TTF/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
        ]
    elif os_type == 'windows':
        paths = [
            "C:\\Windows\\Fonts\\DejaVuSans.ttf",
            os.path.join(os.getenv('LOCALAPPDATA'), 'Microsoft\\Windows\\Fonts\\DejaVuSans.ttf'),
            "DejaVuSans.ttf"  # В текущей директории
        ]
    else:  # MacOS и другие
        paths = [
            "/Library/Fonts/DejaVuSans.ttf",
            "/System/Library/Fonts/DejaVuSans.ttf",
            "DejaVuSans.ttf"  # В текущей директории
        ]
    
    # Проверяем наличие файла
    for path in paths:
        if os.path.exists(path):
            return path
            
    # Если шрифт не найден - скачиваем
    logger.info("Шрифт не найден, скачиваю...")
    try:
        import requests
        url = "https://github.com/dejavu-fonts/dejavu-fonts/raw/master/ttf/DejaVuSans.ttf"
        response = requests.get(url)
        with open("DejaVuSans.ttf", "wb") as f:
            f.write(response.content)
        return "DejaVuSans.ttf"
    except Exception as e:
        logger.error(f"Не удалось скачать шрифт: {str(e)}")
        raise Exception("Не удалось найти или скачать шрифт DejaVuSans.ttf")

def generate_pdf_report(content: str, folder: str) -> str:
    """Генерирует отчет в формате PDF"""
    filename = f"analysis_{folder}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    
    # Создаем PDF с поддержкой русского
    c = canvas.Canvas(filename, pagesize=A4)
    width, height = A4
    
    # Регистрируем шрифт DejaVu (поддерживает русский)
    font_path = get_font_path()
    pdfmetrics.registerFont(TTFont('DejaVu', font_path))
    
    # Пишем заголовок
    c.setFont('DejaVu', 16)  # Увеличенный размер для основного заголовка
    c.drawString(50, height - 50, f'Анализ папки: {folder}')
    
    # Пишем контент
    y = height - 100  # Начальная позиция для текста
    
    for line in content.split('\n'):
        if line.strip():  # Пропускаем пустые строки
            # Проверяем на заголовки разных уровней
            if line.strip().startswith('###'):
                # H3 заголовок
                c.setFont('DejaVu', 14)
                header_text = line.strip().replace('###', '').strip()
                c.drawString(50, y, header_text)
                y -= 30
                c.setFont('DejaVu', 12)
            elif line.strip().startswith('####'):
                # H4 заголовок
                c.setFont('DejaVu', 13)
                header_text = line.strip().replace('####', '').strip()
                c.drawString(70, y, header_text)  # Больший отступ для подзаголовка
                y -= 25
                c.setFont('DejaVu', 12)
            elif '**' in line.strip():
                # Ищем все вхождения жирного текста
                parts = line.split('**')
                x = 50  # Начальная позиция по X
                
                for i, part in enumerate(parts):
                    if i % 2 == 0:  # Обычный текст
                        if part.strip():
                            c.setFont('DejaVu', 12)
                            c.drawString(x, y, part)
                            x += c.stringWidth(part, 'DejaVu', 12)
                    else:  # Жирный текст
                        if part.strip():
                            c.setFont('DejaVu', 14)  # Делаем жирный текст чуть больше
                            c.drawString(x, y, part)
                            x += c.stringWidth(part, 'DejaVu', 14)
                
                y -= 20
                c.setFont('DejaVu', 12)  # Возвращаем обычный шрифт
            else:
                # Обычный текст
                c.setFont('DejaVu', 12)
                # Если строка слишком длинная, разбиваем ее
                words = line.split()
                current_line = ''
                for word in words:
                    test_line = current_line + ' ' + word if current_line else word
                    # Если строка становится слишком длинной, печатаем ее и начинаем новую
                    if c.stringWidth(test_line, 'DejaVu', 12) > width - 100:
                        c.drawString(50, y, current_line)
                        y -= 20
                        current_line = word
                    else:
                        current_line = test_line
                
                # Печатаем оставшуюся строку
                if current_line:
                    c.drawString(50, y, current_line)
                    y -= 20
            
            # Если достигли конца страницы, создаем новую
            if y < 50:
                c.showPage()
                c.setFont('DejaVu', 12)
                y = height - 50
    
    c.save()
    return filename

@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    me = await bot.get_me()
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    buttons = [
        "📁 Создать папку",
        "📋 Список папок",
        "✏️ Изменить промпт",
        "⚙️ Настройка ИИ",
        "🔄 Запустить анализ",
        "📊 История отчетов",
        "⏰ Настроить расписание"
    ]
    keyboard.add(*buttons)
    await message.answer(
        f"Привет! Я бот для анализа Telegram каналов.\n"
        f"Мой юзернейм: @{me.username}\n"
        "Что хочешь сделать?",
        reply_markup=keyboard
    )

@dp.message_handler(lambda message: message.text == "📁 Создать папку")
async def create_folder(message: types.Message):
    await BotStates.waiting_for_folder_name.set()
    await message.answer("Введи название папки:")

@dp.message_handler(state=BotStates.waiting_for_folder_name)
async def process_folder_name(message: types.Message, state: FSMContext):
    folder_name = message.text
    await state.update_data(current_folder=folder_name)
    user_data.get_user_data(message.from_user.id)['folders'][folder_name] = []
    user_data.get_user_data(message.from_user.id)['prompts'][folder_name] = "Проанализируй посты и составь краткий отчет"
    user_data.save()
    
    await BotStates.waiting_for_channels.set()
    await message.answer(
        "Отправь ссылки на каналы для этой папки.\n"
        "Каждую ссылку с новой строки.\n"
        "Когда закончишь, напиши 'готово'"
    )

def is_valid_channel(channel_link: str) -> bool:
    """Проверяем, что ссылка похожа на канал"""
    return bool(re.match(r'^@[\w\d_]+$', channel_link))

@dp.message_handler(state=BotStates.waiting_for_channels)
async def process_channels(message: types.Message, state: FSMContext):
    if message.text.lower() == 'готово':
        await state.finish()
        await message.answer("Папка создана! Используй /folders чтобы увидеть список папок")
        return

    data = await state.get_data()
    folder_name = data['current_folder']
    
    channels = [ch.strip() for ch in message.text.split('\n')]
    valid_channels = []
    
    for channel in channels:
        if not is_valid_channel(channel):
            await message.answer(f"❌ Канал {channel} не похож на правильную ссылку. Используй формат @username")
            continue
        valid_channels.append(channel)
    
    if valid_channels:
        user_data.get_user_data(message.from_user.id)['folders'][folder_name].extend(valid_channels)
        user_data.save()
        await message.answer(f"✅ Каналы добавлены в папку {folder_name}")

@dp.message_handler(lambda message: message.text == "📋 Список папок")
async def list_folders(message: types.Message):
    if not user_data.get_user_data(message.from_user.id)['folders']:
        await message.answer("Пока нет созданных папок")
        return

    keyboard = types.InlineKeyboardMarkup(row_width=1)
    for folder in user_data.get_user_data(message.from_user.id)['folders']:
        keyboard.add(
            types.InlineKeyboardButton(
                f"📁 {folder}",
                callback_data=f"edit_folder_{folder}"
            )
        )
    
    await message.answer("Выберите папку для редактирования:", reply_markup=keyboard)

@dp.message_handler(commands=['folders'])
async def cmd_list_folders(message: types.Message):
    await list_folders(message)

@dp.callback_query_handler(lambda c: c.data.startswith('edit_folder_'))
async def edit_folder_menu(callback_query: types.CallbackQuery):
    folder = callback_query.data.replace('edit_folder_', '')
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    
    # Добавляем кнопки для каждого канала
    channels = user_data.get_user_data(callback_query.from_user.id)['folders'][folder]
    for channel in channels:
        keyboard.add(
            types.InlineKeyboardButton(
                f"❌ {channel}",
                callback_data=f"remove_channel_{folder}_{channel}"
            )
        )
    
    # Добавляем основные кнопки управления
    keyboard.add(
        types.InlineKeyboardButton("➕ Добавить каналы", callback_data=f"add_channels_{folder}"),
        types.InlineKeyboardButton("❌ Удалить папку", callback_data=f"delete_folder_{folder}")
    )
    keyboard.add(types.InlineKeyboardButton("🔙 Назад", callback_data="back_to_folders"))
    
    await callback_query.message.edit_text(
        f"Редактирование папки {folder}:\n"
        f"Нажми на канал чтобы удалить его:\n" + 
        "\n".join(f"- {channel}" for channel in channels),
        reply_markup=keyboard
    )

@dp.callback_query_handler(lambda c: c.data.startswith('add_channels_'))
async def add_channels_start(callback_query: types.CallbackQuery, state: FSMContext):
    folder = callback_query.data.replace('add_channels_', '')
    await state.update_data(current_folder=folder)
    await BotStates.waiting_for_channels.set()
    
    await callback_query.message.answer(
        "Отправь ссылки на каналы для добавления.\n"
        "Каждую ссылку с новой строки.\n"
        "Когда закончишь, напиши 'готово'"
    )

@dp.callback_query_handler(lambda c: c.data.startswith('delete_folder_'))
async def delete_folder(callback_query: types.CallbackQuery):
    folder = callback_query.data.replace('delete_folder_', '')
    user = user_data.get_user_data(callback_query.from_user.id)
    
    if folder in user['folders']:
        del user['folders'][folder]
        del user['prompts'][folder]
        user_data.save()
        
        await callback_query.message.edit_text(f"✅ Папка {folder} удалена")
        
@dp.callback_query_handler(lambda c: c.data == "back_to_folders")
async def back_to_folders(callback_query: types.CallbackQuery):
    await callback_query.message.delete()  # Удаляем сообщение с инлайн клавиатурой
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    buttons = [
        "📁 Создать папку",
        "📋 Список папок",
        "✏️ Изменить промпт",
        "⚙️ Настройка ИИ",
        "🔄 Запустить анализ",
        "📊 История отчетов",
        "⏰ Настроить расписание"
    ]
    keyboard.add(*buttons)
    await callback_query.message.answer("Главное меню:", reply_markup=keyboard)

@dp.message_handler(lambda message: message.text == "✏️ Изменить промпт")
async def edit_prompt_start(message: types.Message):
    if not user_data.get_user_data(message.from_user.id)['folders']:
        await message.answer("Сначала создай хотя бы одну папку!")
        return

    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    for folder in user_data.get_user_data(message.from_user.id)['folders']:
        keyboard.add(folder)
    keyboard.add("🔙 Назад")
    
    await BotStates.waiting_for_folder_to_edit.set()
    await message.answer("Выбери папку для изменения промпта:", reply_markup=keyboard)

@dp.message_handler(state=BotStates.waiting_for_folder_to_edit)
async def process_folder_selection(message: types.Message, state: FSMContext):
    if message.text == "🔙 Назад":
        await state.finish()
        await back_to_main_menu(message, state)
        return

    if message.text not in user_data.get_user_data(message.from_user.id)['folders']:
        await message.answer("Такой папки нет. Попробуй еще раз")
        return

    await state.update_data(selected_folder=message.text)
    await BotStates.waiting_for_prompt.set()
    await message.answer(
        f"Текущий промпт для папки {message.text}:\n"
        f"{user_data.get_user_data(message.from_user.id)['prompts'][message.text]}\n\n"
        "Введи новый промпт:"
    )

@dp.message_handler(state=BotStates.waiting_for_prompt)
async def process_new_prompt(message: types.Message, state: FSMContext):
    data = await state.get_data()
    folder = data['selected_folder']
    
    user_data.get_user_data(message.from_user.id)['prompts'][folder] = message.text
    user_data.save()
    
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    buttons = [
        "📁 Создать папку",
        "📋 Список папок",
        "✏️ Изменить промпт",
        "⚙️ Настройка ИИ",
        "🔄 Запустить анализ",
        "📊 История отчетов",
        "⏰ Настроить расписание"
    ]
    keyboard.add(*buttons)
    
    await state.finish()
    await message.answer(
        f"Промпт для папки {folder} обновлен!",
        reply_markup=keyboard
    )

@dp.message_handler(lambda message: message.text == "⚙️ Настройка ИИ")
async def ai_settings(message: types.Message):
    # Получаем текущие настройки пользователя
    user_settings = user_data.get_user_data(message.from_user.id)['ai_settings']
    current_provider = PROVIDER_HIERARCHY[user_settings['provider_index']]['provider'].__name__
    current_model = user_settings['model']
    
    # Создаем клавиатуру для выбора модели
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    for provider_info in PROVIDER_HIERARCHY:
        for model in provider_info['models']:
            keyboard.add(
                types.InlineKeyboardButton(
                    f"{'✅ ' if model == current_model else ''}{model} ({provider_info['provider'].__name__})",
                    callback_data=f"select_model_{provider_info['provider'].__name__}_{model}"
                )
            )
    
    await message.answer(
        f"📊 Текущие настройки ИИ:\n\n"
        f"🔹 Провайдер: {current_provider}\n"
        f"🔹 Модель: {current_model}\n\n"
        f"ℹ️ Выберите предпочитаемую модель из списка:",
        reply_markup=keyboard
    )

@dp.callback_query_handler(lambda c: c.data.startswith('select_model_'))
async def process_model_selection(callback_query: types.CallbackQuery):
    _, provider_name, model = callback_query.data.split('_', 2)
    
    # Обновляем настройки пользователя
    for index, provider_info in enumerate(PROVIDER_HIERARCHY):
        if provider_info['provider'].__name__ == provider_name:
            user_data.get_user_data(callback_query.from_user.id)['ai_settings']['provider_index'] = index
            break
    user_data.get_user_data(callback_query.from_user.id)['ai_settings']['model'] = model
    user_data.save()
    
    await callback_query.message.edit_text(
        f"✅ Модель {model} от провайдера {provider_name} успешно выбрана!"
    )

async def try_gpt_request(prompt: str, posts_text: str, user_id: int):
    """Пытаемся получить ответ от GPT, перебирая провайдеров"""
    last_error = None
    rate_limited_providers = set()
    
    # Очищаем временные файлы и кэш
    try:
        # Чистим временные файлы
        temp_dir = tempfile.gettempdir()
        for filename in os.listdir(temp_dir):
            if filename.startswith('g4f_') or filename.startswith('gpt_'):
                try:
                    os.remove(os.path.join(temp_dir, filename))
                except:
                    pass
                    
        # Чистим кэш сессий
        cache_dirs = ['.cache', '__pycache__', 'tmp']
        for dir_name in cache_dirs:
            if os.path.exists(dir_name):
                try:
                    shutil.rmtree(dir_name)
                except:
                    pass
    except Exception as e:
        logger.warning(f"Ошибка при очистке кэша: {str(e)}")
    
    # Всегда начинаем с DDG
    providers_to_try = [PROVIDER_HIERARCHY[0]]  # DDG первый
    other_providers = PROVIDER_HIERARCHY[1:]  # Остальные в случайном порядке
    random.shuffle(other_providers)
    providers_to_try.extend(other_providers)
    
    # Генерируем случайный ID сессии
    session_id = ''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=32))
    
    for provider_info in providers_to_try:
        if provider_info['provider'] in rate_limited_providers:
            continue
            
        try:
            logger.info(f"Пробую провайдера {provider_info['provider'].__name__}")
            
            # Проверяем поддержку модели
            current_model = user_data.get_user_data(user_id)['ai_settings']['model']
            if current_model not in provider_info['models']:
                model_to_use = provider_info['models'][0]
                logger.info(f"Модель {current_model} не поддерживается, использую {model_to_use}")
            else:
                model_to_use = current_model
            
            # Добавляем случайные заголовки и параметры
            g4f.debug.logging = False
            g4f.check_version = False
            
            # Генерируем рандомные параметры для запроса
            headers = {
                'User-Agent': f'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/{random.randint(500, 600)}.{random.randint(1, 99)}',
                'Accept-Language': f'en-US,en;q=0.{random.randint(1, 9)}',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
                'Cache-Control': 'no-cache',
                'Pragma': 'no-cache',
                'X-Session-ID': session_id,  # Уникальный ID для каждого запроса
                'X-Client-ID': f'{random.randint(1000, 9999)}-{random.randint(1000, 9999)}',
                'X-Request-ID': f'{random.randint(1000, 9999)}-{random.randint(1000, 9999)}'
            }
            
            # Добавляем случайную задержку
            await asyncio.sleep(random.uniform(1.0, 3.0))
            
            response = await g4f.ChatCompletion.create_async(
                model=model_to_use,
                messages=[{"role": "user", "content": f"{prompt}\n\nДанные для анализа:\n{posts_text}"}],
                provider=provider_info['provider'],
                headers=headers,
                proxy=None,
                timeout=30
            )
            
            if response and len(response.strip()) > 0:
                return response
            else:
                raise Exception("Пустой ответ от провайдера")
            
        except Exception as e:
            error_str = str(e)
            last_error = error_str
            logger.error(f"Ошибка с провайдером {provider_info['provider'].__name__}: {error_str}")
            
            if "429" in error_str or "ERR_INPUT_LIMIT" in error_str:
                rate_limited_providers.add(provider_info['provider'])
                logger.warning(f"Провайдер {provider_info['provider'].__name__} временно заблокирован")
                await asyncio.sleep(5.0)
            else:
                await asyncio.sleep(1.0)
                
            continue
    
    if len(rate_limited_providers) > 0:
        raise Exception(f"Все доступные провайдеры временно заблокированы. Попробуйте позже. Последняя ошибка: {last_error}")
    else:
        raise Exception(f"Все провайдеры перепробованы. Последняя ошибка: {last_error}")

async def get_channel_posts(channel_link: str, hours: int = 24) -> list:
    """Получаем посты из канала за последние hours часов"""
    try:
        logger.info(f"Получаю посты из канала {channel_link}")
        
        if not is_valid_channel(channel_link):
            logger.error(f"Невалидная ссылка на канал: {channel_link}")
            return []
            
        try:
            # Пытаемся присоединиться к каналу
            channel = await client.get_entity(channel_link)
            try:
                await client(JoinChannelRequest(channel))
                logger.info(f"Успешно присоединился к каналу {channel_link}")
            except Exception as e:
                logger.warning(f"Не удалось присоединиться к каналу {channel_link}: {str(e)}")
                # Продолжаем работу, возможно мы уже подписаны
        except (ChannelPrivateError, UsernameNotOccupiedError) as e:
            logger.error(f"Не удалось получить доступ к каналу {channel_link}: {str(e)}")
            return []
        
        # Получаем историю сообщений
        posts = []
        time_threshold = datetime.now(channel.date.tzinfo) - timedelta(hours=hours)
        
        async for message in client.iter_messages(channel, limit=100):
            if message.date < time_threshold:
                break
                
            if message.text and len(message.text.strip()) > 0:
                posts.append(message.text)
        
        logger.info(f"Получено {len(posts)} постов из канала {channel_link}")
        return posts
        
    except Exception as e:
        logger.error(f"Ошибка при получении постов из канала {channel_link}: {str(e)}")
        return []

@dp.message_handler(lambda message: message.text == "📊 История отчетов")
async def show_reports(message: types.Message):
    reports = get_user_reports(message.from_user.id)
    if not reports:
        await message.answer("У вас пока нет сохраненных отчетов")
        return
        
    text = "📊 Последние отчеты:\n\n"
    for folder, content, created_at in reports:
        dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
        text += f"📁 {folder} ({dt.strftime('%Y-%m-%d %H:%M')})\n"
        
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    for folder, _, _ in reports:
        keyboard.add(types.InlineKeyboardButton(
            f"📄 Отчет по {folder}",
            callback_data=f"report_{folder}"
        ))
        
    await message.answer(text, reply_markup=keyboard)

@dp.callback_query_handler(lambda c: c.data.startswith('report_'))
async def show_report_content(callback_query: types.CallbackQuery):
    folder = callback_query.data.replace('report_', '')
    reports = get_user_reports(callback_query.from_user.id)
    
    for rep_folder, content, created_at in reports:
        if rep_folder == folder:
            dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
            await callback_query.message.answer(
                f"📊 Отчет по папке {folder}\n"
                f"📅 {dt.strftime('%Y-%m-%d %H:%M')}\n\n"
                f"{content}"
            )
            break

@dp.message_handler(lambda message: message.text == "⏰ Настроить расписание")
async def setup_schedule_start(message: types.Message):
    user = user_data.get_user_data(message.from_user.id)
    if not user['folders']:
        await message.answer("Сначала создайте хотя бы одну папку!")
        return
        
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    for folder in user['folders']:
        keyboard.add(folder)
    keyboard.add("🔙 Назад")
    
    await BotStates.waiting_for_schedule_folder.set()
    await message.answer(
        "Выберите папку для настройки расписания:",
        reply_markup=keyboard
    )

@dp.message_handler(state=BotStates.waiting_for_schedule_folder)
async def process_schedule_folder(message: types.Message, state: FSMContext):
    if message.text == "🔙 Назад":
        await state.finish()
        await back_to_main_menu(message, state)
        return
        
    user = user_data.get_user_data(message.from_user.id)
    if message.text not in user['folders']:
        await message.answer("Такой папки нет. Попробуйте еще раз")
        return
        
    await state.update_data(schedule_folder=message.text)
    await BotStates.waiting_for_schedule_time.set()
    
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add("🔙 Назад")
    
    await message.answer(
        "Введите время для ежедневного анализа в формате HH:MM (например, 09:00):",
        reply_markup=keyboard
    )

@dp.message_handler(state=BotStates.waiting_for_schedule_time)
async def process_schedule_time(message: types.Message, state: FSMContext):
    if message.text == "🔙 Назад":
        await state.finish()
        await back_to_main_menu(message, state)
        return

    if not re.match(r'^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$', message.text):
        await message.answer("Неверный формат времени. Используйте формат HH:MM (например, 09:00)")
        return
        
    data = await state.get_data()
    folder = data['schedule_folder']
    
    # Сохраняем расписание
    save_schedule(message.from_user.id, folder, message.text)
    
    # Добавляем задачу в планировщик
    hour, minute = map(int, message.text.split(':'))
    job_id = f"analysis_{message.from_user.id}_{folder}"
    
    scheduler.add_job(
        run_scheduled_analysis,
        'cron',
        hour=hour,
        minute=minute,
        id=job_id,
        replace_existing=True,
        args=[message.from_user.id, folder]
    )
    
    await state.finish()
    await message.answer(
        f"✅ Расписание установлено! Папка {folder} будет анализироваться ежедневно в {message.text}",
        reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add(*[
            "📁 Создать папку",
            "📋 Список папок",
            "✏️ Изменить промпт",
            "⚙️ Настройка ИИ",
            "🔄 Запустить анализ",
            "📊 История отчетов",
            "⏰ Настроить расписание"
        ])
    )

async def run_scheduled_analysis(user_id: int, folder: str):
    """Запуск анализа по расписанию"""
    try:
        user = user_data.get_user_data(user_id)
        channels = user['folders'][folder]
        
        all_posts = []
        for channel in channels:
            if not is_valid_channel(channel):
                continue
                
            posts = await get_channel_posts(channel)
            if posts:
                all_posts.extend(posts)
                
        if not all_posts:
            logger.error(f"Не удалось получить посты для автоматического анализа папки {folder}")
            return
            
        posts_text = "\n\n---\n\n".join(all_posts)
        prompt = user['prompts'][folder]
        
        response = await try_gpt_request(prompt, posts_text, user_id)
        
        # Сохраняем отчет
        save_report(user_id, folder, response)
        
        # Логируем успешное завершение отчета
        logger.info("отчет удался")
        
        # Отправляем уведомление пользователю
        await bot.send_message(
            user_id,
            f"✅ Автоматический анализ папки {folder} завершен!\n"
            f"Используйте '📊 История отчетов' чтобы просмотреть результат."
        )
        
    except Exception as e:
        logger.error(f"Ошибка при автоматическом анализе: {str(e)}")

@dp.message_handler(lambda message: message.text == "🔄 Запустить анализ")
async def start_analysis(message: types.Message):
    user = user_data.get_user_data(message.from_user.id)
    if not user['folders']:
        await message.answer("Сначала создайте хотя бы одну папку!")
        return
        
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    
    # Добавляем кнопки для каждой папки
    for folder in user['folders']:
        # Подменю для каждой папки
        folder_keyboard = types.InlineKeyboardMarkup(row_width=2)
        folder_keyboard.add(
            types.InlineKeyboardButton(
                "📝 TXT",
                callback_data=f"analyze_{folder}_txt"
            ),
            types.InlineKeyboardButton(
                "📊 PDF",
                callback_data=f"analyze_{folder}_pdf"
            ),
            types.InlineKeyboardButton(
                "📎 Оба формата",
                callback_data=f"analyze_{folder}_both"
            )
        )
        
        keyboard.add(types.InlineKeyboardButton(
            f"📁 {folder}",
            callback_data=f"format_{folder}"
        ))
    
    # Добавляем кнопку "Анализировать все" и "Назад"
    keyboard.add(types.InlineKeyboardButton(
        "📊 Анализировать все папки",
        callback_data="format_all"
    ))
    keyboard.add(types.InlineKeyboardButton(
        "🔙 В главное меню",
        callback_data="back_to_main"
    ))
    
    await message.answer(
        "Выберите папку для анализа:",
        reply_markup=keyboard
    )

@dp.callback_query_handler(lambda c: c.data.startswith('format_'))
async def choose_format(callback_query: types.CallbackQuery):
    folder = callback_query.data.replace('format_', '')
    
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    if folder == 'all':
        keyboard.add(
            types.InlineKeyboardButton("📝 TXT", callback_data="analyze_all_txt"),
            types.InlineKeyboardButton("📊 PDF", callback_data="analyze_all_pdf"),
            types.InlineKeyboardButton("📎 Оба формата", callback_data="analyze_all_both")
        )
    else:
        keyboard.add(
            types.InlineKeyboardButton("📝 TXT", callback_data=f"analyze_{folder}_txt"),
            types.InlineKeyboardButton("📊 PDF", callback_data=f"analyze_{folder}_pdf"),
            types.InlineKeyboardButton("📎 Оба формата", callback_data=f"analyze_{folder}_both")
        )
    
    keyboard.add(types.InlineKeyboardButton("🔙 Назад", callback_data="back_to_folders"))
    
    await callback_query.message.edit_text(
        f"Выберите формат отчета для {'всех папок' if folder == 'all' else f'папки {folder}'}:",
        reply_markup=keyboard
    )

@dp.callback_query_handler(lambda c: c.data.startswith('analyze_'))
async def process_analysis_choice(callback_query: types.CallbackQuery):
    # Парсим параметры из callback_data
    params = callback_query.data.replace('analyze_', '').split('_')
    if len(params) != 2:
        await callback_query.message.answer("❌ Ошибка в параметрах анализа")
        return
        
    choice, format_type = params
    user = user_data.get_user_data(callback_query.from_user.id)
    
    await callback_query.message.edit_text("Начинаю анализ... Это может занять некоторое время")
    
    if choice == 'all':
        folders = user['folders'].items()
    else:
        folders = [(choice, user['folders'][choice])]
    
    for folder, channels in folders:
        await callback_query.message.answer(f"Анализирую папку {folder}...")
        
        all_posts = []
        for channel in channels:
            if not is_valid_channel(channel):
                continue
                
            posts = await get_channel_posts(channel)
            if posts:
                all_posts.extend(posts)
            else:
                await callback_query.message.answer(f"⚠️ Не удалось получить посты из канала {channel}")
        
        if not all_posts:
            await callback_query.message.answer(f"❌ Не удалось получить посты из каналов в папке {folder}")
            continue
            
        posts_text = "\n\n---\n\n".join(all_posts)
        prompt = user['prompts'][folder]
        
        try:
            response = await try_gpt_request(prompt, posts_text, callback_query.from_user.id)
            
            # Сохраняем отчет в БД
            save_report(callback_query.from_user.id, folder, response)
            
            files_to_send = []
            
            # Генерируем отчеты в выбранном формате
            if format_type in ['txt', 'both']:
                txt_filename = generate_txt_report(response, folder)
                files_to_send.append(txt_filename)
                
            if format_type in ['pdf', 'both']:
                try:
                    pdf_filename = generate_pdf_report(response, folder)
                    files_to_send.append(pdf_filename)
                except Exception as pdf_error:
                    logger.error(f"Ошибка при создании PDF: {str(pdf_error)}")
                    await callback_query.message.answer("⚠️ Не удалось создать PDF версию отчета")
            
            # Отправляем файлы
            for filename in files_to_send:
                with open(filename, 'rb') as f:
                    await callback_query.message.answer_document(
                        f,
                        caption=f"✅ Анализ для папки {folder} ({os.path.splitext(filename)[1][1:].upper()})"
                    )
                os.remove(filename)
            
        except Exception as e:
            error_msg = f"❌ Ошибка при анализе папки {folder}: {str(e)}"
            logger.error(error_msg)
            await callback_query.message.answer(error_msg)
    
    await callback_query.message.answer("✅ Анализ завершен!")

@dp.message_handler(lambda message: message.text == "🔙 Назад", state="*")
async def back_to_main_menu(message: types.Message, state: FSMContext):
    await state.finish()
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    buttons = [
        "📁 Создать папку",
        "📋 Список папок",
        "✏️ Изменить промпт",
        "⚙️ Настройка ИИ",
        "🔄 Запустить анализ",
        "📊 История отчетов",
        "⏰ Настроить расписание"
    ]
    await message.answer("Главное меню:", reply_markup=keyboard)

@dp.callback_query_handler(lambda c: c.data.startswith('remove_channel_'))
async def remove_channel(callback_query: types.CallbackQuery):
    _, folder, channel = callback_query.data.split('_', 2)
    user = user_data.get_user_data(callback_query.from_user.id)
    
    if folder in user['folders'] and channel in user['folders'][folder]:
        user['folders'][folder].remove(channel)
        user_data.save()
        
        # Обновляем меню
        await edit_folder_menu(callback_query)

async def main():
    # Запускаем клиент Telethon
    await client.start()
    
    # Получаем инфу о боте
    me = await bot.get_me()
    logger.info(f"Бот @{me.username} запущен!")
    
    # Запускаем планировщик
    scheduler.start()
    
    # Восстанавливаем сохраненные расписания
    for user_id, folder, time in get_active_schedules():
        hour, minute = map(int, time.split(':'))
        job_id = f"analysis_{user_id}_{folder}"
        
        scheduler.add_job(
            run_scheduled_analysis,
            'cron',
            hour=hour,
            minute=minute,
            id=job_id,
            replace_existing=True,
            args=[user_id, folder]
        )
        logger.info(f"Восстановлено расписание: {job_id} в {time}")
    
    # Запускаем бота
    await dp.start_polling()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # Останавливаем планировщик при выходе
        scheduler.shutdown()
        logger.info("Бот остановлен") 