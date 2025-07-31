import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional

class ConversationContext:
    """Класс для управления контекстом разговора с пользователями"""
    
    def __init__(self, max_messages: int = 10, context_file: str = "conversation_context.json"):
        self.max_messages = max_messages
        self.context_file = context_file
        self.conversations: Dict[int, List[dict]] = {}
        self.load_context()
    
    def load_context(self):
        """Загружает контекст из файла"""
        try:
            if os.path.exists(self.context_file):
                with open(self.context_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # Конвертируем строковые ключи обратно в int
                    self.conversations = {int(k): v for k, v in data.items()}
                print(f"Загружен контекст для {len(self.conversations)} пользователей")
            else:
                print("Файл контекста не найден, создаем новый")
        except Exception as e:
            print(f"Ошибка при загрузке контекста: {e}")
            self.conversations = {}
    
    def save_context(self):
        """Сохраняет контекст в файл"""
        try:
            with open(self.context_file, 'w', encoding='utf-8') as f:
                json.dump(self.conversations, f, ensure_ascii=False, indent=2)
            print(f"Контекст сохранен для {len(self.conversations)} пользователей")
        except Exception as e:
            print(f"Ошибка при сохранении контекста: {e}")
    
    def add_message(self, user_id: int, role: str, content: str, timestamp: Optional[datetime] = None):
        """Добавляет сообщение в контекст пользователя"""
        if timestamp is None:
            timestamp = datetime.now()
        
        message = {
            "role": role,
            "content": content,
            "timestamp": timestamp.isoformat()
        }
        
        if user_id not in self.conversations:
            self.conversations[user_id] = []
        
        # Добавляем новое сообщение
        self.conversations[user_id].append(message)
        
        # Ограничиваем количество сообщений
        if len(self.conversations[user_id]) > self.max_messages:
            self.conversations[user_id] = self.conversations[user_id][-self.max_messages:]
        
        # Сохраняем контекст
        self.save_context()
        
        print(f"Добавлено сообщение для пользователя {user_id}, всего сообщений: {len(self.conversations[user_id])}")
    
    def get_context(self, user_id: int) -> List[dict]:
        """Возвращает контекст пользователя"""
        return self.conversations.get(user_id, [])
    
    def get_context_for_ai(self, user_id: int) -> List[dict]:
        """Возвращает контекст в формате для OpenAI API"""
        context = self.get_context(user_id)
        # Убираем timestamp из сообщений для API
        ai_context = []
        for msg in context:
            ai_context.append({
                "role": msg["role"],
                "content": msg["content"]
            })
        return ai_context
    
    def clear_context(self, user_id: int):
        """Очищает контекст пользователя"""
        if user_id in self.conversations:
            del self.conversations[user_id]
            self.save_context()
            print(f"Контекст пользователя {user_id} очищен")
    
    def get_user_stats(self, user_id: int) -> dict:
        """Возвращает статистику пользователя"""
        context = self.get_context(user_id)
        if not context:
            return {"message_count": 0, "last_message": None}
        
        return {
            "message_count": len(context),
            "last_message": context[-1]["timestamp"] if context else None,
            "user_messages": len([msg for msg in context if msg["role"] == "user"]),
            "assistant_messages": len([msg for msg in context if msg["role"] == "assistant"])
        }
    
    def cleanup_old_contexts(self, days: int = 30):
        """Очищает старые контексты (старше указанного количества дней)"""
        cutoff_date = datetime.now() - timedelta(days=days)
        users_to_remove = []
        
        for user_id, messages in self.conversations.items():
            if messages:
                last_message_time = datetime.fromisoformat(messages[-1]["timestamp"])
                if last_message_time < cutoff_date:
                    users_to_remove.append(user_id)
        
        for user_id in users_to_remove:
            del self.conversations[user_id]
        
        if users_to_remove:
            self.save_context()
            print(f"Удалены контексты {len(users_to_remove)} неактивных пользователей")
    
    def get_all_users(self) -> List[int]:
        """Возвращает список всех пользователей с контекстом"""
        return list(self.conversations.keys())
    
    def get_total_stats(self) -> dict:
        """Возвращает общую статистику"""
        total_users = len(self.conversations)
        total_messages = sum(len(messages) for messages in self.conversations.values())
        
        return {
            "total_users": total_users,
            "total_messages": total_messages,
            "average_messages_per_user": total_messages / total_users if total_users > 0 else 0
        }

# Создаем глобальный экземпляр контекста
conversation_context = ConversationContext(max_messages=10)

# Функции для интеграции с основным ботом
def add_user_message(user_id: int, content: str):
    """Добавляет сообщение пользователя в контекст"""
    conversation_context.add_message(user_id, "user", content)

def add_assistant_message(user_id: int, content: str):
    """Добавляет ответ ассистента в контекст"""
    conversation_context.add_message(user_id, "assistant", content)

def get_user_context(user_id: int) -> List[dict]:
    """Получает контекст пользователя для OpenAI API"""
    return conversation_context.get_context_for_ai(user_id)

def clear_user_context(user_id: int):
    """Очищает контекст пользователя"""
    conversation_context.clear_context(user_id)

def get_user_conversation_stats(user_id: int) -> dict:
    """Получает статистику разговора пользователя"""
    return conversation_context.get_user_stats(user_id)

# Пример использования
if __name__ == "__main__":
    # Тестируем функциональность
    test_user_id = 12345
    
    # Добавляем несколько сообщений
    add_user_message(test_user_id, "Привет!")
    add_assistant_message(test_user_id, "Привет! 🐆 Как дела?")
    add_user_message(test_user_id, "Хорошо, спасибо!")
    add_assistant_message(test_user_id, "Отлично! ✨ Чем могу помочь?")
    
    # Получаем контекст
    context = get_user_context(test_user_id)
    print(f"Контекст пользователя {test_user_id}:")
    for msg in context:
        print(f"  {msg['role']}: {msg['content']}")
    
    # Получаем статистику
    stats = get_user_conversation_stats(test_user_id)
    print(f"Статистика: {stats}")
    
    # Очищаем контекст
    clear_user_context(test_user_id)
    print("Контекст очищен")
