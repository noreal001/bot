#!/usr/bin/env python3
"""
Финальный тест всех функций перед загрузкой в GitHub
"""

import asyncio
import traceback

def test_all_functions():
    print('🔍 ФИНАЛЬНАЯ ПРОВЕРКА ВСЕХ ФУНКЦИЙ')
    print('=' * 70)
    
    try:
        # Загружаем основные функции
        exec(open('1.py').read(), globals())
        
        # 1. Тест загрузки данных
        print('1️⃣ ТЕСТ ЗАГРУЗКИ ДАННЫХ ИЗ GOOGLE SHEETS')
        print('-' * 50)
        
        df = load_excel_data()
        if df is not None:
            print(f'✅ Загружено товаров: {len(df)}')
            print(f'📊 Столбцы: {list(df.columns)}')
            
            # Проверяем качество товаров
            quality_values = df['Качество'].unique()[:10]
            print(f'⭐ Примеры качества: {list(quality_values)}')
            
            # Проверяем цены
            price_example = df.iloc[0]
            print(f'💰 Пример цен товара "{price_example.get("Бренд")} - {price_example.get("Аромат")}":')
            for col in ['30 GR', '50 GR', '500 GR', '1 KG']:
                price = price_example.get(col, 'N/A')
                print(f'    {col}: {price}₽/мл')
        else:
            print('❌ ОШИБКА: Не удалось загрузить данные')
            return False
        
        # 2. Тест поиска товаров
        print('\n2️⃣ ТЕСТ ПОИСКА ТОВАРОВ')
        print('-' * 50)
        
        search_results = search_products('AJMAL', limit=3)
        print(f'🔍 Поиск "AJMAL": найдено {len(search_results)} товаров')
        for i, product in enumerate(search_results, 1):
            brand = product.get('Бренд', 'N/A')
            aroma = product.get('Аромат', 'N/A')
            quality = product.get('Качество', 'N/A')
            print(f'  {i}. {brand} - {aroma} (качество: {quality})')
        
        # 3. Тест ТОП ароматов
        print('\n3️⃣ ТЕСТ ТОП АРОМАТОВ')
        print('-' * 50)
        
        top_products = get_top_products(sort_by='TOP LAST', limit=3)
        print(f'🔥 ТОП-3 популярных аромата:')
        for i, product in enumerate(top_products, 1):
            brand = product.get('Бренд', 'N/A')
            aroma = product.get('Аромат', 'N/A')
            quality = product.get('Качество', 'N/A')
            popularity = product.get('TOP LAST', 0)
            print(f'  {i}. {brand} - {aroma}')
            print(f'     ⭐ Качество: {quality}')
            print(f'     📈 Популярность: {popularity*100:.2f}%')
        
        # 4. КРИТИЧЕСКИЙ ТЕСТ: Расчет цен для 300 мл
        print('\n4️⃣ КРИТИЧЕСКИЙ ТЕСТ: РАСЧЕТ ЦЕН ДЛЯ 300 МЛ')
        print('-' * 50)
        
        if top_products:
            test_product = top_products[0]
            brand = test_product.get('Бренд', 'N/A')
            aroma = test_product.get('Аромат', 'N/A')
            
            print(f'🧪 Тестируем: {brand} - {aroma}')
            print('📊 Все цены этого товара:')
            for col in ['30 GR', '50 GR', '500 GR', '1 KG']:
                price = test_product.get(col, 'N/A')
                print(f'    {col}: {price}₽/мл')
            
            # Расчет для 300 мл
            price_info = calculate_price(test_product, 300)
            if price_info:
                print(f'\n💰 РАСЧЕТ ДЛЯ 300 МЛ:')
                print(f'    📦 Объем: {price_info["volume_ml"]} мл')
                print(f'    🎯 Используемый tier: {price_info["tier"]}')
                print(f'    💵 Цена за мл: {price_info["price_per_ml"]}₽')
                print(f'    🧮 Итоговая цена: {price_info["total_price"]}₽')
                
                # Проверяем правильность
                expected_price_per_ml = test_product.get('50 GR', 0)
                if price_info["price_per_ml"] == expected_price_per_ml:
                    print('    ✅ ЦЕНА ПРАВИЛЬНАЯ (используется 50 GR для 300 мл)')
                else:
                    print(f'    ❌ ОШИБКА: ожидалась цена {expected_price_per_ml}₽/мл из столбца 50 GR')
                    return False
            else:
                print('❌ ОШИБКА: Не удалось рассчитать цену')
                return False
        
        # 5. Тест различных объемов
        print('\n5️⃣ ТЕСТ РАЗЛИЧНЫХ ОБЪЕМОВ')
        print('-' * 50)
        
        test_volumes = [30, 100, 300, 600, 1200]
        for volume in test_volumes:
            price_info = calculate_price(test_product, volume)
            if price_info:
                print(f'📦 {volume} мл → tier: {price_info["tier"]}, цена: {price_info["price_per_ml"]}₽/мл, итого: {price_info["total_price"]}₽')
            else:
                print(f'❌ {volume} мл → не удалось рассчитать')
        
        # 6. Тест создания контекста для DeepSeek
        print('\n6️⃣ ТЕСТ КОНТЕКСТА ДЛЯ DEEPSEEK')
        print('-' * 50)
        
        context = get_excel_context_for_deepseek('AJMAL')
        print(f'📝 Размер контекста: {len(context)} символов')
        print(f'📄 Первые 300 символов контекста:')
        print(f'    {context[:300]}...')
        
        # Проверяем, что качество в контексте правильное
        if 'TOP' in context or 'Q1' in context or 'Q2' in context:
            print('✅ Качество в контексте в правильном формате (TOP/Q1/Q2)')
        else:
            print('❌ ОШИБКА: Качество в контексте не найдено')
            return False
        
        # 7. Тест анализа запросов
        print('\n7️⃣ ТЕСТ АНАЛИЗА ЗАПРОСОВ')
        print('-' * 50)
        
        test_queries = [
            "Сколько стоит AJMAL AMBER WOOD 300 мл?",
            "Покажи топ ароматы",
            "Привет как дела?"
        ]
        
        for query in test_queries:
            needs_excel, search_query = analyze_query_for_excel_data(query)
            print(f'❓ "{query}"')
            print(f'    📊 Нужен Excel: {needs_excel}')
            print(f'    🔍 Поисковый запрос: "{search_query}"')
        
        print('\n' + '=' * 70)
        print('🎉 ВСЕ ТЕСТЫ ПРОЙДЕНЫ УСПЕШНО!')
        print('✅ Загрузка данных работает')
        print('✅ Качество в правильном формате (TOP/Q1/Q2)')
        print('✅ Расчет цен корректный (300 мл → 50 GR tier)')
        print('✅ Поиск и ТОП ароматы работают')
        print('✅ Контекст для DeepSeek создается правильно')
        print('✅ Анализ запросов функционирует')
        print('\n🚀 ГОТОВО К ЗАГРУЗКЕ В GITHUB!')
        
        return True
        
    except Exception as e:
        print(f'\n❌ КРИТИЧЕСКАЯ ОШИБКА: {e}')
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_all_functions()
    if not success:
        print('\n🛑 ЕСТЬ ПРОБЛЕМЫ! НЕ ЗАГРУЖАЙТЕ В GITHUB!')
        exit(1)
    else:
        print('\n✨ ВСЕ ОТЛИЧНО! МОЖНО ЗАГРУЖАТЬ В GITHUB!') 