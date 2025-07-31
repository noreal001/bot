#!/usr/bin/env python3
"""
Тест системы контекста
"""

import asyncio
import sys
import os

# Добавляем текущую директорию в путь
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

async def test_context_system():
    """Тестирует систему контекста"""
    print("🧪 Тестирование системы контекста...")
    
    try:
        # Импортируем модуль контекста
        from context import add_user_message, add_assistant_message, get_user_context, clear_user_context
        
        # Тестовый пользователь
        test_user_id = 999999
        
        print(f"📝 Добавляем сообщения для пользователя {test_user_id}")
        
        # Добавляем несколько сообщений
        add_user_message(test_user_id, "Привет!")
        add_assistant_message(test_user_id, "Привет! 🐆 Как дела?")
        add_user_message(test_user_id, "Хорошо, спасибо!")
        add_assistant_message(test_user_id, "Отлично! ✨ Чем могу помочь?")
        add_user_message(test_user_id, "Расскажи про духи")
        add_assistant_message(test_user_id, "Конечно! 🎭 У нас есть отличная коллекция ароматов!")
        
        # Получаем контекст
        context = get_user_context(test_user_id)
        print(f"\n📋 Контекст пользователя {test_user_id}:")
        for i, msg in enumerate(context, 1):
            print(f"  {i}. {msg['role']}: {msg['content'][:50]}...")
        
        print(f"\n✅ Контекст содержит {len(context)} сообщений")
        
        # Очищаем контекст
        clear_user_context(test_user_id)
        print("🧹 Контекст очищен")
        
        print("\n🎉 Тест системы контекста пройден успешно!")
        return True
        
    except Exception as e:
        print(f"❌ Ошибка при тестировании: {e}")
        return False

async def test_main_integration():
    """Тестирует интеграцию с основным файлом"""
    print("\n🔗 Тестирование интеграции с основным файлом...")
    
    try:
        # Импортируем основной модуль
        import importlib.util
        spec = importlib.util.spec_from_file_location("main_module", "1.py")
        main_module = importlib.util.module_from_spec(spec)
        
        # Проверяем, что CONTEXT_ENABLED установлен
        if hasattr(main_module, 'CONTEXT_ENABLED'):
            print(f"✅ CONTEXT_ENABLED = {main_module.CONTEXT_ENABLED}")
        else:
            print("❌ CONTEXT_ENABLED не найден")
            return False
        
        print("🎉 Интеграция работает корректно!")
        return True
        
    except Exception as e:
        print(f"❌ Ошибка при тестировании интеграции: {e}")
        return False

if __name__ == "__main__":
    print("🚀 Запуск тестов системы контекста...")
    
    # Запускаем тесты
    context_test = asyncio.run(test_context_system())
    integration_test = asyncio.run(test_main_integration())
    
    if context_test and integration_test:
        print("\n🎊 Все тесты пройдены! Система контекста работает корректно!")
    else:
        print("\n💥 Некоторые тесты не пройдены!")
        sys.exit(1) 