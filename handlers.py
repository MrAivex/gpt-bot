import time
import asyncio
from aiohttp import web
from logger_config import logger
from workers import worker_manager
from config import WEBHOOK_PATH
from database import db # Импортируем базу для очистки

class WebhookHandler:
    def __init__(self, bot):
        self.bot = bot

    async def handle_max_webhook(self, request):
        try:
            data = await request.json()
            if data.get('update_type') != 'message_created':
                return web.Response(status=200)

            message_data = data.get('message', {})
            user_id = message_data.get('sender', {}).get('user_id')
            chat_id = message_data.get('recipient', {}).get('chat_id')
            
            # Извлекаем текст и вложения
            body = message_data.get('body', {})
            text = body.get('text', '')

            button_payload = body.get('attachments', {}).get('payload', '')
            logger.info(button_payload)

            attachments = message_data.get('attachments') or body.get('attachments') or []

            # Бот должен реагировать, если есть либо текст, либо картинка
            if not all([user_id, chat_id]):
                return web.Response(status=200)
            
            raw_command = (text or button_payload or "").strip().lower()

            if raw_command:
                # Команда /START
                if raw_command == "/start":
                    logger.info(f"Команда /start от {user_id}")
                    await db.register_user(user_id) # Метод должен быть в database.py
                    
                    welcome_text = (
                        "👋 Привет! Я твой ИИ-ассистент.\n\n"
                        "Я помогу тебе с кодом на C++/Python или задачами из Бауманки 🛠\n\n"
                        "Команды:\n"
                        "/help — показать меню\n"
                        "/clear — очистить историю."
                    )
                    await self.bot.send_message(chat_id=chat_id, text=welcome_text)
                    return web.Response(status=200)
            
            if text:
                cmd = text.strip().lower()
                
                if cmd == "/start":
                    logger.info(f"Команда /start от {user_id}")
                    
                    # 1. Регистрируем пользователя в базе
                    await db.register_user(user_id)
                    
                    # 2. Отправляем приветствие
                    welcome_text = (
                        "👋 Привет! Я твой ИИ-ассистент.\n\n"
                        "Я помогу тебе с кодом на C++/Python, задачами"
                        "или просто поддержу беседу. Можешь даже прислать мне фото!\n\n"
                        "Команды:\n"
                        "/clear — очистить историю нашей переписки."
                    )
                    
                    await self.bot.send_message(chat_id=chat_id, text=welcome_text)
                    return web.Response(status=200)
                
                if cmd == "/clear":
                    await db.delete_user_history(user_id)
                    await self.bot.send_message(chat_id=chat_id, text="🧹 Память очищена!")
                    return web.Response(status=200)
                
                if cmd == "/help":
                    logger.info(f"Команда /help от {user_id}")
                    
                    help_text = "📖 *Доступные команды:*\n\n" \
                                "/start — Регистрация и начало работы\n" \
                                "/help — Показать это меню\n" \
                                "/clear — Очистить контекст нашей беседы"
                    
                    # Строго по формату API MAX
                    reply_markup = [
                        {
                            "type": "inline_keyboard",
                            "payload": {
                                "buttons": [
                                    [
                                        {
                                            "type": "callback",
                                            "text": "🚀 Старт",
                                            "payload": "/start"
                                        },
                                        {
                                            "type": "callback",
                                            "text": "🧹 Очистить историю",
                                            "payload": "/clear"
                                        }
                                    ]
                                ]
                            }
                        }
                    ]
                    
                    await self.bot.send_message(
                        chat_id=chat_id, 
                        text=help_text, 
                        reply_markup=reply_markup
                    )
                    return web.Response(status=200)

            msg_timestamp = data.get('timestamp', 0) / 1000 
            if time.time() - msg_timestamp > 60:
                return web.Response(status=200)

            # ВАЖНО: Передаем attachments пятым аргументом
            asyncio.create_task(
                worker_manager.process_message(self.bot, chat_id, user_id, text, attachments)
            )

            return web.Response(status=200)
        except Exception as e:
            logger.error(f"Ошибка в обработчике вебхука: {e}")
            return web.Response(status=200)

def setup_handlers(app, bot):
    handler = WebhookHandler(bot)
    app.router.add_post(WEBHOOK_PATH, handler.handle_max_webhook)