import asyncio
from collections import OrderedDict
from datetime import datetime, timedelta
from database import db
from ai_providers import get_ai_brain
from logger_config import logger
from config import ADMIN_ID
from config import ADMIN_ID, OPENAI_API_KEY # Импортируем ключ

# Реализация ограниченного словаря
class LimitedDict(OrderedDict):
    def __init__(self, limit=10000):
        self.limit = limit
        super().__init__()

    def __setitem__(self, key, value):
        # Если ключ уже есть, удаляем его, чтобы при вставке он стал "самым свежим"
        if key in self:
            del self[key]
        # Если лимит превышен, удаляем самый старый элемент (первый в очереди)
        if len(self) >= self.limit:
            self.popitem(last=False)
        super().__setitem__(key, value)

# Ограничиваем память 10 000 активных пользователей. 
# Этого за глаза хватит для VPS с небольшим объемом RAM.
user_cooldowns = LimitedDict(limit=10000)

brain = get_ai_brain("openai", api_key=OPENAI_API_KEY)

SYSTEM_PROMPT = {
    "role": "system", 
    "content": "Ты — полезный ИИ-ассистент в мессенджере MAX. Отвечай дружелюбно. Ты помнишь контекст предыдущих сообщений."
}

class ProcessManager:
    @staticmethod
    async def process_message(bot, chat_id, user_id, user_text, attachments=None):
        """
        Обновленный метод: принимает список вложений (attachments)
        """
        try:
            logger.info(f"--- ЗАПУСК ЛОГИКИ ДЛЯ {user_id} ---")

            # 1. Защита от спама (Cooldown)
            now = datetime.now()
            last_msg_time = user_cooldowns.get(user_id)

            if last_msg_time and (now - last_msg_time) < timedelta(seconds=3):
                logger.warning(f"Флуд от {user_id}. Запрос проигнорирован.")
                await bot.send_message(chat_id=chat_id, text="⚠️ Пожалуйста, подождите 3 секунды перед следующим сообщением.")
                return

            user_cooldowns[user_id] = now

            # 2. Лимиты из БД
            remaining_queries = await db.check_and_update_user(user_id)
            if remaining_queries <= 0 and user_id != ADMIN_ID:
                await bot.send_message(chat_id=chat_id, text="❌ Лимит запросов исчерпан.")
                return

            # 3. Обработка изображений (Исправлено под структуру MAX API)
            image_url = None
            if attachments:
                # logger.info(f"Анализ вложений: {attachments}")
                logger.info(f"Анализ вложений...")
                for attach in attachments:
                    # В MAX ссылка прячется внутри payload
                    payload = attach.get('payload', {})
                    url = payload.get('url')
                    
                    if attach.get('type') == 'image' and url:
                        image_url = url
                        logger.info(f"Ура! Ссылка на фото получена: {image_url}")
                        break

            # 4. Контекст памяти
            history = await db.get_recent_history(user_id, limit=5)
            
            # Важно: если текста нет (пользователь скинул только фото), 
            # добавляем дефолтный вопрос, чтобы модель понимала, что делать.
            current_text = user_text if user_text else "Что на этом изображении?"
            full_messages = [SYSTEM_PROMPT] + history + [{"role": "user", "content": current_text}]

            # 5. Запрос к ИИ (передаем URL картинки, если он есть)
            logger.info(f"Запрос к ИИ для чата {chat_id}. Контекст: {len(full_messages)} сообщ.")
            ai_response = await brain.get_answer(full_messages, image_url=image_url)

            # 6. Отправка и сохранение
            await bot.send_message(chat_id=chat_id, text=ai_response)
            
            # Сохраняем в историю текст пользователя (или пометку о фото)
            log_text = user_text if user_text else "[Изображение]"
            await db.save_message(user_id, 'user', log_text)
            await db.save_message(user_id, 'assistant', ai_response)
            
            logger.info(f"Воркер успешно завершил работу для {user_id}")

        except Exception as e:
            logger.error(f"Ошибка воркера {user_id}: {e}")
            await bot.send_message(chat_id=chat_id, text="🤖 Произошла ошибка при обработке сообщения.")

worker_manager = ProcessManager()