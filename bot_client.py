import aiohttp
from logger_config import logger

class MaxBot:
    def __init__(self, token):
        self.token = token
        self.base_url = "https://platform-api.max.ru" 

    async def send_message(self, chat_id, text, reply_markup=None):
        """
        Исправленная отправка: используем chat_id в параметрах URL
        """
        # Меняем user_id на chat_id в строке запроса
        url = f"{self.base_url}/messages?chat_id={chat_id}"
        
        payload = {
            "text": text
        }
        
        if reply_markup:
            payload["attachments"] = reply_markup

        headers = {
            "Authorization": self.token,
            "Content-Type": "application/json"
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers) as resp:
                    if resp.status in [200, 201]:
                        logger.info(f"Сообщение успешно доставлено в чат {chat_id}")
                    else:
                        err = await resp.text()
                        logger.error(f"Ошибка API MAX ({resp.status}): {err}")
        except Exception as e:
            logger.error(f"Критическая ошибка HTTP: {e}")