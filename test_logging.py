#!/usr/bin/env python3
"""
Тест логирования статистики для DeepSeek
"""

import asyncio
import logging

# Настройка логирования для теста
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Импортируем функции из основного файла
def load_main_functions():
    import os
    import sys
    
    # Читаем основной файл
    with open('1.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Создаем глобальное окружение для выполнения
    global_env = {
        '__name__': '__main__',
        'logger': logger,
        'excel_data': None
    }
    
    # Выполняем код
    exec(content, global_env)
    
    return global_env

async def test_deepseek_logging():
    """Тест логирования запросов к DeepSeek"""
    print("🔄 Загружаем функции из основного файла...")
    
    try:
        env = load_main_functions()
        
        # Получаем функции
        analyze_query = env['analyze_query_for_excel_data']
        get_context = env['get_excel_context_for_deepseek']
        load_excel = env['load_excel_data']
        
        print("✅ Функции загружены успешно")
        
        # Загружаем данные Excel
        print("\n📊 Загружаем данные Excel...")
        excel_data = load_excel()
        env['excel_data'] = excel_data
        
        if excel_data is not None:
            print(f"✅ Данные загружены: {len(excel_data)} товаров")
        else:
            print("❌ Не удалось загрузить данные Excel")
            return
        
        # Тестируем различные запросы
        test_questions = [
            "Сколько стоит AJMAL AMBER WOOD?",
            "Покажи популярные ароматы BVLGARI", 
            "Какие есть ароматы от фабрики EPS?",
            "Привет, как дела?",
            "Расскажи про качество TOP"
        ]
        
        print("\n" + "="*60)
        print("🧪 ТЕСТИРОВАНИЕ ЛОГИРОВАНИЯ")
        print("="*60)
        
        for i, question in enumerate(test_questions, 1):
            print(f"\n🔍 ТЕСТ {i}: '{question}'")
            print("-" * 50)
            
            # Анализируем запрос
            needs_excel, search_query = analyze_query(question)
            
            # Если нужны Excel данные, создаем контекст
            if needs_excel:
                context = get_context(search_query)
                print(f"📄 Создан контекст: {len(context)} символов")
            else:
                print("ℹ️ Excel данные не требуются")
            
            print("-" * 50)
        
        print("\n✅ Тестирование логирования завершено!")
        print("🎯 Теперь вы можете видеть детальную статистику в логах Render")
        
    except Exception as e:
        print(f"❌ Ошибка теста: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_deepseek_logging()) 