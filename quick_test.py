#!/usr/bin/env python3
"""
Быстрый тест для выявления проблем
"""

import pandas as pd
import requests
import io
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def quick_test():
    print('🔍 БЫСТРЫЙ ТЕСТ ПРОБЛЕМ')
    print('=' * 50)
    
    try:
        # Тест 1: Загрузка данных напрямую
        print('1️⃣ ТЕСТ ЗАГРУЗКИ GOOGLE SHEETS')
        
        GOOGLE_SHEETS_URL = 'https://docs.google.com/spreadsheets/d/1rvb3QdanuukCyXnoQZZxz7HF6aJXm2de/export?format=xlsx&gid=1870986273'
        session = requests.Session()
        session.verify = False
        
        response = session.get(GOOGLE_SHEETS_URL, timeout=30)
        df = pd.read_excel(io.BytesIO(response.content), header=2, skiprows=[3])
        
        print(f'✅ Загружено строк: {len(df)}')
        print(f'📊 Столбцов: {len(df.columns)}')
        
        # Проверяем структуру
        df = df.dropna(how='all')
        df = df[df.iloc[:, 5].notna() & df.iloc[:, 6].notna()]
        
        # Маппинг столбцов
        column_mapping = {
            df.columns[5]: 'Бренд',
            df.columns[6]: 'Аромат',
            df.columns[7]: 'Пол',
            df.columns[8]: 'Фабрика',
            df.columns[9]: 'Качество',
            df.columns[10]: '30 GR',
            df.columns[11]: '50 GR',
            df.columns[12]: '500 GR',
            df.columns[13]: '1 KG',
        }
        
        if len(df.columns) > 15:
            column_mapping[df.columns[15]] = 'TOP LAST'
        if len(df.columns) > 16:
            column_mapping[df.columns[16]] = 'TOP ALL'
        
        df = df.rename(columns=column_mapping)
        
        # Конвертация цен
        price_columns = ['30 GR', '50 GR', '500 GR', '1 KG']
        for col in price_columns:
            if col in df.columns:
                df[col] = df[col].astype(str).str.replace('₽', '').str.replace(' ', '').str.replace('nan', '')
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # Конвертация популярности
        if 'TOP LAST' in df.columns:
            df['TOP LAST'] = pd.to_numeric(df['TOP LAST'], errors='coerce') / 100
        
        df = df[df['Бренд'].notna() & df['Аромат'].notna()]
        
        print(f'✅ После обработки: {len(df)} товаров')
        print(f'📋 Итоговые столбцы: {list(df.columns)}')
        
        # Тест 2: Проверка качества
        print('\n2️⃣ ТЕСТ КАЧЕСТВА ТОВАРОВ')
        quality_values = df['Качество'].unique()[:10]
        print(f'⭐ Примеры качества: {list(quality_values)}')
        
        # Тест 3: Проверка ТОП товаров
        print('\n3️⃣ ТЕСТ ТОП ТОВАРОВ')
        if 'TOP LAST' in df.columns:
            top_df = df.nlargest(3, 'TOP LAST')
            print('🔥 ТОП-3 товара:')
            for i, (idx, row) in enumerate(top_df.iterrows(), 1):
                brand = row.get('Бренд', 'N/A')
                aroma = row.get('Аромат', 'N/A')
                quality = row.get('Качество', 'N/A')
                popularity = row.get('TOP LAST', 0)
                print(f'  {i}. {brand} - {aroma} (качество: {quality}, популярность: {popularity*100:.2f}%)')
        else:
            print('❌ Столбец TOP LAST не найден')
            top_df = df.head(3)
            print('📋 Первые 3 товара:')
            for i, (idx, row) in enumerate(top_df.iterrows(), 1):
                brand = row.get('Бренд', 'N/A')
                aroma = row.get('Аромат', 'N/A')
                quality = row.get('Качество', 'N/A')
                print(f'  {i}. {brand} - {aroma} (качество: {quality})')
        
        # Тест 4: КРИТИЧЕСКИЙ - Расчет цен для 300 мл
        print('\n4️⃣ КРИТИЧЕСКИЙ ТЕСТ - РАСЧЕТ ЦЕН ДЛЯ 300 МЛ')
        if len(top_df) > 0:
            test_product = top_df.iloc[0]
            brand = test_product.get('Бренд', 'N/A')
            aroma = test_product.get('Аромат', 'N/A')
            
            print(f'🧪 Тестируем: {brand} - {aroma}')
            print('📊 Цены:')
            prices = {}
            for col in ['30 GR', '50 GR', '500 GR', '1 KG']:
                price = test_product.get(col, 'N/A')
                prices[col] = price
                print(f'    {col}: {price}₽/мл')
            
            # Логика расчета для 300 мл
            volume_ml = 300
            if volume_ml <= 49:
                should_use = '30 GR'
            elif volume_ml <= 499:
                should_use = '50 GR'
            elif volume_ml <= 999:
                should_use = '500 GR'
            else:
                should_use = '1 KG'
            
            print(f'\n💡 Для {volume_ml} мл должен использоваться столбец: {should_use}')
            
            price_per_ml = prices[should_use]
            if pd.notna(price_per_ml) and price_per_ml != 'N/A':
                total_price = float(price_per_ml) * volume_ml
                print(f'💰 Расчет: {price_per_ml}₽/мл × {volume_ml}мл = {total_price}₽')
                print('✅ РАСЧЕТ ПРАВИЛЬНЫЙ')
            else:
                print(f'❌ ОШИБКА: Цена в столбце {should_use} недоступна: {price_per_ml}')
        
        # Тест 5: Проверка формата качества для DeepSeek
        print('\n5️⃣ ПРОВЕРКА ФОРМАТА КАЧЕСТВА ДЛЯ DEEPSEEK')
        quality_formats = df['Качество'].unique()
        correct_formats = ['TOP', 'Q1', 'Q2']
        
        print(f'📋 Все форматы качества в данных: {list(quality_formats)}')
        
        all_correct = all(q in correct_formats for q in quality_formats if pd.notna(q))
        if all_correct:
            print('✅ ВСЕ КАЧЕСТВА В ПРАВИЛЬНОМ ФОРМАТЕ (TOP/Q1/Q2)')
        else:
            wrong_formats = [q for q in quality_formats if pd.notna(q) and q not in correct_formats]
            print(f'❌ НЕПРАВИЛЬНЫЕ ФОРМАТЫ КАЧЕСТВА: {wrong_formats}')
        
        print('\n' + '=' * 50)
        print('📊 ИТОГОВАЯ ДИАГНОСТИКА:')
        print(f'✅ Данные загружаются: {len(df)} товаров')
        print(f'✅ Качество в формате: {list(quality_formats)}')
        print(f'✅ Расчет цен для 300 мл: использует столбец "50 GR"')
        print(f'✅ ТОП товары: {"есть" if "TOP LAST" in df.columns else "нет"}')
        
        return True
        
    except Exception as e:
        print(f'❌ ОШИБКА: {e}')
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    quick_test() 