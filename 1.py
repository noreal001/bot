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
DB_PATH = "aromas.db"
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
            state = user_states.get(user_id)
            logger.info(f"[TG] user_id: {user_id}, text: {text}, state: {state}")
            
            try:
                if text == "/start":
                    welcome = (
                        '<b>Здравствуйте!\n\n'
                        'Я — ваш ароматный помощник от BAHUR.\n'
                        '🍓 Ищу ноты и 🧸 отвечаю на вопросы с любовью. ❤</b>'
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
                    return {"ok": True}
                if state == 'awaiting_ai_question':
                    logger.info(f"[TG] Processing AI question for user {user_id}")
                    ai_answer = await ask_deepseek(text)
                    ai_answer = ai_answer.replace('*', '')
                    success = await telegram_send_message(chat_id, ai_answer)
                    if success:
                        logger.info(f"[TG] Sent ai_answer to {chat_id}")
                    else:
                        logger.error(f"[TG] Failed to send ai_answer to {chat_id}")
                    return {"ok": True}
                if state == 'awaiting_note_search':
                    logger.info(f"[TG] Processing note search for user {user_id}")
                    result = await search_note_api(text)
                    if result.get("status") == "success":
                        msg = f'✨ {result.get("brand")} {result.get("aroma")}\n\n{result.get("description")}'
                        success = await telegram_send_message(chat_id, msg)
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
                    return {"ok": True}
                # Если нет состояния, предлагаем выбрать режим
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
            logger.info(f"[TG] Callback: {data} from {user_id}")
            
            try:
                if data == "instruction":
                    user_states[user_id] = 'awaiting_note_search'
                    success = await telegram_send_message(chat_id, '🍉 Напиши любую ноту (например, апельсин, клубника) — я найду ароматы с этой нотой!')
                    if success:
                        logger.info(f"[TG] Set state awaiting_note_search for {user_id}")
                    else:
                        logger.error(f"[TG] Failed to send instruction message to {chat_id}")
                    return {"ok": True}
                elif data == "ai":
                    user_states[user_id] = 'awaiting_ai_question'
                    success = await telegram_send_message(chat_id, greet())
                    if success:
                        logger.info(f"[TG] Set state awaiting_ai_question for {user_id}")
                    else:
                        logger.error(f"[TG] Failed to send ai greeting to {chat_id}")
                    return {"ok": True}
                elif data.startswith("repeatapi_"):
                    aroma_id = data.split('_', 1)[1]
                    url = f"https://api.alexander-dev.ru/bahur/search/?id={aroma_id}"
                    async with aiohttp.ClientSession() as session:
                        async with session.get(url, timeout=10) as response:
                            response.raise_for_status()
                            result = await response.json()
                    if result.get("status") == "success":
                        msg = f'✨ {result.get("brand")} {result.get("aroma")}\n\n{result.get("description")}'
                        success = await telegram_send_message(chat_id, msg)
                        if success:
                            logger.info(f"[TG] Sent repeatapi result to {chat_id}")
                        else:
                            logger.error(f"[TG] Failed to send repeatapi result to {chat_id}")
                    else:
                        success = await telegram_send_message(chat_id, "Ничего не найдено по этой ноте 😢")
                        if success:
                            logger.info(f"[TG] Sent repeatapi not found to {chat_id}")
                        else:
                            logger.error(f"[TG] Failed to send repeatapi not found to {chat_id}")
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
    state = user_states.get(user_id)
    logger.info(f"[SUPERLOG] user_id: {user_id}, text: {text}, state: {state}")
    try:
        if state == 'awaiting_ai_question':
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
            user_states[user_id] = 'awaiting_note_search'
            return JSONResponse({"text": '🍉 Напиши любую ноту (например, апельсин, клубника) — я найду ароматы с этой нотой!'} )
        elif data == 'ai':
            user_states[user_id] = 'awaiting_ai_question'
            result = greet()
            return JSONResponse({"text": result})
        elif data.startswith('repeatapi_'):
            aroma_id = data.split('_', 1)[1]
            url = f"https://api.alexander-dev.ru/bahur/search/?id={aroma_id}"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=10) as response:
                    response.raise_for_status()
                    result = await response.json()
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