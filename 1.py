import asyncio
import logging
import sqlite3
import re
import requests
import nest_asyncio
import random
import os
from aiohttp import web
import traceback
nest_asyncio.apply()

from aiogram import Bot, Dispatcher, F, types
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, BusinessConnection, BotCommand
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
import aiohttp

# --- Конфигурация ---
TOKEN = os.getenv('TOKEN')
WEB_SERVER_HOST = '0.0.0.0'  # Хост для веб-сервера
WEB_SERVER_PORT = 3000       # Порт для веб-сервера
WEBHOOK_PATH = '/webhook'    # Путь для вебхука

DB_PATH = "aromas.db"
BASE_WEBHOOK_URL = os.getenv('WEBHOOK_BASE_URL')
DEEPSEEK_API = os.getenv('DEEPSEEK')

# --- Инициализация бота ---
bot = Bot(token=TOKEN)
dp = Dispatcher()

# --- DeepSeek и данные Bahur ---
def load_bahur_data():
    with open("bahur_data.txt", "r", encoding="utf-8") as f:
        return f.read()

# --- Поиск нот через внешний API Bahur ---
async def search_note_api(note):
    url = f"https://api.alexander-dev.ru/bahur/search/?text={note}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=10) as resp:
            resp.raise_for_status()
            return await resp.json()

BAHUR_DATA = load_bahur_data()

def main_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    
    # Первый ряд (1 кнопка)
    builder.row(
        InlineKeyboardButton(text='🧸 Ai-Медвежонок', callback_data='ai')
    )
    
    # Второй ряд (3 кнопки)
    builder.row(
        InlineKeyboardButton(text='🍦 Прайс', url="https://drive.google.com/file/d/1J70LlZwh6g7JOryDG2br-weQrYfv6zTc/view?usp=sharing"),
        InlineKeyboardButton(text='🍿 Магазин', url="https://www.bahur.store/m/"),
        InlineKeyboardButton(text='♾️ Вопросы', url="https://vk.com/@bahur_store-optovye-praisy-ot-bahur")
    )
    
    # Третий ряд (3 кнопки)
    builder.row(
        InlineKeyboardButton(text='🎮 Чат', url="https://t.me/+VYDZEvbp1pce4KeT"),
        InlineKeyboardButton(text='💎 Статьи', url="https://vk.com/bahur_store?w=app6326142_-133936126%2523w%253Dapp6326142_-133936126"),
        InlineKeyboardButton(text='🏆 Отзывы', url="https://vk.com/@bahur_store")
    )

    builder.row(
        InlineKeyboardButton(text='🍓 Ноты', callback_data='instruction')
    )
    
    return builder.as_markup()  # Убрал resize_keyboard=True для Inline клавиатуры

def create_reply_menu() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    
    builder.row(KeyboardButton(text='🍓 Ноты'))
    builder.row(
        KeyboardButton(text='🍦 Прайс'),
        KeyboardButton(text='🍿 Магазин'),
        KeyboardButton(text='♾️ Вопросы')
    )
    builder.row(
        KeyboardButton(text='🎮 Чат'),
        KeyboardButton(text='💎 Статьи'),
        KeyboardButton(text='🏆 Отзывы')
    )
    builder.row(KeyboardButton(text='🧸 Ai-Медвежонок'))
    
    return builder.as_markup(resize_keyboard=True)

# --- Настройки ---
TOKEN = '8102330882:AAESnqYWciSpebuEmghAqjTKcgJtq3fSQ-4'

# --- DeepSeek и данные Bahur ---
def load_bahur_data():
    with open("bahur_data.txt", "r", encoding="utf-8") as f:
        return f.read()

BAHUR_DATA = load_bahur_data()

def greet():
    return random.choice([
    "Привет-привет! 🐾 Готов раскрыть все секреты продаж — спрашивай смело!",
    "Эй, друг! 🌟 Ai-Медвежонок на связи — давай обсудим твои вопросы за виртуальным мёдом!",
    "Мягкий привет! 🧸✨ Хочешь, расскажу, как продавать лучше, чем медведь в лесу малину?",
    "Здравствуй, человек! 🌟 Готов устроить мозговой штурм? Задавай вопрос — я в деле!",
    "Приветик из цифровой берлоги! 🐻‍❄️💻 Чем могу помочь? (Совет: спроси что-нибудь классное!)",
    "Алло-алло! 📞 Ты дозвонился до самого продающего медведя в сети. Вопросы — в студию!",
    "Хей-хей! 🎯 Готов к диалогу, как пчела к мёду. Запускай свой запрос!",
    "Тыдыщь! 🎩✨ Ai-Медвежонок-волшебник приветствует тебя. Какой вопрос спрятан у тебя в рукаве?",
    "Привет, землянин! 👽🐻 (Шучу, я просто AI). Давай общаться — спрашивай что угодно!"
    ])


async def ask_deepseek(question):
    url = "https://api.deepseek.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API}",  # <-- Вставьте свой ключ
        "Content-Type": "application/json"
    }
    data = {
        "model": "deepseek-chat",
        "messages": [
            {
                "role": "system",
                "content": (
                    "Ты - Ai-Медвежонок (менеджер по продажам), здоровайся креативно, зная это. Используй ТОЛЬКО эти данные для ответа клиенту:\n"
                    f"{BAHUR_DATA}\n"
                    "Если есть подходящая ссылка из данных, обязательно включи её в ответ. "
                    "Отвечай только по теме вопроса, без лишней информации, на русском языке, без markdown, обязательно с крутыми смайликами."
                    "Если вопрос не по теме, то обязательно переведи в шутку, никаких 'не знаю' и аккуратно предложи купить духи"
                    "Когда вставляешь ссылку, используй HTML-формат: <a href='ССЫЛКА'>ТЕКСТ</a>. Не используй markdown."
                    "Но если он пишет несколько слов, которые похожи на ноты, предложи ему нажать на кнопку 🍓 Ноты в меню"
                    "Не пиши про номера ароматов в прайсе"
                )
            },
            {
                "role": "user",
                "content": f"{question}"
            }
        ],
        "temperature": 0.9
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=data, timeout=30) as resp:
            resp.raise_for_status()
            result = await resp.json()
            return result["choices"][0]["message"]["content"].strip()

# --- Логирование ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=TOKEN)
dp = Dispatcher()

# --- Состояния пользователей для AI ---
user_states = {}

# --- Healthcheck endpoint ---
async def healthcheck(request):
    logging.info("Healthcheck requested")
    return web.Response(text="OK")

# --- Обработка обычных сообщений ---
@dp.message(F.text & ~F.text.startswith('/'))
async def handle_regular_message(message: Message):
    try:
        logging.info(f"[SUPERLOG] Incoming message: {message}")
        user_id = message.from_user.id
        logging.info(f"[SUPERLOG] user_id: {user_id}, text: {message.text}")
        state = user_states.get(user_id)
        logging.info(f"[SUPERLOG] user_state: {state}")
        # Режим AI
        if state == 'awaiting_ai_question':
            question = message.text.strip()
            logging.info(f"[SUPERLOG] DeepSeek question: {question}")
            ai_answer = await ask_deepseek(question)
            ai_answer = ai_answer.replace('*', '')
            logging.info(f"[SUPERLOG] DeepSeek answer: {ai_answer}")
            await message.answer(ai_answer, parse_mode=ParseMode.HTML)
            logging.info("[SUPERLOG] AI answer sent")
            return
        # Режим поиска нот через внешний API
        if state == 'awaiting_note_search':
            note = message.text.strip()
            logging.info(f"[SUPERLOG] Note search: {note}")
            result = await search_note_api(note)
            logging.info(f"[SUPERLOG] Note search API result: {result}")
            if result.get("status") == "success":
                brand = result.get("brand")
                aroma = result.get("aroma")
                description = result.get("description")
                url = result.get("url")
                aroma_id = result.get("ID")
                logging.info(f"[SUPERLOG] Found: {brand} {aroma} (id={aroma_id}) url={url}")
                keyboard = [
                    [
                        InlineKeyboardButton(text='🚀 Подробнее', url=url),
                        InlineKeyboardButton(text='♾️ Повторить', callback_data=f'repeatapi_{aroma_id}')
                    ]
                ]
                reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
                await message.answer(
                    f'✨ {brand} {aroma}\n\n{description}',
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.HTML
                )
                logging.info("[SUPERLOG] Note answer sent")
            else:
                logging.info(f"[SUPERLOG] Nothing found for note: {note}")
                await message.answer("Ничего не найдено по этой ноте 😢")
            return
        logging.info("[SUPERLOG] No special state, message ignored")
    except Exception as e:
        logging.error(f"[SUPERLOG] Exception in handle_regular_message: {e}\n{traceback.format_exc()}")
        await message.answer(f"[ERROR] {e}")

# --- Обработка обычных команд ---
@dp.message(Command("start"))
async def cmd_start(message: Message):
    logging.info(f"/start command from user {message.from_user.id}")
    print("Получена команда /start")
    text = (
        '<b>Здравствуйте!\n\n'
        'Я — ваш ароматный помощник от BAHUR.\n'
        '🍓 Ищу ноты и 🧸 отвечаю на вопросы с любовью. ❤</b>'
    )
    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=main_menu()
    )
    logging.info("Sent start message with main menu")

# --- Обработка callback-кнопок ---
@dp.callback_query()
async def handle_callback(callback: CallbackQuery):
    try:
        logging.info(f"[SUPERLOG] Incoming callback: {callback}")
        data = callback.data
        user_id = callback.from_user.id
        logging.info(f"[SUPERLOG] Callback data: {data}, user_id: {user_id}")
        if data != 'ai' and user_id in user_states:
            user_states.pop(user_id, None)
            logging.debug(f"[SUPERLOG] AI state reset for user {user_id}")
        if data == 'instruction':
            user_states[user_id] = 'awaiting_note_search'
            text = (
                '🍉 Напиши любую ноту (например, апельсин, клубника) — я найду ароматы с этой нотой!'
            )
            await callback.message.edit_text(
                text,
                parse_mode="HTML"
            )
            logging.info("[SUPERLOG] Switched user to note search mode")
            await callback.answer()
            return
        elif data == 'ai':
            user_states[user_id] = 'awaiting_ai_question'
            result = greet()
            await callback.message.edit_text(result)
            logging.info("[SUPERLOG] Switched user to AI mode and sent greeting")
        elif data.startswith('repeatapi_'):
            aroma_id = data.split('_', 1)[1]
            logging.info(f"[SUPERLOG] Repeatapi callback with aroma_id={aroma_id}")
            url = f"https://api.alexander-dev.ru/bahur/search/?id={aroma_id}"
            logging.info(f"[SUPERLOG] Repeatapi request url: {url}")
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=10) as response:
                    logging.info(f"[SUPERLOG] Repeatapi response status: {response.status}")
                    response.raise_for_status()
                    result = await response.json()
            logging.info(f"[SUPERLOG] Repeatapi API result: {result}")
            if result.get("status") == "success":
                brand = result.get("brand")
                aroma = result.get("aroma")
                description = result.get("description")
                url = result.get("url")
                aroma_id = result.get("ID")
                logging.info(f"[SUPERLOG] Repeatapi found: {brand} {aroma} (id={aroma_id}) url={url}")
                keyboard = [
                    [
                        InlineKeyboardButton(text='🚀 Подробнее', url=url),
                        InlineKeyboardButton(text='♾️ Повторить', callback_data=f'repeatapi_{aroma_id}')
                    ]
                ]
                reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
                await callback.message.edit_text(
                    f'✨ {brand} {aroma}\n\n{description}',
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.HTML
                )
                logging.info("[SUPERLOG] Repeatapi answer sent")
            else:
                logging.info(f"[SUPERLOG] Repeatapi nothing found for id: {aroma_id}")
                await callback.message.edit_text("Ничего не найдено по этой ноте 😢")
            await callback.answer()
            return
        await callback.answer()
        logging.debug("[SUPERLOG] Callback answered")
    except Exception as e:
        logging.error(f"[SUPERLOG] Exception in handle_callback: {e}\n{traceback.format_exc()}")
        await callback.message.answer(f"[ERROR] {e}")

# --- Настройка вебхука ---
async def on_startup(bot: Bot):
    logging.info("[SUPERLOG] on_startup: setting webhook...")
    await bot.set_webhook(f"{BASE_WEBHOOK_URL}{WEBHOOK_PATH}")
    logging.info("[SUPERLOG] Webhook set!")

async def on_shutdown(bot: Bot):
    logging.warning('[SUPERLOG] Выключение бота...')
    await bot.delete_webhook()
    logging.warning('[SUPERLOG] Бот выключен')

# --- Запуск приложения ---
def main():
    logging.info("[SUPERLOG] Starting main()...")
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    app = web.Application()
    app.router.add_get("/", healthcheck)
    logging.info("[SUPERLOG] Healthcheck endpoint added at /")
    webhook_requests_handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
    )
    logging.info("[SUPERLOG] SimpleRequestHandler created")
    webhook_requests_handler.register(app, path=WEBHOOK_PATH)
    logging.info(f"[SUPERLOG] Webhook handler registered at {WEBHOOK_PATH}")
    setup_application(app, dp, bot=bot)
    logging.info("[SUPERLOG] Application setup complete")
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    try:
        logging.info(f"[SUPERLOG] Running app on {WEB_SERVER_HOST}:{WEB_SERVER_PORT}")
        web.run_app(app, host=WEB_SERVER_HOST, port=WEB_SERVER_PORT)
    except KeyboardInterrupt:
        logger.info("[SUPERLOG] Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"[SUPERLOG] Exception in main: {e}\n{traceback.format_exc()}")

# --- Утилита для отправки markdown-сообщений ---
def send_markdown_message(message, text):
    return message.answer(text, parse_mode="Markdown")

# Пример использования send_markdown_message:
# await send_markdown_message(message, your_markdown_text)

if __name__ == "__main__":
    main()