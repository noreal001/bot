import logging
import sqlite3
import re
import requests
import nest_asyncio
import random
import os
import traceback
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import PlainTextResponse, JSONResponse
from pydantic import BaseModel
import aiohttp
import asyncio
import httpx
import sys
import uvicorn

print('=== [LOG] 1.py импортирован ===')
nest_asyncio.apply()

# --- Конфигурация ---
TOKEN = os.getenv('TOKEN')
BASE_WEBHOOK_URL = os.getenv('WEBHOOK_BASE_URL')
WEBHOOK_PATH = "/webhook/ai-bear-123456"
DEEPSEEK_API = os.getenv('DEEPSEEK')

# --- FastAPI app ---
print('=== [LOG] FastAPI app создаётся ===')
app = FastAPI()
print('=== [LOG] FastAPI app создан ===')

# Глобальный обработчик исключений
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Global exception handler: {exc}\n{traceback.format_exc()}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )

print(f'=== [LOG] WEBHOOK_PATH: {WEBHOOK_PATH} ===')

@app.on_event("startup")
async def log_routes():
    logger.info("=== ROUTES REGISTERED ===")
    for route in app.routes:
        logger.info(f"{route.path} [{','.join(route.methods or [])}]")
    logger.info(f"WEBHOOK_PATH: {WEBHOOK_PATH}")
    logger.info("=========================")

# --- DeepSeek и данные Bahur ---
def load_bahur_data():
    with open("bahur_data.txt", "r", encoding="utf-8") as f:
        return f.read()

BAHUR_DATA = load_bahur_data()

# --- Логирование ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
def greet():
    return random.choice([
    "Привет! 🐻✨ Я Ai-Медвежонок — эксперт по ароматам BAHUR! Спрашивай про любые духи, масла, доставку или цены — я найду всё в нашем каталоге! 🌟",
    "Здравствуй! 🧸💫 Готов помочь с выбором ароматов! Хочешь узнать про конкретные духи, масла, доставку или цены? Спрашивай — у меня есть полный каталог! ✨",
    "Привет, ароматный друг! 🐻‍❄️✨ Я знаю всё о духах BAHUR! Спрашивай про любые ароматы, масла, доставку — найду в каталоге и расскажу подробно! 🌟",
    "Добро пожаловать! 🎯🐻 Я эксперт по ароматам BAHUR! Хочешь узнать про конкретные духи, масла, цены или доставку? Спрашивай — у меня есть все данные! ✨",
    "Привет! 🌟🧸 Я Ai-Медвежонок — знаю всё о духах BAHUR! Спрашивай про любые ароматы, масла, доставку или цены — найду в каталоге и помогу с выбором! 💫"
    ])

async def ask_deepseek(question):
    try:
        url = "https://api.deepseek.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {DEEPSEEK_API}",
            "Content-Type": "application/json"
        }
        data = {
            "model": "deepseek-chat",
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Ты - Ai-Медвежонок (менеджер по продажам), эксперт по ароматам BAHUR. Используй ТОЛЬКО эти данные для ответа клиенту:\n"
                        f"{BAHUR_DATA}\n"
                        "ПРАВИЛА ОТВЕТОВ:\n"
                        "1. Отвечай КОНКРЕТНО на вопрос клиента, используя данные из каталога\n"
                        "2. Если клиент спрашивает про аромат - найди его в данных и опиши подробно\n"
                        "3. Если клиент спрашивает про доставку/оплату - дай конкретную информацию\n"
                        "4. Если есть подходящая ссылка из данных, обязательно включи её в ответ\n"
                        "5. НЕ давай общих ответов типа 'пиши текстом' или 'нажми кнопку ноты'\n"
                        "6. Отвечай на русском языке, с эмодзи, но БЕЗ markdown\n"
                        "7. Если вопрос не по теме ароматов - аккуратно переведи в шутку и предложи конкретный аромат\n"
                        "8. Когда вставляешь ссылку, используй HTML-формат: <a href='ССЫЛКА'>ТЕКСТ</a>\n"
                        "9. НЕ предлагай 'нажать кнопку ноты' - вместо этого найди аромат в данных\n"
                        "10. Если не можешь найти аромат в данных - предложи конкретные варианты из каталога\n"
                        "ВАЖНО: Если в ответе есть ссылки, используй формат <a href='ССЫЛКА'>ТЕКСТ</a> - они будут автоматически преобразованы в кнопки"
                    )
                },
                {
                    "role": "user",
                    "content": f"{question}"
                }
            ],
            "temperature": 0.5
        }
        
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, headers=headers, json=data) as resp:
                if resp.status != 200:
                    logger.error(f"DeepSeek API error: {resp.status} - {await resp.text()}")
                    return "Извините, произошла ошибка при обработке вашего запроса. Попробуйте еще раз."
                
                result = await resp.json()
                if "choices" not in result or not result["choices"]:
                    logger.error(f"DeepSeek API unexpected response: {result}")
                    return "Извините, произошла ошибка при обработке вашего запроса. Попробуйте еще раз."
                
                return result["choices"][0]["message"]["content"].strip()
                
    except asyncio.TimeoutError:
        logger.error("DeepSeek API timeout")
        return "Извините, запрос занял слишком много времени. Попробуйте еще раз."
    except aiohttp.ClientError as e:
        logger.error(f"DeepSeek API client error: {e}")
        return "Извините, произошла ошибка сети. Попробуйте еще раз."
    except Exception as e:
        logger.error(f"DeepSeek API unexpected error: {e}\n{traceback.format_exc()}")
        return "Извините, произошла неожиданная ошибка. Попробуйте еще раз."

async def search_note_api(note):
    try:
        url = f"https://api.alexander-dev.ru/bahur/search/?text={note}"
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    logger.error(f"Search API error: {resp.status} - {await resp.text()}")
                    return {"status": "error", "message": "Ошибка API"}
                
                result = await resp.json()
                return result
                
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

# --- Поиск по ID аромата ---
async def search_by_id_api(aroma_id):
    try:
        url = f"https://api.alexander-dev.ru/bahur/search/?id={aroma_id}"
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    logger.error(f"Search by ID API error: {resp.status} - {await resp.text()}")
                    return {"status": "error", "message": "Ошибка API"}
                
                result = await resp.json()
                return result
                
    except asyncio.TimeoutError:
        logger.error("Search by ID API timeout")
        return {"status": "error", "message": "Таймаут запроса"}
    except aiohttp.ClientError as e:
        logger.error(f"Search by ID API client error: {e}")
        return {"status": "error", "message": "Ошибка сети"}
    except Exception as e:
        logger.error(f"Search by ID API unexpected error: {e}\n{traceback.format_exc()}")
        return {"status": "error", "message": "Неожиданная ошибка"}

# --- Обработка голосовых сообщений ---
async def recognize_voice_content(file_content):
    """Распознаёт речь из байтового содержимого ogg-файла. Возвращает текст или строку-ошибку."""
    try:
        import speech_recognition as sr
        from pydub import AudioSegment
        import tempfile
        recognizer = sr.Recognizer()
        with tempfile.NamedTemporaryFile(suffix='.ogg') as temp_ogg, tempfile.NamedTemporaryFile(suffix='.wav') as temp_wav:
            temp_ogg.write(file_content)
            temp_ogg.flush()
            try:
                audio = AudioSegment.from_file(temp_ogg.name)
                audio.export(temp_wav.name, format='wav')
                temp_wav.flush()
            except Exception as audio_error:
                logger.error(f"Audio conversion error: {audio_error}")
                return "Ошибка при обработке аудио файла. Попробуйте еще раз или напишите текст."
            try:
                with sr.AudioFile(temp_wav.name) as source:
                    audio_data = recognizer.record(source)
                text_content = recognizer.recognize_google(audio_data, language='ru-RU')
                logger.info(f"Voice recognized: '{text_content}'")
                return text_content
            except sr.UnknownValueError:
                logger.error("Speech recognition could not understand audio")
                return "Не удалось разобрать речь. Попробуйте говорить четче или напишите текст."
            except sr.RequestError as e:
                logger.error(f"Speech recognition service error: {e}")
                return "Ошибка сервиса распознавания речи. Попробуйте еще раз или напишите текст."
    except Exception as e:
        logger.error(f"Speech recognition error: {e}\n{traceback.format_exc()}")
        return "Ошибка при обработке голосового сообщения."

async def process_voice_message(voice, chat_id):
    try:
        # Получаем информацию о файле
        file_id = voice["file_id"]
        file_unique_id = voice["file_unique_id"]
        duration = voice.get("duration", 0)
        
        # Получаем файл
        file_url = f"https://api.telegram.org/bot{TOKEN}/getFile?file_id={file_id}"
        async with httpx.AsyncClient() as client:
            resp = await client.get(file_url)
            if resp.status_code != 200:
                logger.error(f"Failed to get file info: {resp.status_code}")
                return None
            
            file_info = resp.json()
            if not file_info.get("ok"):
                logger.error(f"File info error: {file_info}")
                return None
            
            file_path = file_info["result"]["file_path"]
            file_url = f"https://api.telegram.org/file/bot{TOKEN}/{file_path}"
            
            # Скачиваем файл
            async with client.stream("GET", file_url) as response:
                if response.status_code != 200:
                    logger.error(f"Failed to download file: {response.status_code}")
                    return None
                
                # Читаем содержимое файла
                file_content = await response.aread()
                
                # Распознаем речь с использованием tempfile
                text_content = await recognize_voice_content(file_content)
                # Если результат не ошибка, отправляем в дипсик
                if text_content and not any(err in text_content for err in ["Ошибка", "Не удалось", "недоступно"]):
                    ai_answer = await ask_deepseek(text_content)
                    return ai_answer
                else:
                    return text_content
                
    except Exception as e:
        logger.error(f"Voice processing error: {e}\n{traceback.format_exc()}")
        return "Ошибка при обработке голосового сообщения."

# --- Альтернативная обработка голосовых сообщений (без aifc) ---
async def process_voice_message_alternative(voice, chat_id):
    """Альтернативная обработка голосовых сообщений без aifc"""
    try:
        # Получаем информацию о файле
        file_id = voice["file_id"]
        file_unique_id = voice["file_unique_id"]
        duration = voice.get("duration", 0)
        
        # Если голосовое сообщение слишком короткое
        if duration < 1:
            return "Голосовое сообщение слишком короткое. Попробуйте записать более длинное сообщение."
        
        # Получаем файл
        file_url = f"https://api.telegram.org/bot{TOKEN}/getFile?file_id={file_id}"
        async with httpx.AsyncClient() as client:
            resp = await client.get(file_url)
            if resp.status_code != 200:
                logger.error(f"Failed to get file info: {resp.status_code}")
                return None
            
            file_info = resp.json()
            if not file_info.get("ok"):
                logger.error(f"File info error: {file_info}")
                return None
            
            file_path = file_info["result"]["file_path"]
            file_url = f"https://api.telegram.org/file/bot{TOKEN}/{file_path}"
            
            # Скачиваем файл
            async with client.stream("GET", file_url) as response:
                if response.status_code != 200:
                    logger.error(f"Failed to download file: {response.status_code}")
                    return None
                
                # Читаем содержимое файла
                file_content = await response.aread()
                
                # Пытаемся распознать речь без aifc
                text_content = await recognize_voice_content(file_content)
                if text_content and not any(err in text_content for err in ["Ошибка", "Не удалось", "недоступно"]):
                    ai_answer = await ask_deepseek(text_content)
                    return ai_answer
                else:
                    return text_content
                
    except Exception as e:
        logger.error(f"Alternative voice processing error: {e}\n{traceback.format_exc()}")
        return "Ошибка при обработке голосового сообщения."

# --- Упрощенная обработка голосовых сообщений (без распознавания) ---
async def process_voice_message_simple(voice, chat_id):
    """Упрощенная обработка голосовых сообщений без сложных зависимостей"""
    try:
        # Получаем информацию о файле
        file_id = voice["file_id"]
        duration = voice.get("duration", 0)
        
        # Если голосовое сообщение слишком короткое
        if duration < 1:
            return "Голосовое сообщение слишком короткое. Попробуйте записать более длинное сообщение."
        
        # Получаем файл
        file_url = f"https://api.telegram.org/bot{TOKEN}/getFile?file_id={file_id}"
        async with httpx.AsyncClient() as client:
            resp = await client.get(file_url)
            if resp.status_code != 200:
                logger.error(f"Failed to get file info: {resp.status_code}")
                return None
            
            file_info = resp.json()
            if not file_info.get("ok"):
                logger.error(f"File info error: {file_info}")
                return None
            
            # Просто возвращаем информацию о голосовом сообщении
            return f"Получено голосовое сообщение длительностью {duration} секунд. Для распознавания речи напишите ваш вопрос текстом."
                
    except Exception as e:
        logger.error(f"Simple voice processing error: {e}\n{traceback.format_exc()}")
        return "Ошибка при обработке голосового сообщения."

# --- Функция "печатает" ---
async def send_typing_action(chat_id):
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/sendChatAction"
        payload = {
            "chat_id": chat_id,
            "action": "typing"
        }
        timeout = httpx.Timeout(5.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code != 200:
                logger.error(f"Failed to send typing action: {resp.status_code} - {resp.text}")
    except Exception as e:
        logger.error(f"Failed to send typing action: {e}")

# --- Умное распознавание нот ---
def is_likely_note(text):
    """Определяет, похож ли текст на название ноты"""
    if not text:
        return False
    
    # Список популярных нот
    common_notes = [
        'ваниль', 'лаванда', 'роза', 'жасмин', 'сандал', 'мускус', 'амбра', 'пачули',
        'бергамот', 'лимон', 'апельсин', 'мандарин', 'грейпфрут', 'лайм',
        'клубника', 'малина', 'черника', 'вишня', 'персик', 'абрикос', 'яблоко',
        'груша', 'ананас', 'манго', 'банан', 'кокос', 'карамель', 'шоколад',
        'кофе', 'чай', 'мята', 'базилик', 'розмарин', 'тимьян', 'орегано',
        'корица', 'кардамон', 'имбирь', 'куркума', 'перец', 'гвоздика',
        'кедр', 'сосна', 'ель', 'дуб', 'береза', 'иланг-иланг', 'нероли',
        'ирис', 'фиалка', 'ландыш', 'сирень', 'жасмин', 'гардения',
        'морская соль', 'морской бриз', 'дождь', 'снег', 'земля', 'мох',
        'дым', 'кожа', 'табак', 'виски', 'коньяк', 'ром', 'вино',
        'мед', 'сливки', 'молоко', 'йогурт', 'сыр', 'масло'
    ]
    
    text_lower = text.lower().strip()
    
    # Проверяем точное совпадение
    if text_lower in common_notes:
        return True
    
    # Проверяем частичное совпадение
    for note in common_notes:
        if note in text_lower or text_lower in note:
            return True
    
    # Проверяем по длине и характеру (короткие слова часто бывают нотами)
    if len(text_lower) <= 15 and not any(char.isdigit() for char in text_lower):
        # Если текст короткий и не содержит цифр, возможно это нота
        return True
    
    return False

# --- Обработка ссылок в тексте ---
import re

def extract_links_from_text(text):
    """Извлекает ссылки из HTML-текста и создает кнопки"""
    # Ищем ссылки в формате <a href='URL'>ТЕКСТ</a>
    link_pattern = r"<a\s+href=['\"]([^'\"]+)['\"][^>]*>([^<]+)</a>"
    links = re.findall(link_pattern, text)
    
    if not links:
        return None
    
    # Создаем кнопки для каждой ссылки
    buttons = []
    for url, button_text in links:
        # Делаем первую букву заглавной
        button_text_capitalized = button_text.strip().capitalize()
        buttons.append([{"text": button_text_capitalized, "url": url}])
    
    return {"inline_keyboard": buttons}

def remove_html_links(text):
    """Удаляет HTML-ссылки из текста, оставляя только текст"""
    # Удаляем ссылки в формате <a href='URL'>ТЕКСТ</a>, оставляя только ТЕКСТ
    link_pattern = r"<a\s+href=['\"][^'\"]+['\"][^>]*>([^<]+)</a>"
    return re.sub(link_pattern, r"\1", text)

# --- Telegram webhook endpoint ---
print('=== [LOG] Объявляю эндпоинт webhook... ===')
@app.post("/webhook/ai-bear-123456")
async def telegram_webhook(update: dict, request: Request):
    logger.info(f"=== WEBHOOK CALLED ===")
    logger.info(f"Request from: {request.client.host}")
    logger.info(f"Update type: {list(update.keys()) if update else 'None'}")
    
    try:
        result = await telegram_webhook_impl(update, request)
        logger.info(f"=== WEBHOOK COMPLETED SUCCESSFULLY ===")
        return result
    except Exception as e:
        logger.error(f"=== WEBHOOK FAILED: {e} ===")
        logger.error(traceback.format_exc())
        return {"ok": False, "error": str(e)}

# --- Переносим вашу логику webhook сюда ---
async def telegram_webhook_impl(update: dict, request: Request):
    print(f'[WEBHOOK] Called: {request.url} from {request.client.host}')
    print(f'[WEBHOOK] Body: {update}')
    logger.info(f"[WEBHOOK] Called: {request.url} from {request.client.host}")
    logger.info(f"[WEBHOOK] Body: {update}")
    try:
        if "message" in update:
            print('[WEBHOOK] message detected')
            message = update["message"]
            chat_id = message["chat"]["id"]
            user_id = message["from"]["id"]
            text = message.get("text", "").strip()
            voice = message.get("voice")
            state = get_user_state(user_id)
            logger.info(f"[TG] user_id: {user_id}, text: {text}, state: {state}")
            
            try:
                # Обработка голосовых сообщений
                if voice:
                    logger.info(f"[TG] Voice message received from {user_id}")
                    await send_typing_action(chat_id)
                    file_id = voice["file_id"]
                    file_unique_id = voice["file_unique_id"]
                    duration = voice.get("duration", 0)
                    file_url = f"https://api.telegram.org/bot{TOKEN}/getFile?file_id={file_id}"
                    async with httpx.AsyncClient() as client:
                        resp = await client.get(file_url)
                        if resp.status_code != 200:
                            logger.error(f"Failed to get file info: {resp.status_code}")
                            await telegram_send_message(chat_id, "Ошибка при получении голосового файла.")
                            return {"ok": True}
                        file_info = resp.json()
                        if not file_info.get("ok"):
                            logger.error(f"File info error: {file_info}")
                            await telegram_send_message(chat_id, "Ошибка при получении голосового файла.")
                            return {"ok": True}
                        file_path = file_info["result"]["file_path"]
                        file_url = f"https://api.telegram.org/file/bot{TOKEN}/{file_path}"
                        async with client.stream("GET", file_url) as response:
                            if response.status_code != 200:
                                logger.error(f"Failed to download file: {response.status_code}")
                                await telegram_send_message(chat_id, "Ошибка при скачивании голосового файла.")
                                return {"ok": True}
                            file_content = await response.aread()
                            text_content = await recognize_voice_content(file_content)
                            logger.info(f"[TG] Voice recognized text: {text_content}")
                            if text_content and not any(err in text_content for err in ["Ошибка", "Не удалось", "недоступно"]):
                                ai_answer = await ask_deepseek(text_content)
                                ai_answer = ai_answer.replace('*', '')
                                buttons = extract_links_from_text(ai_answer)
                                ai_answer_clean = remove_html_links(ai_answer)
                                success = await telegram_send_message(chat_id, ai_answer_clean, buttons if buttons else None)
                                if success:
                                    logger.info(f"[TG] Sent AI answer to voice message for {chat_id}")
                                else:
                                    logger.error(f"[TG] Failed to send AI answer to voice message for {chat_id}")
                            else:
                                await telegram_send_message(chat_id, text_content)
                    return {"ok": True}
                
                if text == "/start":
                    welcome = (
                        '<b>Здравствуйте!\n\n'
                        'Я — ваш ароматный помощник от BAHUR.\n'
                        '🍓 Ищу ноты и 🧸 отвечаю на вопросы с любовью. ❤\n\n'
                        '💡 <i>Используйте /menu для возврата в главное меню</i></b>'
                    )
                    main_menu = {
                        "inline_keyboard": [
                            [{"text": "🧸 Ai-Медвежонок", "callback_data": "ai"}],
                            [
                                {"text": "🍦 Прайс", "url": "https://drive.google.com/file/d/1J70LlZwh6g7JOryDG2br-weQrYfv6zTc/view?usp=sharing"},
                                {"text": "🍿 Магазин", "url": "https://www.bahur.store/m/"},
                                {"text": "♾️ Вопросы", "url": "https://vk.com/@bahur_store-optovye-praisy-ot-bahur"}
                            ],
                            [
                                {"text": "🎮 Чат", "url": "https://t.me/+VYDZEvbp1pce4KeT"},
                                {"text": "💎 Статьи", "url": "https://vk.com/bahur_store?w=app6326142_-133936126%2523w%253Dapp6326142_-133936126"},
                                {"text": "🏆 Отзывы", "url": "https://vk.com/@bahur_store"}
                            ],
                            [{"text": "🍓 Ноты", "callback_data": "instruction"}]
                        ]
                    }
                    success = await telegram_send_message(chat_id, welcome, main_menu)
                    if success:
                        logger.info(f"[TG] Sent welcome to {chat_id}")
                    else:
                        logger.error(f"[TG] Failed to send welcome to {chat_id}")
                    set_user_state(user_id, None)  # Сбрасываем состояние при /start
                    return {"ok": True}
                elif text == "/menu":
                    # Команда для выхода из режима AI и возврата в главное меню
                    welcome = (
                        '<b>Здравствуйте!\n\n'
                        'Я — ваш ароматный помощник от BAHUR.\n'
                        '🍓 Ищу ноты и 🧸 отвечаю на вопросы с любовью. ❤\n\n'
                        '💡 <i>Используйте /menu для возврата в главное меню</i></b>'
                    )
                    main_menu = {
                        "inline_keyboard": [
                            [{"text": "🧸 Ai-Медвежонок", "callback_data": "ai"}],
                            [
                                {"text": "🍦 Прайс", "url": "https://drive.google.com/file/d/1J70LlZwh6g7JOryDG2br-weQrYfv6zTc/view?usp=sharing"},
                                {"text": "🍿 Магазин", "url": "https://www.bahur.store/m/"},
                                {"text": "♾️ Вопросы", "url": "https://vk.com/@bahur_store-optovye-praisy-ot-bahur"}
                            ],
                            [
                                {"text": "🎮 Чат", "url": "https://t.me/+VYDZEvbp1pce4KeT"},
                                {"text": "💎 Статьи", "url": "https://vk.com/bahur_store?w=app6326142_-133936126%2523w%253Dapp6326142_-133936126"},
                                {"text": "🏆 Отзывы", "url": "https://vk.com/@bahur_store"}
                            ],
                            [{"text": "🍓 Ноты", "callback_data": "instruction"}]
                        ]
                    }
                    success = await telegram_send_message(chat_id, welcome, main_menu)
                    if success:
                        logger.info(f"[TG] Sent menu to {chat_id}")
                    else:
                        logger.error(f"[TG] Failed to send menu to {chat_id}")
                    set_user_state(user_id, None)  # Сбрасываем состояние
                    return {"ok": True}
                if state == 'awaiting_ai_question':
                    logger.info(f"[TG] Processing AI question for user {user_id}")
                    # Отправляем индикатор "печатает"
                    await send_typing_action(chat_id)
                    ai_answer = await ask_deepseek(text)
                    ai_answer = ai_answer.replace('*', '')
                    
                    # Извлекаем ссылки из ответа и создаем кнопки
                    buttons = extract_links_from_text(ai_answer)
                    ai_answer_clean = remove_html_links(ai_answer)
                    
                    success = await telegram_send_message(chat_id, ai_answer_clean, buttons if buttons else None)
                    if success:
                        logger.info(f"[TG] Sent ai_answer to {chat_id}")
                    else:
                        logger.error(f"[TG] Failed to send ai_answer to {chat_id}")
                    # НЕ сбрасываем состояние - остаемся в режиме AI
                    return {"ok": True}
                if state == 'awaiting_note_search':
                    logger.info(f"[TG] Processing note search for user {user_id}")
                    # Отправляем индикатор "печатает"
                    await send_typing_action(chat_id)
                    result = await search_note_api(text)
                    if result.get("status") == "success":
                        msg = f'✨ {result.get("brand")} {result.get("aroma")}\n\n{result.get("description")}'
                        # Добавляем кнопки "Подробнее" и "Повторить"
                        reply_markup = {
                            "inline_keyboard": [
                                [
                                    {"text": "🚀 Подробнее", "url": result.get("url", "")},
                                    {"text": "♾️ Повторить", "callback_data": f"repeatapi_{result.get('ID', '')}"}
                                ]
                            ]
                        }
                        success = await telegram_send_message(chat_id, msg, reply_markup)
                        if success:
                            logger.info(f"[TG] Sent note result to {chat_id}")
                        else:
                            logger.error(f"[TG] Failed to send note result to {chat_id}")
                    else:
                        success = await telegram_send_message(chat_id, "Ничего не найдено по этой ноте 😢")
                        if success:
                            logger.info(f"[TG] Sent not found to {chat_id}")
                        else:
                            logger.error(f"[TG] Failed to send not found to {chat_id}")
                    set_user_state(user_id, None)  # Сбрасываем состояние
                    return {"ok": True}
                # Если нет состояния, проверяем, похож ли текст на ноту
                if is_likely_note(text):
                    logger.info(f"[TG] Text '{text}' looks like a note, searching...")
                    # Отправляем индикатор "печатает"
                    await send_typing_action(chat_id)
                    result = await search_note_api(text)
                    if result.get("status") == "success":
                        msg = f'✨ {result.get("brand")} {result.get("aroma")}\n\n{result.get("description")}'
                        # Добавляем кнопки "Подробнее" и "Повторить"
                        reply_markup = {
                            "inline_keyboard": [
                                [
                                    {"text": "🚀 Подробнее", "url": result.get("url", "")},
                                    {"text": "♾️ Повторить", "callback_data": f"repeatapi_{result.get('ID', '')}"}
                                ]
                            ]
                        }
                        success = await telegram_send_message(chat_id, msg, reply_markup)
                        if success:
                            logger.info(f"[TG] Auto-found note result for {chat_id}")
                        else:
                            logger.error(f"[TG] Failed to send auto-found note result to {chat_id}")
                    else:
                        success = await telegram_send_message(chat_id, f"По запросу '{text}' ничего не найдено 😢\n\nПопробуйте другие ноты или выберите режим поиска.")
                        if success:
                            logger.info(f"[TG] Sent auto-search not found to {chat_id}")
                        else:
                            logger.error(f"[TG] Failed to send auto-search not found to {chat_id}")
                else:
                    # Если не похоже на ноту, предлагаем выбрать режим
                    menu = {
                        "inline_keyboard": [
                            [{"text": "🧸 Ai-Медвежонок", "callback_data": "ai"}],
                            [{"text": "🍓 Ноты", "callback_data": "instruction"}]
                        ]
                    }
                    success = await telegram_send_message(chat_id, "Выберите режим: 🧸 Ai-Медвежонок или 🍓 Ноты", reply_markup=menu)
                    if success:
                        logger.info(f"[TG] Sent menu to {chat_id}")
                    else:
                        logger.error(f"[TG] Failed to send menu to {chat_id}")
                set_user_state(user_id, None)  # Сбрасываем состояние
                return {"ok": True}
            except Exception as e:
                logger.error(f"[TG] Exception in message processing: {e}\n{traceback.format_exc()}")
                try:
                    await telegram_send_message(chat_id, "Произошла ошибка при обработке сообщения. Попробуйте еще раз.")
                except:
                    logger.error("Failed to send error message to user")
                return {"ok": False, "error": str(e)}
                
        elif "callback_query" in update:
            print('[WEBHOOK] callback_query detected')
            callback = update["callback_query"]
            data = callback["data"]
            chat_id = callback["message"]["chat"]["id"]
            user_id = callback["from"]["id"]
            message_id = callback["message"]["message_id"]
            callback_id = callback["id"]
            logger.info(f"[TG] Callback: {data} from {user_id}")
            
            try:
                if data == "instruction":
                    set_user_state(user_id, 'awaiting_note_search')
                    success = await telegram_edit_message(chat_id, message_id, '🍉 Напиши любую ноту (например, апельсин, клубника) — я найду ароматы с этой нотой!')
                    if success:
                        logger.info(f"[TG] Set state awaiting_note_search for {user_id}")
                    else:
                        logger.error(f"[TG] Failed to edit instruction message for {chat_id}")
                    await telegram_answer_callback_query(callback_id)
                    return {"ok": True}
                elif data == "ai":
                    set_user_state(user_id, 'awaiting_ai_question')
                    ai_greeting = greet()
                    
                    # Извлекаем ссылки из приветствия и создаем кнопки
                    buttons = extract_links_from_text(ai_greeting)
                    ai_greeting_clean = remove_html_links(ai_greeting)
                    
                    success = await telegram_edit_message(chat_id, message_id, ai_greeting_clean, buttons if buttons else None)
                    if success:
                        logger.info(f"[TG] Set state awaiting_ai_question for {user_id}")
                    else:
                        logger.error(f"[TG] Failed to edit ai greeting for {chat_id}")
                    await telegram_answer_callback_query(callback_id)
                    return {"ok": True}
                elif data.startswith("repeatapi_"):
                    aroma_id = data.split('_', 1)[1]
                    result = await search_by_id_api(aroma_id)
                    if result.get("status") == "success":
                        msg = f'✨ {result.get("brand")} {result.get("aroma")}\n\n{result.get("description")}'
                        # Добавляем кнопки обратно при повторном показе
                        reply_markup = {
                            "inline_keyboard": [
                                [
                                    {"text": "🚀 Подробнее", "url": result.get("url", "")},
                                    {"text": "♾️ Повторить", "callback_data": f"repeatapi_{result.get('ID', '')}"}
                                ]
                            ]
                        }
                        success = await telegram_edit_message(chat_id, message_id, msg, reply_markup)
                        if success:
                            logger.info(f"[TG] Edited repeatapi result for {chat_id}")
                        else:
                            logger.error(f"[TG] Failed to edit repeatapi result for {chat_id}")
                    else:
                        success = await telegram_edit_message(chat_id, message_id, "Ничего не найдено по этой ноте 😢")
                        if success:
                            logger.info(f"[TG] Edited repeatapi not found for {chat_id}")
                        else:
                            logger.error(f"[TG] Failed to edit repeatapi not found for {chat_id}")
                    await telegram_answer_callback_query(callback_id)
                    return {"ok": True}
                else:
                    success = await telegram_send_message(chat_id, "Callback обработан.")
                    if success:
                        logger.info(f"[TG] Sent generic callback to {chat_id}")
                    else:
                        logger.error(f"[TG] Failed to send generic callback to {chat_id}")
                    return {"ok": True}
            except Exception as e:
                logger.error(f"[TG] Exception in callback processing: {e}\n{traceback.format_exc()}")
                try:
                    await telegram_send_message(chat_id, "Произошла ошибка при обработке callback. Попробуйте еще раз.")
                except:
                    logger.error("Failed to send error message to user")
                return {"ok": False, "error": str(e)}
        else:
            print('[WEBHOOK] unknown update type')
            logger.warning("[TG] Unknown update type")
            return {"ok": False}
    except Exception as e:
        print(f'[WEBHOOK] Exception: {e}')
        logger.error(f"[TG] Exception in webhook: {e}\n{traceback.format_exc()}")
        # Не пытаемся отправлять сообщение пользователю здесь, так как у нас нет chat_id
        return {"ok": False, "error": str(e)}
print('=== [LOG] Эндпоинт webhook объявлен ===')

# --- Установка Telegram webhook ---
async def set_telegram_webhook(base_url: str):
    url = f"https://api.telegram.org/bot{TOKEN}/setWebhook"
    webhook_url = f"{base_url}{WEBHOOK_PATH}"
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, data={"url": webhook_url})
        logger.info(f"Set webhook response: {resp.text}")
        return resp.json()

# --- Эндпоинты FastAPI ---
@app.on_event("startup")
async def startup_event():
    logger.info("=== STARTUP EVENT ===")
    base_url = os.getenv("WEBHOOK_BASE_URL")
    if not base_url:
        logger.warning("WEBHOOK_BASE_URL не задан, webhook не будет установлен!")
        return
    try:
        result = await set_telegram_webhook(base_url)
        logger.info(f"Webhook set result: {result}")
    except Exception as e:
        logger.error(f"Failed to set webhook: {e}\n{traceback.format_exc()}")
    logger.info("=== STARTUP EVENT COMPLETE ===")

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("=== SHUTDOWN EVENT ===")
    logger.info("Application is shutting down gracefully...")
    logger.info("=== SHUTDOWN EVENT COMPLETE ===")

@app.get("/")
async def healthcheck():
    logger.info("Healthcheck requested")
    return PlainTextResponse("OK")

@app.post("/message")
async def handle_message(msg: MessageModel):
    user_id = msg.user_id
    text = msg.text.strip()
    state = get_user_state(user_id)
    logger.info(f"[SUPERLOG] user_id: {user_id}, text: {text}, state: {state}")
    try:
        if state == 'awaiting_ai_question':
            # Отправляем индикатор "печатает" (но здесь нет chat_id, поэтому пропускаем)
            ai_answer = await ask_deepseek(text)
            ai_answer = ai_answer.replace('*', '')
            return JSONResponse({"answer": ai_answer, "parse_mode": "HTML"})
        elif state == 'awaiting_note_search':
            result = await search_note_api(text)
            if result.get("status") == "success":
                return JSONResponse({
                    "brand": result.get("brand"),
                    "aroma": result.get("aroma"),
                    "description": result.get("description"),
                    "url": result.get("url"),
                    "aroma_id": result.get("ID")
                })
            else:
                return JSONResponse({"error": "Ничего не найдено по этой ноте 😢"})
        else:
            return JSONResponse({"info": "Нет активного режима для пользователя. Используйте /start или callback."})
    except Exception as e:
        logger.error(f"[SUPERLOG] Exception in handle_message: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/callback")
async def handle_callback(cb: CallbackModel):
    user_id = cb.user_id
    data = cb.data
    logger.info(f"[SUPERLOG] Callback data: {data}, user_id: {user_id}")
    try:
        if data != 'ai' and user_id in user_states:
            user_states.pop(user_id, None)
        if data == 'instruction':
            set_user_state(user_id, 'awaiting_note_search')
            return JSONResponse({"text": '🍉 Напиши любую ноту (например, апельсин, клубника) — я найду ароматы с этой нотой!'} )
        elif data == 'ai':
            set_user_state(user_id, 'awaiting_ai_question')
            result = greet()
            return JSONResponse({"text": result})
        elif data.startswith('repeatapi_'):
            aroma_id = data.split('_', 1)[1]
            result = await search_by_id_api(aroma_id)
            if result.get("status") == "success":
                return JSONResponse({
                    "brand": result.get("brand"),
                    "aroma": result.get("aroma"),
                    "description": result.get("description"),
                    "url": result.get("url"),
                    "aroma_id": result.get("ID")
                })
            else:
                return JSONResponse({"error": "Ничего не найдено по этой ноте 😢"})
        else:
            return JSONResponse({"info": "Callback обработан."})
    except Exception as e:
        logger.error(f"[SUPERLOG] Exception in handle_callback: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/start")
async def cmd_start(msg: MessageModel):
    logger.info(f"/start command from user {msg.user_id}")
    text = (
        '<b>Здравствуйте!\n\n'
        'Я — ваш ароматный помощник от BAHUR.\n'
        '🍓 Ищу ноты и 🧸 отвечаю на вопросы с любовью. ❤</b>'
    )
    return JSONResponse({"text": text, "parse_mode": "HTML"})

# --- Для запуска: uvicorn 1:app --reload ---
if __name__ == "__main__":
    import signal
    
    def signal_handler(signum, frame):
        logger.info("Received shutdown signal, gracefully shutting down...")
        sys.exit(0)
    
    # Регистрируем обработчики сигналов
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    port = int(os.environ.get("PORT", 8000))
    print(f"[INFO] Starting uvicorn on 0.0.0.0:{port}")
    uvicorn.run("1:app", host="0.0.0.0", port=port)