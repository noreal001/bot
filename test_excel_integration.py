#!/usr/bin/env python3
"""
Демонстрация интеграции Excel данных с AI медвежонком
"""

import pandas as pd
import re

def get_quality_name(quality_code):
    """Конвертирует код качества в краткое название"""
    quality_map = {
        6: 'TOP',
        5: 'Q1', 
        4: 'Q2'
    }
    return quality_map.get(quality_code, f'{quality_code}')

# Загрузка данных из Excel
def load_excel_demo():
    """Демо загрузки данных"""
    print("🔄 Загружаю данные из Google Sheets...")
    
    GOOGLE_SHEETS_URL = "https://docs.google.com/spreadsheets/d/1rvb3QdanuukCyXnoQZZxz7HF6aJXm2de/export?format=xlsx&gid=1870986273"
    
    try:
        # Читаем данные напрямую из Google Sheets
        df = pd.read_excel(GOOGLE_SHEETS_URL, header=2, skiprows=[3])
        
        # Очищаем данные
        df = df.dropna(how='all')
        
        # Фильтруем по наличию бренда и аромата
        df = df[df.iloc[:, 3].notna() & df.iloc[:, 4].notna()]  # Столбцы F и G
        
        # Переименовываем столбцы
        column_mapping = {
            df.columns[3]: 'Бренд',      # Столбец F
            df.columns[4]: 'Аромат',     # Столбец G  
            df.columns[5]: 'Пол',        # Столбец H
            df.columns[6]: 'Фабрика',    # Столбец I
            df.columns[7]: 'Качество',   # Столбец J
            df.columns[8]: '30 GR',      # Столбец K
            df.columns[9]: '50 GR',      # Столбец L
            df.columns[10]: '500 GR',    # Столбец M
            df.columns[11]: '1 KG',      # Столбец N
        }
        
        # Найдем столбцы TOP LAST и TOP ALL
        for i, col in enumerate(df.columns):
            if 'TOP LAST' in str(col):
                column_mapping[col] = 'TOP LAST'
            elif 'TOP ALL' in str(col):
                column_mapping[col] = 'TOP ALL'
        
        df = df.rename(columns=column_mapping)
        
        # Конвертируем типы данных
        price_columns = ['30 GR', '50 GR', '500 GR', '1 KG']
        for col in price_columns:
            if col in df.columns:
                # Убираем символы валюты и конвертируем в числа
                df[col] = df[col].astype(str).str.replace('₽', '').str.replace(' ', '')
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # Конвертируем столбцы популярности
        if 'TOP LAST' in df.columns:
            df['TOP LAST'] = df['TOP LAST'].astype(str).str.replace('%', '').str.replace(',', '.')
            df['TOP LAST'] = pd.to_numeric(df['TOP LAST'], errors='coerce') / 100
        
        if 'TOP ALL' in df.columns:
            df['TOP ALL'] = df['TOP ALL'].astype(str).str.replace('%', '').str.replace(',', '.')
            df['TOP ALL'] = pd.to_numeric(df['TOP ALL'], errors='coerce') / 100
        
        print(f"✅ Загружено {len(df)} товаров из Google Sheets")
        return df
        
    except Exception as e:
        print(f"❌ Ошибка загрузки из Google Sheets: {e}")
        print("🔄 Пытаюсь загрузить локальный файл...")
        
        # Fallback к локальному файлу
        df = pd.read_excel('1.xlsx', header=2, skiprows=[3])
        df = df.dropna(how='all')
        df = df[~df['Бренд'].astype(str).str.contains('Column', na=False)]
        df = df[df['Бренд'].notna()]
        
        # Конвертируем числовые столбцы
        numeric_columns = ['30 GR', '50 GR', '500 GR', '1 KG', '5 KG', '10 KG', 'TOP LAST', 'TOP ALL']
        for col in numeric_columns:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        print(f"✅ Загружено {len(df)} товаров из локального файла")
        return df

def search_products_demo(df, query):
    """Демо поиска товаров"""
    print(f"\n🔍 Ищу товары по запросу: '{query}'")
    
    query_lower = query.lower()
    mask = (
        df['Бренд'].astype(str).str.lower().str.contains(query_lower, na=False) |
        df['Аромат'].astype(str).str.lower().str.contains(query_lower, na=False)
    )
    
    results = df[mask].head(5)
    print(f"Найдено: {len(results)} товаров")
    
    for i, (idx, row) in enumerate(results.iterrows()):
        print(f"  {i+1}. {row['Бренд']} - {row['Аромат']}")
        print(f"     🏭 Фабрика: {row['Фабрика']}, ⭐ Качество: {get_quality_name(row['Качество'])}")
        print(f"     💰 Цены: 50мл={row.get('50 GR', 'N/A')}₽/мл, 500мл={row.get('500 GR', 'N/A')}₽/мл")
        print()
    
    return results

def calculate_price_demo(product, volume):
    """Демо расчета цены"""
    print(f"\n💰 Расчет цены для {volume}мл:")
    
    if 30 <= volume < 50:
        price_per_ml = product.get('30 GR', 0)
        category = "30-49 мл"
    elif 50 <= volume < 500:
        price_per_ml = product.get('50 GR', 0)
        category = "50-499 мл"
    elif 500 <= volume < 1000:
        price_per_ml = product.get('500 GR', 0)
        category = "500-999 мл"
    elif volume >= 1000:
        price_per_ml = product.get('1 KG', 0)
        category = "1000+ мл"
    else:
        price_per_ml = product.get('30 GR', 0)
        category = "до 30 мл"
    
    if price_per_ml and not pd.isna(price_per_ml):
        total_price = float(price_per_ml) * volume
        print(f"  📊 Категория: {category}")
        print(f"  💵 Цена за мл: {price_per_ml}₽")
        print(f"  🛒 Общая стоимость: {total_price:,.0f}₽")
        return total_price
    else:
        print("  ❌ Цена недоступна")
        return None

def create_ai_context_demo(df, query):
    """Демо создания контекста для AI"""
    print(f"\n🤖 Создаю контекст для AI медвежонка...")
    
    # Поиск релевантных товаров
    query_lower = query.lower()
    mask = (
        df['Бренд'].astype(str).str.lower().str.contains(query_lower, na=False) |
        df['Аромат'].astype(str).str.lower().str.contains(query_lower, na=False)
    )
    
    products = df[mask].head(3)
    
    context = "=== АКТУАЛЬНЫЕ ДАННЫЕ ИЗ ПРАЙС-ЛИСТА ===\n\n"
    
    if len(products) > 0:
        context += f"🔍 НАЙДЕННЫЕ АРОМАТЫ ПО ЗАПРОСУ '{query}':\n"
        for _, product in products.iterrows():
            context += f"🏷️ {product['Бренд']} - {product['Аромат']}\n"
            context += f"🏭 Фабрика: {product['Фабрика']}\n"
            context += f"⭐ Качество: {get_quality_name(product['Качество'])}\n"
            
            prices = []
            for col, range_text in [('30 GR', '30-49мл'), ('50 GR', '50-499мл'), 
                                   ('500 GR', '500-999мл'), ('1 KG', '1000+мл')]:
                price = product.get(col)
                if price and not pd.isna(price):
                    prices.append(f"{range_text}: {price}₽/мл")
            
            if prices:
                context += f"💰 Цены: {', '.join(prices)}\n"
            
            # Популярность
            top_last = product.get('TOP LAST')
            if top_last and not pd.isna(top_last):
                context += f"📈 Популярность (6 мес): {float(top_last)*100:.2f}%\n"
            
            context += "\n"
    
    # Топ товары
    if 'TOP LAST' in df.columns and df['TOP LAST'].notna().sum() > 0:
        top_products = df.nlargest(3, 'TOP LAST')
        context += "🔥 ТОП-3 ПОПУЛЯРНЫХ АРОМАТОВ:\n"
        for i, (_, product) in enumerate(top_products.iterrows(), 1):
            popularity = product.get('TOP LAST', 0)
            if pd.notna(popularity):
                context += f"{i}. {product['Бренд']} - {product['Аромат']} "
                context += f"({float(popularity)*100:.2f}% популярности)\n"
            else:
                context += f"{i}. {product['Бренд']} - {product['Аромат']}\n"
    else:
        context += "🔥 ТОП АРОМАТОВ: данные недоступны\n"
    
    context += "\n🏭 ФАБРИКИ: EPS, LUZI, SELUZ, UNKNOWN, MANE\n"
    context += "⭐ КАЧЕСТВА: TOP > Q1 > Q2\n"
    
    print("✅ Контекст создан")
    return context

def main():
    """Главная демо функция"""
    print("=" * 60)
    print("🐻 ДЕМО: ИНТЕГРАЦИЯ EXCEL ДАННЫХ С AI МЕДВЕЖОНКОМ")
    print("=" * 60)
    
    # 1. Загрузка данных
    df = load_excel_demo()
    
    # 2. Поиск товаров
    search_query = "AJMAL"
    results = search_products_demo(df, search_query)
    
    # 3. Расчет цены
    if len(results) > 0:
        product = results.iloc[0]
        calculate_price_demo(product, 60)  # 60 мл
        calculate_price_demo(product, 300)  # 300 мл
    
    # 4. Создание контекста для AI
    ai_context = create_ai_context_demo(df, search_query)
    
    # 5. Демо ответа медвежонка
    print(f"\n🐻 Пример ответа AI медвежонка:")
    print("-" * 50)
    print(f"Привет! Нашел для тебя ароматы {search_query}! 🌟")
    print()
    
    if len(results) > 0:
        product = results.iloc[0]
        print(f"🏷️ {product['Бренд']} - {product['Аромат']}")
        print(f"🏭 Фабрика {product['Фабрика']}, качество {get_quality_name(product['Качество'])}")
        
        if product.get('50 GR') and not pd.isna(product.get('50 GR')):
            price_50ml = float(product['50 GR']) * 50
            price_100ml = float(product['50 GR']) * 100
            print(f"💰 Цены: 50мл = {price_50ml:,.0f}₽, 100мл = {price_100ml:,.0f}₽")
        
        print()
        print("<a href='https://www.bahur.store/'>🛒 Заказать</a>")
    
    print("-" * 50)
    print()
    print("=" * 60)
    print("✅ ДЕМОНСТРАЦИЯ ЗАВЕРШЕНА!")
    print("🚀 Медвежонок теперь знает актуальные цены и может:")
    print("   • Искать товары по названию")
    print("   • Рассчитывать точные цены для любого объема")
    print("   • Показывать популярные ароматы")
    print("   • Учитывать фабрики и качество")
    print("   • Давать персонализированные рекомендации")
    print("=" * 60)

if __name__ == "__main__":
    main() 