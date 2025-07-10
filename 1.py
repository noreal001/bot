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

nest_asyncio.apply()

# --- Конфигурация ---
TOKEN = os.getenv('TOKEN')
DB_PATH = "aromas.db"
BASE_WEBHOOK_URL = os.getenv('WEBHOOK_BASE_URL')
WEBHOOK_PATH = "/webhook/ai-bear-123456"
DEEPSEEK_API = os.getenv('DEEPSEEK')

# --- FastAPI app ---
app = FastAPI()

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
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=data, timeout=30) as resp:
            resp.raise_for_status()
            result = await resp.json()
            return result["choices"][0]["message"]["content"].strip()

async def search_note_api(note):
    url = f"https://api.alexander-dev.ru/bahur/search/?text={note}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=10) as resp:
            resp.raise_for_status()
            return await resp.json()

# --- Telegram sendMessage ---
async def telegram_send_message(chat_id, text, reply_markup=None, parse_mode="HTML"):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    async with httpx.AsyncClient() as client:
        await client.post(url, json=payload)

# --- Telegram webhook endpoint ---
@app.post(WEBHOOK_PATH)
async def telegram_webhook(update: dict):
    try:
        if "message" in update:
            message = update["message"]
            chat_id = message["chat"]["id"]
            user_id = message["from"]["id"]
            text = message.get("text", "").strip()
            state = user_states.get(user_id)
            logger.info(f"[TG] user_id: {user_id}, text: {text}, state: {state}")
            if text == "/start":
                welcome = (
                    '<b>Здравствуйте!\n\n'
                    'Я — ваш ароматный помощник от BAHUR.\n'
                    '🍓 Ищу ноты и 🧸 отвечаю на вопросы с любовью. ❤</b>'
                )
                await telegram_send_message(chat_id, welcome)
                return {"ok": True}
            if state == 'awaiting_ai_question':
                ai_answer = await ask_deepseek(text)
                ai_answer = ai_answer.replace('*', '')
                await telegram_send_message(chat_id, ai_answer)
                return {"ok": True}
            if state == 'awaiting_note_search':
                result = await search_note_api(text)
                if result.get("status") == "success":
                    msg = f'✨ {result.get("brand")} {result.get("aroma")}\n\n{result.get("description")}'
                    await telegram_send_message(chat_id, msg)
                else:
                    await telegram_send_message(chat_id, "Ничего не найдено по этой ноте 😢")
                return {"ok": True}
            # Если нет состояния, предлагаем выбрать режим
            menu = {
                "inline_keyboard": [
                    [{"text": "🧸 Ai-Медвежонок", "callback_data": "ai"}],
                    [{"text": "🍓 Ноты", "callback_data": "instruction"}]
                ]
            }
            await telegram_send_message(chat_id, "Выберите режим: 🧸 Ai-Медвежонок или 🍓 Ноты", reply_markup=menu)
            return {"ok": True}
        elif "callback_query" in update:
            callback = update["callback_query"]
            data = callback["data"]
            chat_id = callback["message"]["chat"]["id"]
            user_id = callback["from"]["id"]
            message_id = callback["message"]["message_id"]
            if data == "instruction":
                user_states[user_id] = 'awaiting_note_search'
                await telegram_send_message(chat_id, '🍉 Напиши любую ноту (например, апельсин, клубника) — я найду ароматы с этой нотой!')
                return {"ok": True}
            elif data == "ai":
                user_states[user_id] = 'awaiting_ai_question'
                await telegram_send_message(chat_id, greet())
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
                    await telegram_send_message(chat_id, msg)
                else:
                    await telegram_send_message(chat_id, "Ничего не найдено по этой ноте 😢")
                return {"ok": True}
            else:
                await telegram_send_message(chat_id, "Callback обработан.")
                return {"ok": True}
        else:
            logger.warning("[TG] Unknown update type")
            return {"ok": False}
    except Exception as e:
        logger.error(f"[TG] Exception in webhook: {e}\n{traceback.format_exc()}")
        return {"ok": False, "error": str(e)}

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
    base_url = os.getenv("WEBHOOK_BASE_URL")
    if not base_url:
        logger.warning("WEBHOOK_BASE_URL не задан, webhook не будет установлен!")
        return
    result = await set_telegram_webhook(base_url)
    logger.info(f"Webhook set result: {result}")

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