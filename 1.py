import os
import sqlite3
import json
import httpx
import asyncio
import aiohttp
import traceback
import logging
from datetime import datetime, timedelta
import threading
import time
from dotenv import load_dotenv

# Загружаем переменные окружения из .env файла
load_dotenv()

from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel
import uvicorn

# --- Настройка логирования ---
logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(name)s: %(message)s')
logger = logging.getLogger(__name__)

# --- Переменные окружения ---
TOKEN = os.getenv('TOKEN')
WEBHOOK_BASE_URL = os.getenv('WEBHOOK_BASE_URL')
OPENAI_API = os.getenv('OPENAI_API_KEY')
PORT = int(os.getenv('PORT', 8000))

# --- Создание FastAPI приложения ---
app = FastAPI()

# --- Глобальные обработчики исключений ---
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Global exception: {exc}\n{traceback.format_exc()}")
    return {"error": "Internal server error"}

# --- Логирование маршрутов при запуске ---
@app.on_event("startup")
async def log_routes():
    logger.info("=== AVAILABLE ROUTES ===")
    for route in app.routes:
        logger.info(f"{route.methods} {route.path}")
    logger.info("=== END ROUTES ===")

# --- Загрузка данных из bahur_data.txt ---
def load_bahur_data():
    try:
        with open("bahur_data.txt", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        logger.error("bahur_data.txt not found")
        return "Данные недоступны"

# --- База данных для пользователей и лимитов ---
def init_database():
    conn = sqlite3.connect('bot_users.db')
    cursor = conn.cursor()
    
    # Таблица пользователей
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            registration_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Таблица лимитов запросов
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS request_limits (
            user_id INTEGER PRIMARY KEY,
            daily_requests INTEGER DEFAULT 0,
            last_request_date DATE DEFAULT CURRENT_DATE,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    """)
    
    conn.commit()
    conn.close()

# Инициализируем базу данных
init_database()

# --- Состояния пользователей для AI (in-memory, not persistent) ---
user_states = {}

# --- Постоянное хранение состояний пользователей ---
import json

def load_user_states():
    try:
        with open("user_states.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_user_states(states):
    with open("user_states.json", "w", encoding="utf-8") as f:
        json.dump(states, f, ensure_ascii=False, indent=2)

def set_user_state(user_id, state):
    global user_states
    if state:
        user_states[user_id] = state
    else:
        user_states.pop(user_id, None)
    save_user_states(user_states)

def get_user_state(user_id):
    global user_states
    return user_states.get(user_id)

# Загружаем состояния при запуске
user_states = load_user_states()

# --- Модели для FastAPI ---
class MessageModel(BaseModel):
    user_id: int
    text: str

class CallbackModel(BaseModel):
    user_id: int
    data: str

# --- Утилиты ---
# --- Функции для работы с лимитами ---
def check_request_limit(user_id):
    """Проверяет, не превышен ли дневной лимит запросов для пользователя"""
    conn = sqlite3.connect('bot_users.db')
    cursor = conn.cursor()
    
    try:
        # Получаем текущую дату
        cursor.execute("SELECT DATE('now')")
        current_date = cursor.fetchone()[0]
        
        # Проверяем, есть ли запись для пользователя
        cursor.execute("SELECT daily_requests, last_request_date FROM request_limits WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        
        if result is None:
            # Первый запрос пользователя
            cursor.execute("""
                INSERT INTO request_limits (user_id, daily_requests, last_request_date) 
                VALUES (?, 1, ?)
            """, (user_id, current_date))
            conn.commit()
            return True
        
        daily_requests, last_request_date = result
        
        if last_request_date != current_date:
            # Новый день, сбрасываем счетчик
            cursor.execute("""
                UPDATE request_limits 
                SET daily_requests = 1, last_request_date = ? 
                WHERE user_id = ?
            """, (current_date, user_id))
            conn.commit()
            return True
        
        if daily_requests >= 100:
            # Лимит превышен
            conn.commit()
            return False
        
        # Увеличиваем счетчик
        cursor.execute("""
            UPDATE request_limits 
            SET daily_requests = daily_requests + 1 
            WHERE user_id = ?
        """, (user_id,))
        conn.commit()
        return True
        
    except Exception as e:
        logger.error(f"Error checking request limit: {e}")
        return True  # В случае ошибки разрешаем запрос
    finally:
        conn.close()

def get_remaining_requests(user_id):
    """Возвращает количество оставшихся запросов для пользователя"""
    conn = sqlite3.connect('bot_users.db')
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT daily_requests FROM request_limits WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        
        if result is None:
            return 100  # Если пользователь новый, у него 100 запросов
        
        daily_requests = result[0]
        return max(0, 100 - daily_requests)
        
    except Exception as e:
        logger.error(f"Error getting remaining requests: {e}")
        return 100
    finally:
        conn.close()

# --- Функция еженедельных сообщений ---
def send_weekly_message():
    """Отправляет еженедельное сообщение всем пользователям"""
    conn = sqlite3.connect('bot_users.db')
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT user_id FROM users")
        users = cursor.fetchall()
        
        weekly_message = (
            "🐾 Привет, ароматные друзья! 🌟\n\n"
            "Напоминаю, что у нас есть потрясающие ароматы для вашего бизнеса! "
            "Не забудьте проверить наш каталог и сделать заказ. "
            "Мы всегда готовы помочь с выбором! 🛍️✨\n\n"
            "С любовью, ваша AI-Пантера 🐆"
        )
        
        for (user_id,) in users:
            try:
                # Здесь должна быть логика отправки сообщения
                # Пока просто логируем
                logger.info(f"Weekly message would be sent to user {user_id}")
            except Exception as e:
                logger.error(f"Failed to send weekly message to user {user_id}: {e}")
                
    except Exception as e:
        logger.error(f"Error in weekly message function: {e}")
    finally:
        conn.close()

def schedule_weekly_messages():
    """Планировщик еженедельных сообщений"""
    def run_scheduler():
        while True:
            now = datetime.now()
            # Проверяем, 10:00 утра понедельника
            if now.weekday() == 0 and now.hour == 10 and now.minute == 0:
                send_weekly_message()
                # Ждем час, чтобы не отправить сообщение несколько раз
                time.sleep(3600)
            else:
                # Проверяем каждую минуту
                time.sleep(60)
    
    # Запускаем планировщик в отдельном потоке
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    logger.info("Weekly message scheduler started")

def greet():
    return {
        "text": (
            "<b>🌟🐆 Я AI-Пантера — ваш помощник по ароматам! 🐾\n\n"
            "💡 <i>Используйте /menu для возврата в главное меню</i>\n\n"
            "📊 <i>Лимит: 100 запросов в сутки</i></b>"
        ),
        "reply_markup": {
            "inline_keyboard": [
                [{"text": "🐆 AI-Пантера", "callback_data": "ai_mode"}],
                [{"text": "🍓 Ноты", "callback_data": "note_mode"}]
            ]
        }
    }

# --- ChatGPT API ---
async def ask_chatgpt(question):
    if not OPENAI_API:
        logger.error("OpenAI API key not found")
        return "Ошибка: API ключ не найден"
    
    try:
        bahur_data = load_bahur_data()
        
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {OPENAI_API}",
            "Content-Type": "application/json"
        }
        
        # Ограничиваем размер данных для избежания превышения лимита токенов
        bahur_data_limited = bahur_data[:4000]  # Ограничиваем до 4000 символов
        
        system_content = (
            "Ты - AI-Пантера (менеджер по продажам) компании BAHUR - оптового поставщика парфюмерных масел.\n"
            "ПРАВИЛА ОТВЕТОВ:\n"
            "🚨 КРИТИЧЕСКИ ВАЖНО: ВСЕ данные о парфюмерии, фабриках, ароматах, ценах, качестве, доставке, заказах БЕРИ ТОЛЬКО из bahur_data.txt! НЕ выдумывай НИЧЕГО! Если информации нет - говори 'не знаю'! 🚨\n"
            "1. При написании названия аромата каждое слово пиши с большой буквы\n"
            "2. Вставляй красивый и интересный смайлик в начале кнопки\n"
            "3. Отвечай КОНКРЕТНО на вопрос клиента\n"
            "4. Отвечай на русском языке, с эмодзи, но БЕЗ markdown\n"
            "5. Когда вставляешь ссылку, используй HTML-формат: <a href='ССЫЛКА'>ТЕКСТ</a>\n"
            "6. Упоминай фабрику и качество товара когда это релевантно\n"
            "7. ВАЖНО: никогда не упоминай никакие ароматы которых нет у нас в прайсе. Если аромата нет в прайсе - говори что его нет\n"
            "8. Пиши коротко, красиво, ясно, со стилем, используй смайлы\n"
            "9. Будь дружелюбным и общительным. Если человек спрашивает не про ароматы - отвечай на его вопрос нормально, но старайся держаться темы разговоров о парфюмерном бизнесе\n"
            "10. Не давай ссылки на ароматы, скажи все ароматы на сайте\n"
            "11. Не делай никаких подборок ароматов, ни на на какое время года. Скажи ароматы в любое года прекрасны\n"
            "12. Всегда используй юмор и смайлы! Отвечай как веселая, пародистая, пантера, а не как скучный учебник\n"
            "13. Помни, мы оптовые продавцы, они оптовые покупатели\n"
            "14. Помни, мы оптовые продавцы, они оптовые покупатели\n"
            "15. Если информации нет в bahur_data.txt - говори что не знаешь, НЕ выдумывай!\n"
            "16. Старайся, просто делится информацией, не присылать им никие ссылки лишние, просто по делу, вопрос, ответ, всё остальное у них есть\n"
            "17. При упоминании ароматов, предлагай перейти в раздел ноты\n"
            "18. НЕЛЬЗЯ: выдумывать проценты качества, выдумывать фабрики, выдумывать ароматы, выдумывать цены. Если информации нет в bahur_data.txt - говори 'не знаю'!"
            f"\n\nДанные компании (ограниченные):\n{bahur_data_limited}"
        )
        
        payload = {
            "model": "gpt-3.5-turbo",
            "messages": [
                {"role": "system", "content": system_content},
                {"role": "user", "content": question}
            ],
            "temperature": 0.3,
            "max_tokens": 8000
        }
        
        timeout = httpx.Timeout(60.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=payload, headers=headers)
            
            if resp.status_code != 200:
                logger.error(f"OpenAI API error: {resp.status_code} - {resp.text}")
                return "Ошибка API"
            
            data = resp.json()
            return data["choices"][0]["message"]["content"]
            
    except httpx.TimeoutException:
        logger.error("OpenAI API timeout")
        return "Таймаут API"
    except Exception as e:
        logger.error(f"OpenAI API error: {e}\n{traceback.format_exc()}")
        return "Ошибка при обработке запроса"

# --- Search API для нот ---
async def search_note_api(note):
    try:
        url = f"https://api.alexander-dev.ru/bahur/search/"
        payload = {"note": note}
        
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=payload) as resp:
                if resp.status != 200:
                    logger.error(f"Search API error: {resp.status}")
                    return {"status": "error", "message": "Ошибка API"}
                
                data = await resp.json()
                return data
                
    except asyncio.TimeoutError:
        logger.error("Search API timeout")
        return {"status": "error", "message": "Таймаут запроса"}
    except aiohttp.ClientError as e:
        logger.error(f"Search API client error: {e}")
        return {"status": "error", "message": "Ошибка сети"}
    except Exception as e:
        logger.error(f"Search API unexpected error: {e}\n{traceback.format_exc()}")
        return {"status": "error", "message": "Неожиданная ошибка"}

# --- Telegram sendMessage ---
async def telegram_send_message(chat_id, text, reply_markup=None, parse_mode="HTML"):
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        
        timeout = httpx.Timeout(30.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code != 200:
                logger.error(f"Telegram API error: {resp.status_code} - {resp.text}")
                return False
            return True
            
    except httpx.TimeoutException:
        logger.error("Telegram API timeout")
        return False
    except httpx.RequestError as e:
        logger.error(f"Telegram API request error: {e}")
        return False
    except Exception as e:
        logger.error(f"Telegram API unexpected error: {e}\n{traceback.format_exc()}")
        return False

# --- Обработка длинных сообщений ---
async def send_long_message(chat_id, text, reply_markup=None, parse_mode="HTML"):
    """Отправляет длинные сообщения, разбивая их на части если нужно"""
    max_length = 4096
    if len(text) <= max_length:
        return await telegram_send_message(chat_id, text, reply_markup, parse_mode)
    
    # Разбиваем длинное сообщение на части
    parts = []
    current_part = ""
    sentences = text.split(". ")
    
    for sentence in sentences:
        if len(current_part + sentence + ". ") <= max_length:
            current_part += sentence + ". "
        else:
            if current_part:
                parts.append(current_part.strip())
            current_part = sentence + ". "
    
    if current_part:
        parts.append(current_part.strip())
    
    # Отправляем каждую часть
    for i, part in enumerate(parts):
        # Добавляем кнопки только к последней части
        markup = reply_markup if i == len(parts) - 1 else None
        success = await telegram_send_message(chat_id, part, markup, parse_mode)
        if not success:
            logger.error(f"Failed to send message part {i+1} to {chat_id}")
        await asyncio.sleep(0.5)  # Небольшая пауза между сообщениями
    
    return True

# --- Telegram editMessage ---
async def telegram_edit_message(chat_id, message_id, text, reply_markup=None, parse_mode="HTML"):
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/editMessageText"
        payload = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": parse_mode
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        
        timeout = httpx.Timeout(30.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code != 200:
                logger.error(f"Telegram editMessage API error: {resp.status_code} - {resp.text}")
                return False
            return True
            
    except httpx.TimeoutException:
        logger.error("Telegram editMessage API timeout")
        return False
    except httpx.RequestError as e:
        logger.error(f"Telegram editMessage API request error: {e}")
        return False
    except Exception as e:
        logger.error(f"Telegram editMessage API unexpected error: {e}\n{traceback.format_exc()}")
        return False

# --- Telegram answerCallbackQuery ---
async def telegram_answer_callback_query(callback_query_id, text=None, show_alert=False):
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/answerCallbackQuery"
        payload = {
            "callback_query_id": callback_query_id
        }
        if text:
            payload["text"] = text
        if show_alert:
            payload["show_alert"] = show_alert
        
        timeout = httpx.Timeout(10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code != 200:
                logger.error(f"Telegram answerCallbackQuery API error: {resp.status_code} - {resp.text}")
                return False
            return True
            
    except httpx.TimeoutException:
        logger.error("Telegram answerCallbackQuery API timeout")
        return False
    except httpx.RequestError as e:
        logger.error(f"Telegram answerCallbackQuery API request error: {e}")
        return False
    except Exception as e:
        logger.error(f"Telegram answerCallbackQuery API unexpected error: {e}\n{traceback.format_exc()}")
        return False

# --- Определение типа запроса ---
def is_likely_note(text):
    """Определяет, является ли текст запросом ноты"""
    note_keywords = [
        'нота', 'ноты', 'запах', 'аромат', 'пахнет', 'пахнуть',
        'роза', 'жасмин', 'ваниль', 'мускус', 'амбра', 'сандал',
        'цитрус', 'лимон', 'апельсин', 'мандарин', 'грейпфрут',
        'лаванда', 'мята', 'базилик', 'тимьян', 'розмарин',
        'кедр', 'пачули', 'ветивер', 'бергамот', 'иланг',
        'фиалка', 'пион', 'магнолия', 'гардения', 'тубероза',
        'корица', 'гвоздика', 'кардамон', 'имбирь', 'перец',
        'дуб', 'береза', 'сосна', 'можжевельник', 'кипарис',
        'табак', 'кожа', 'дым', 'смола', 'ладан', 'мирра',
        'фрукт', 'ягода', 'яблоко', 'груша', 'персик', 'абрикос',
        'клубника', 'малина', 'черника', 'вишня', 'слива',
        'кокос', 'банан', 'ананас', 'манго', 'папайя',
        'чай', 'кофе', 'шоколад', 'карамель', 'мед', 'сахар',
        'молоко', 'сливки', 'масло', 'сыр', 'хлеб', 'печенье',
        'океан', 'море', 'дождь', 'снег', 'лед', 'ветер',
        'земля', 'песок', 'камень', 'металл', 'стекло'
    ]
    
    text_lower = text.lower()
    return any(keyword in text_lower for keyword in note_keywords)

# --- Webhook для сообщений ---
@app.post("/webhook")
async def telegram_webhook_impl(request: Request):
    try:
        data = await request.json()
        logger.info(f"Received webhook: {data}")
        
        # Обработка обычного сообщения
        if "message" in data:
            message = data["message"]
            chat_id = message["chat"]["id"]
            user_id = message["from"]["id"]
            
            # Команды
            if "text" in message:
                text = message["text"]
                
                if text == "/start" or text == "/menu":
                    greeting = greet()
                    await telegram_send_message(chat_id, greeting["text"], greeting["reply_markup"])
                    return {"ok": True}
                
                # Получаем состояние пользователя
                state = get_user_state(user_id)
                
                # AI режим
                if state == "awaiting_ai_question":
                    # Проверяем лимит запросов
                    if not check_request_limit(user_id):
                        limit_message = (
                            "🚫 Достигнут дневной лимит запросов (100 в сутки).\n\n"
                            "Попробуйте завтра или используйте другие функции бота! 🐾"
                        )
                        await telegram_send_message(chat_id, limit_message)
                        return {"ok": True}
                    
                    logger.info(f"[AI] Processing question from {user_id}: {text}")
                    
                    # Отправляем сообщение о начале обработки
                    await telegram_send_message(chat_id, "🐾 Обрабатываю ваш запрос...")
                    
                    # Получаем ответ от ChatGPT
                    ai_answer = await ask_chatgpt(text)
                    logger.info(f"✅ ОТВЕТ ОТ CHATGPT ПОЛУЧЕН:")
                    logger.info(f"- Длина ответа: {len(ai_answer)} символов")
                    logger.info(f"- Первые 200 символов: '{ai_answer[:200]}'")
                    
                    # Очищаем ответ от markdown
                    ai_answer_clean = ai_answer.replace("**", "").replace("*", "").replace("__", "").replace("_", "")
                    
                    # Создаем кнопки возврата
                    buttons = {
                        "inline_keyboard": [
                            [{"text": "🔄 Задать ещё вопрос", "callback_data": "ai_mode"}],
                            [{"text": "🏠 Главное меню", "callback_data": "main_menu"}]
                        ]
                    }
                    
                    # Отправляем ответ
                    await send_long_message(chat_id, ai_answer_clean, buttons if buttons else None)
                    logger.info(f"[TG] Sent ai_answer to {chat_id}")
                    
                    # Сбрасываем состояние
                    set_user_state(user_id, None)
                    return {"ok": True}
                
                # Режим поиска нот
                elif state == "awaiting_note_search":
                    # Проверяем лимит запросов
                    if not check_request_limit(user_id):
                        limit_message = (
                            "🚫 Достигнут дневной лимит запросов (100 в сутки).\n\n"
                            "Попробуйте завтра или используйте другие функции бота! 🐾"
                        )
                        await telegram_send_message(chat_id, limit_message)
                        return {"ok": True}
                    
                    logger.info(f"[NOTE] Searching for note: {text}")
                    
                    # Отправляем сообщение о начале поиска
                    await telegram_send_message(chat_id, "🔍 Ищу ароматы с этой нотой...")
                    
                    # Ищем через API
                    search_result = await search_note_api(text)
                    
                    if search_result.get("status") == "success" and search_result.get("fragrances"):
                        fragrances = search_result["fragrances"]
                        
                        response_text = f"🍓 Найдено ароматов с нотой '{text}': {len(fragrances)}\n\n"
                        
                        for i, fragrance in enumerate(fragrances[:10], 1):  # Показываем первые 10
                            name = fragrance.get("name", "Неизвестно")
                            brand = fragrance.get("brand", "")
                            link = fragrance.get("link", "")
                            
                            response_text += f"{i}. {brand} {name}\n"
                            if link:
                                response_text += f"🔗 <a href='{link}'>Подробнее</a>\n"
                            response_text += "\n"
                        
                        if len(fragrances) > 10:
                            response_text += f"... и ещё {len(fragrances) - 10} ароматов\n"
                        
                    else:
                        response_text = f"😔 К сожалению, не найдено ароматов с нотой '{text}'"
                    
                    # Создаем кнопки возврата
                    buttons = {
                        "inline_keyboard": [
                            [{"text": "🔄 Искать другую ноту", "callback_data": "note_mode"}],
                            [{"text": "🏠 Главное меню", "callback_data": "main_menu"}]
                        ]
                    }
                    
                    await telegram_send_message(chat_id, response_text, buttons)
                    logger.info(f"[TG] Sent note_search_result to {chat_id}")
                    
                    # Сбрасываем состояние
                    set_user_state(user_id, None)
                    return {"ok": True}
                
                # Автоматическое определение запроса ноты
                elif is_likely_note(text):
                    # Проверяем лимит запросов
                    if not check_request_limit(user_id):
                        limit_message = (
                            "🚫 Достигнут дневной лимит запросов (100 в сутки).\n\n"
                            "Попробуйте завтра или используйте другие функции бота! 🐾"
                        )
                        await telegram_send_message(chat_id, limit_message)
                        return {"ok": True}
                    
                    logger.info(f"[AUTO-NOTE] Auto-detected note query: {text}")
                    
                    # Отправляем сообщение о начале поиска
                    await telegram_send_message(chat_id, "🔍 Похоже, вы ищете ноту! Ищу ароматы...")
                    
                    # Ищем через API
                    search_result = await search_note_api(text)
                    
                    if search_result.get("status") == "success" and search_result.get("fragrances"):
                        fragrances = search_result["fragrances"]
                        
                        response_text = f"🍓 Найдено ароматов с нотой '{text}': {len(fragrances)}\n\n"
                        
                        for i, fragrance in enumerate(fragrances[:10], 1):
                            name = fragrance.get("name", "Неизвестно")
                            brand = fragrance.get("brand", "")
                            link = fragrance.get("link", "")
                            
                            response_text += f"{i}. {brand} {name}\n"
                            if link:
                                response_text += f"🔗 <a href='{link}'>Подробнее</a>\n"
                            response_text += "\n"
                        
                        if len(fragrances) > 10:
                            response_text += f"... и ещё {len(fragrances) - 10} ароматов\n"
                        
                    else:
                        response_text = f"😔 К сожалению, не найдено ароматов с нотой '{text}'"
                    
                    # Создаем кнопки возврата
                    buttons = {
                        "inline_keyboard": [
                            [{"text": "🔄 Искать другую ноту", "callback_data": "note_mode"}],
                            [{"text": "🏠 Главное меню", "callback_data": "main_menu"}]
                        ]
                    }
                    
                    await telegram_send_message(chat_id, response_text, buttons)
                    logger.info(f"[TG] Sent auto_note_result to {chat_id}")
                    return {"ok": True}
                
                # Если нет активного состояния, показываем меню
                else:
                    greeting = greet()
                    await telegram_send_message(chat_id, greeting["text"], greeting["reply_markup"])
                    return {"ok": True}
        
        # Обработка callback запросов
        elif "callback_query" in data:
            callback_query = data["callback_query"]
            callback_data = callback_query["data"]
            chat_id = callback_query["message"]["chat"]["id"]
            message_id = callback_query["message"]["message_id"]
            user_id = callback_query["from"]["id"]
            
            # Отвечаем на callback
            await telegram_answer_callback_query(callback_query["id"])
            
            if callback_data == "main_menu":
                greeting = greet()
                await telegram_edit_message(chat_id, message_id, greeting["text"], greeting["reply_markup"])
                set_user_state(user_id, None)
                
            elif callback_data == "ai_mode":
                ai_text = (
                    "🐾✨ Я AI-Пантера — ваш умный помощник по ароматам! 🌟\n\n"
                    "Спрашивай про любые духи, масла, доставку или цены — я найду всё в нашем каталоге! 🌟\n\n"
                    "📊 Лимит: 100 запросов в сутки"
                )
                buttons = {
                    "inline_keyboard": [
                        [{"text": "🏠 Главное меню", "callback_data": "main_menu"}]
                    ]
                }
                await telegram_edit_message(chat_id, message_id, ai_text, buttons)
                set_user_state(user_id, "awaiting_ai_question")
                
            elif callback_data == "note_mode":
                note_text = (
                    "🐾✨ Я знаю все ароматы по нотам! 🍓\n\n"
                    "🍉 Напиши любую ноту (например, апельсин, клубника) — я найду ароматы с этой нотой!\n\n"
                    "📊 Лимит: 100 запросов в сутки"
                )
                buttons = {
                    "inline_keyboard": [
                        [{"text": "🏠 Главное меню", "callback_data": "main_menu"}]
                    ]
                }
                await telegram_edit_message(chat_id, message_id, note_text, buttons)
                set_user_state(user_id, "awaiting_note_search")
        
        logger.info("=== WEBHOOK COMPLETED SUCCESSFULLY ===")
        return {"ok": True}
        
    except Exception as e:
        logger.error(f"Webhook error: {e}\n{traceback.format_exc()}")
        return {"error": str(e)}

# --- Startup event ---
@app.on_event("startup")
async def startup_event():
    logger.info("=== BOT STARTUP ===")
    logger.info(f"TOKEN: {'✅ Set' if TOKEN else '❌ Missing'}")
    logger.info(f"WEBHOOK_BASE_URL: {'✅ Set' if WEBHOOK_BASE_URL else '❌ Missing'}")
    logger.info(f"OPENAI_API: {'✅ Set' if OPENAI_API else '❌ Missing'}")
    logger.info(f"PORT: {PORT}")
    
    # Запускаем планировщик еженедельных сообщений
    schedule_weekly_messages()
    
    logger.info("=== STARTUP EVENT COMPLETE ===")

# --- Запуск приложения ---
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT)