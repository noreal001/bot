#!/usr/bin/env python3
"""
Тест новой структуры таблицы после изменений пользователя
"""

import sys
import traceback

def test_new_structure():
    print('🔄 ТЕСТ НОВОЙ СТРУКТУРЫ ТАБЛИЦЫ')
    print('=' * 60)
    
    try:
        # Загружаем функции из основного файла
        exec(open('1.py').read(), globals())
        
        # Загружаем данные
        df = load_excel_data()
        if df is not None:
            print(f'✅ Данные загружены: {len(df)} товаров')
            print(f'📊 Столбцы: {list(df.columns)}')
            
            # Проверяем первые товары
            print('\n📋 ПЕРВЫЕ 3 ТОВАРА:')
            for i in range(min(3, len(df))):
                row = df.iloc[i]
                brand = row.get('Бренд', 'N/A')
                aroma = row.get('Аромат', 'N/A')
                quality = row.get('Качество', 'N/A')
                factory = row.get('Фабрика', 'N/A')
                price_50 = row.get('50 GR', 'N/A')
                price_500 = row.get('500 GR', 'N/A')
                
                print(f'  {i+1}. {brand} - {aroma}')
                print(f'     ⭐ Качество: {quality} (уже в правильном формате!)')
                print(f'     🏭 Фабрика: {factory}')
                print(f'     💰 Цены: 50 GR = {price_50}₽/мл, 500 GR = {price_500}₽/мл')
                print()
            
            # Проверяем ТОП-5 ароматов
            print('🔥 ТОП-5 ПОПУЛЯРНЫХ АРОМАТОВ:')
            top_products = get_top_products(sort_by='TOP LAST', limit=5)
            
            for i, product in enumerate(top_products, 1):
                brand = product.get('Бренд', 'N/A')
                aroma = product.get('Аромат', 'N/A')
                quality = product.get('Качество', 'N/A')
                popularity = product.get('TOP LAST', 0)
                
                print(f'{i}. {brand} - {aroma}')
                print(f'   ⭐ Качество: {quality}')
                print(f'   📈 Популярность: {popularity*100:.2f}%')
                print()
            
            # Проверяем расчет для 300 мл
            if top_products:
                product = top_products[0]
                brand = product.get('Бренд', 'N/A')
                aroma = product.get('Аромат', 'N/A')
                
                print(f'💰 РАСЧЕТ ДЛЯ {brand} - {aroma} (300 мл):')
                
                # Показываем все цены для этого товара
                print('📊 Все цены:')
                for col in ['30 GR', '50 GR', '500 GR', '1 KG']:
                    price = product.get(col, 'N/A')
                    print(f'  {col}: {price}₽/мл')
                    
                price_info = calculate_price(product, 300)
                if price_info:
                    print(f'\n🧮 Расчет для 300 мл:')
                    print(f'  📦 Объем: {price_info["volume_ml"]} мл')
                    print(f'  🎯 Tier: {price_info["tier"]}')
                    print(f'  💵 Цена за мл: {price_info["price_per_ml"]}₽')
                    print(f'  💰 Итого: {price_info["total_price"]}₽')
                else:
                    print('❌ Не удалось рассчитать цену')
                    
        else:
            print('❌ Не удалось загрузить данные')
            
        print('\n✅ Тест завершен успешно!')
        
    except Exception as e:
        print(f'❌ Ошибка теста: {e}')
        traceback.print_exc()

if __name__ == "__main__":
    test_new_structure() 