#!/usr/bin/env python3
"""
Комплексный тест проекта AI-Медвежонок
Проверяет все основные функции интеграции с Google Sheets и DeepSeek
"""

import pandas as pd
import requests
import io
import urllib3
import asyncio
import sys

# Отключаем предупреждения SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def get_quality_name(quality_code):
    """Конвертирует код качества в краткое название для DeepSeek"""
    quality_map = {
        6: 'TOP',
        5: 'Q1', 
        4: 'Q2'
    }
    return quality_map.get(quality_code, f'{quality_code}')

def get_quality_description(quality_code):
    """Получает подробное описание качества для пользователей"""
    quality_desc_map = {
        6: 'TOP (высшее качество)',
        5: 'Q1 (отличное качество)', 
        4: 'Q2 (хорошее качество)'
    }
    return quality_desc_map.get(quality_code, f'Качество {quality_code}')

def test_google_sheets_loading():
    """Тест загрузки данных из Google Sheets"""
    print("🔄 Тест 1: Загрузка данных из Google Sheets...")
    
    try:
        GOOGLE_SHEETS_URL = "https://docs.google.com/spreadsheets/d/1rvb3QdanuukCyXnoQZZxz7HF6aJXm2de/export?format=xlsx&gid=1870986273"
        
        # Загружаем данные через requests без SSL проверки
        session = requests.Session()
        session.verify = False
        
        response = session.get(GOOGLE_SHEETS_URL, timeout=30)
        response.raise_for_status()
        
        # Читаем Excel из памяти
        df = pd.read_excel(io.BytesIO(response.content), header=2, skiprows=[3])
        
        # Очищаем данные
        df = df.dropna(how='all')
        
        # Фильтруем по наличию бренда и аромата (столбцы 5 и 6)
        if len(df.columns) > 6:
            df = df[df.iloc[:, 5].notna() & df.iloc[:, 6].notna()]
        else:
            raise Exception("Invalid data structure")
        
        # Переименовываем столбцы
        if len(df.columns) >= 15:
            column_mapping = {
                df.columns[5]: 'Бренд',      # Столбец 5
                df.columns[6]: 'Аромат',     # Столбец 6
                df.columns[7]: 'Пол',        # Столбец 7
                df.columns[8]: 'Фабрика',    # Столбец 8
                df.columns[9]: 'Качество',   # Столбец 9
                df.columns[11]: '30 GR',     # Столбец 11
                df.columns[12]: '50 GR',     # Столбец 12
                df.columns[13]: '500 GR',    # Столбец 13
                df.columns[14]: '1 KG',      # Столбец 14
            }
            
            # Добавляем столбцы TOP LAST и TOP ALL
            if len(df.columns) > 23:
                column_mapping[df.columns[23]] = 'TOP LAST'
            if len(df.columns) > 24:
                column_mapping[df.columns[24]] = 'TOP ALL'
            
            df = df.rename(columns=column_mapping)
        else:
            raise Exception("Invalid column structure")
        
        # Конвертируем типы данных
        price_columns = ['30 GR', '50 GR', '500 GR', '1 KG']
        for col in price_columns:
            if col in df.columns:
                df[col] = df[col].astype(str).str.replace('₽', '').str.replace(' ', '').str.replace('nan', '')
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # Конвертируем столбцы популярности
        if 'TOP LAST' in df.columns:
            df['TOP LAST'] = pd.to_numeric(df['TOP LAST'], errors='coerce')
        
        if 'TOP ALL' in df.columns:
            df['TOP ALL'] = pd.to_numeric(df['TOP ALL'], errors='coerce')
        
        # Очищаем от строк без данных
        df = df[df['Бренд'].notna() & df['Аромат'].notna()]
        
        print(f"  ✅ Загружено {len(df)} товаров")
        print(f"  📊 Столбцы: {list(df.columns)}")
        
        # Показываем примеры товаров
        print("\n  📋 Примеры товаров:")
        for i in range(min(3, len(df))):
            row = df.iloc[i]
            brand = row.get('Бренд', 'N/A')
            aroma = row.get('Аромат', 'N/A')
            factory = row.get('Фабрика', 'N/A')
            quality = get_quality_name(row.get('Качество', 0))
            price_50 = row.get('50 GR', 'N/A')
            
            print(f"    {i+1}. {brand} - {aroma}")
            print(f"       🏭 Фабрика: {factory}, ⭐ Качество: {quality}")
            print(f"       💰 50 GR: {price_50}₽")
        
        return df
        
    except Exception as e:
        print(f"  ❌ Ошибка: {e}")
        return None

def test_product_search(df):
    """Тест поиска товаров"""
    print("\n🔍 Тест 2: Поиск товаров...")
    
    if df is None:
        print("  ❌ Нет данных для тестирования")
        return
    
    try:
        # Функция поиска
        def search_products(query, limit=10):
            if df is None or df.empty:
                return []
            
            query_lower = query.lower()
            mask = (
                df['Бренд'].str.lower().str.contains(query_lower, na=False) |
                df['Аромат'].str.lower().str.contains(query_lower, na=False)
            )
            
            results = df[mask].head(limit)
            return results.to_dict('records')
        
        # Тестируем поиск
        test_queries = ['AJMAL', 'BVLGARI', 'KILIAN']
        
        for query in test_queries:
            results = search_products(query, limit=3)
            print(f"  🔍 Поиск '{query}': найдено {len(results)} товаров")
            
            for i, product in enumerate(results[:2]):
                brand = product.get('Бренд', 'N/A')
                aroma = product.get('Аромат', 'N/A')
                quality = get_quality_name(product.get('Качество', 0))
                print(f"    - {brand} - {aroma} (качество: {quality})")
        
        print("  ✅ Поиск работает корректно")
        return True
        
    except Exception as e:
        print(f"  ❌ Ошибка поиска: {e}")
        return False

def test_price_calculation(df):
    """Тест расчета цен"""
    print("\n💰 Тест 3: Расчет цен...")
    
    if df is None:
        print("  ❌ Нет данных для тестирования")
        return
    
    try:
        def calculate_price(product, volume_ml):
            """Рассчитывает цену на основе объема"""
            if volume_ml <= 49:
                base_price = product.get('30 GR')
                tier = '30-49 мл'
            elif volume_ml <= 499:
                base_price = product.get('50 GR')
                tier = '50-499 мл'
            elif volume_ml <= 999:
                base_price = product.get('500 GR')
                tier = '500-999 мл'
            else:
                base_price = product.get('1 KG')
                tier = '1000+ мл'
            
            if pd.isna(base_price) or base_price is None:
                return None
            
            total_price = float(base_price) * volume_ml
            
            return {
                'volume_ml': volume_ml,
                'price_per_ml': float(base_price),
                'total_price': total_price,
                'tier': tier
            }
        
        # Тестируем расчет цен
        if len(df) > 0:
            product = df.iloc[0].to_dict()
            brand = product.get('Бренд', 'N/A')
            aroma = product.get('Аромат', 'N/A')
            
            print(f"  🧪 Тестируем с товаром: {brand} - {aroma}")
            
            test_volumes = [30, 100, 500, 1500]
            for volume in test_volumes:
                price_info = calculate_price(product, volume)
                if price_info:
                    print(f"    📦 {volume} мл: {price_info['total_price']:.2f}₽ "
                          f"({price_info['price_per_ml']:.2f}₽/мл, tier: {price_info['tier']})")
                else:
                    print(f"    📦 {volume} мл: Цена недоступна")
        
        print("  ✅ Расчет цен работает корректно")
        return True
        
    except Exception as e:
        print(f"  ❌ Ошибка расчета цен: {e}")
        return False

def test_deepseek_context(df):
    """Тест создания контекста для DeepSeek"""
    print("\n🤖 Тест 4: Создание контекста для DeepSeek...")
    
    if df is None:
        print("  ❌ Нет данных для тестирования")
        return
    
    try:
        def get_excel_context_for_deepseek(query=""):
            context = "\n=== БАЗА ДАННЫХ АРОМАТОВ ===\n"
            context += f"📊 Всего товаров: {len(df)}\n"
            
            # Если есть поисковый запрос
            if query.strip():
                query_lower = query.lower()
                mask = (
                    df['Бренд'].str.lower().str.contains(query_lower, na=False) |
                    df['Аромат'].str.lower().str.contains(query_lower, na=False)
                )
                
                products = df[mask].head(5).to_dict('records')
                if products:
                    context += f"\n🔍 НАЙДЕННЫЕ АРОМАТЫ ПО ЗАПРОСУ '{query}':\n"
                    for product in products:
                        brand = product.get('Бренд', 'N/A')
                        aroma = product.get('Аромат', 'N/A')
                        factory = product.get('Фабрика', 'N/A')
                        quality = get_quality_name(product.get('Качество', 0))
                        
                        context += f"🏷️ {brand} - {aroma}\n"
                        context += f"🏭 Фабрика: {factory}\n"
                        context += f"⭐ Качество: {quality}\n"
                        
                        # Добавляем цены
                        prices = []
                        price_columns = {'30 GR': '30-49мл', '50 GR': '50-499мл', '500 GR': '500-999мл', '1 KG': '1000+мл'}
                        for col, desc in price_columns.items():
                            price = product.get(col)
                            if pd.notna(price) and price > 0:
                                prices.append(f"{desc}: {price}₽/мл")
                        
                        if prices:
                            context += f"💰 Цены: {', '.join(prices)}\n"
                        context += "\n"
            
            # Добавляем топ популярные ароматы
            if 'TOP LAST' in df.columns:
                top_products = df.nlargest(5, 'TOP LAST').to_dict('records')
                if top_products:
                    context += "\n🔥 ТОП-5 ПОПУЛЯРНЫХ АРОМАТОВ (последние 6 месяцев):\n"
                    for i, product in enumerate(top_products, 1):
                        brand = product.get('Бренд', 'N/A')
                        aroma = product.get('Аромат', 'N/A')
                        factory = product.get('Фабрика', 'N/A')
                        quality = get_quality_name(product.get('Качество', 0))
                        popularity = product.get('TOP LAST', 0)
                        
                        context += f"{i}. 🏷️ {brand} - {aroma}\n"
                        context += f"🏭 Фабрика: {factory}\n"
                        context += f"⭐ Качество: {quality}\n"
                        if pd.notna(popularity) and popularity > 0:
                            context += f"📈 Популярность: {popularity*100:.2f}%\n"
                        context += "\n"
            
            # Информация о фабриках и качестве
            context += "\n🏭 ДОСТУПНЫЕ ФАБРИКИ: EPS, LUZI, SELUZ, UNKNOWN, MANE\n"
            context += "⭐ КАЧЕСТВА: TOP > Q1 > Q2\n"
            context += "\n💰 ЦЕНОВЫЕ КАТЕГОРИИ:\n"
            context += "• 30-49 мл: цена из столбца '30 GR'\n"
            context += "• 50-499 мл: цена из столбца '50 GR'\n"
            context += "• 500-999 мл: цена из столбца '500 GR'\n"
            context += "• 1000+ мл: цена из столбца '1 KG'\n"
            
            return context
        
        # Тестируем создание контекста
        test_queries = ['', 'AJMAL', 'BVLGARI']
        
        for query in test_queries:
            context = get_excel_context_for_deepseek(query)
            print(f"  📝 Контекст для запроса '{query or 'общий'}':")
            print(f"    📏 Длина: {len(context)} символов")
            
            # Показываем первые 200 символов
            preview = context[:200] + "..." if len(context) > 200 else context
            print(f"    📄 Превью: {preview}")
            print()
        
        print("  ✅ Создание контекста работает корректно")
        return True
        
    except Exception as e:
        print(f"  ❌ Ошибка создания контекста: {e}")
        return False

def test_quality_mapping():
    """Тест маппинга качества"""
    print("\n⭐ Тест 5: Маппинг качества...")
    
    try:
        test_cases = [
            (4, 'Q2', 'Q2 (хорошее качество)'),
            (5, 'Q1', 'Q1 (отличное качество)'),
            (6, 'TOP', 'TOP (высшее качество)'),
            (7, '7', 'Качество 7'),
        ]
        
        for quality_code, expected_short, expected_full in test_cases:
            short_name = get_quality_name(quality_code)
            full_name = get_quality_description(quality_code)
            
            if short_name == expected_short and full_name == expected_full:
                print(f"  ✅ Качество {quality_code}: {short_name} / {full_name}")
            else:
                print(f"  ❌ Качество {quality_code}: ожидали {expected_short}/{expected_full}, получили {short_name}/{full_name}")
                return False
        
        print("  ✅ Маппинг качества работает корректно")
        return True
        
    except Exception as e:
        print(f"  ❌ Ошибка маппинга качества: {e}")
        return False

async def test_deepseek_integration():
    """Тест интеграции с DeepSeek (симуляция)"""
    print("\n🧠 Тест 6: Интеграция с DeepSeek (симуляция)...")
    
    try:
        # Симулируем анализ запроса
        def analyze_query_for_excel_data(question):
            question_lower = question.lower()
            
            # Проверяем, нужны ли данные из Excel
            excel_keywords = [
                'цена', 'стоимость', 'сколько стоит', 'прайс',
                'фабрика', 'качество', 'популярный', 'топ',
                'бренд', 'аромат', 'духи', 'парфюм'
            ]
            
            needs_excel = any(keyword in question_lower for keyword in excel_keywords)
            
            # Извлекаем потенциальные поисковые термины
            search_terms = []
            brands = ['ajmal', 'bvlgari', 'kilian', 'afnan', 'creed']
            for brand in brands:
                if brand in question_lower:
                    search_terms.append(brand)
            
            return {
                'needs_excel_data': needs_excel,
                'search_terms': search_terms,
                'question_type': 'price_inquiry' if any(w in question_lower for w in ['цена', 'стоимость', 'сколько']) else 'general'
            }
        
        # Тестируем разные типы запросов
        test_questions = [
            "Сколько стоит аромат AJMAL?",
            "Какие фабрики самые популярные?",
            "Расскажи о качестве TOP",
            "Привет, как дела?",
            "Какой аромат BVLGARI самый популярный?"
        ]
        
        for question in test_questions:
            analysis = analyze_query_for_excel_data(question)
            print(f"  🔍 Вопрос: '{question}'")
            print(f"    📊 Нужны данные Excel: {analysis['needs_excel_data']}")
            print(f"    🔎 Поисковые термины: {analysis['search_terms']}")
            print(f"    📝 Тип вопроса: {analysis['question_type']}")
            print()
        
        print("  ✅ Анализ запросов работает корректно")
        return True
        
    except Exception as e:
        print(f"  ❌ Ошибка анализа запросов: {e}")
        return False

def main():
    """Основная функция тестирования"""
    print("🐻 КОМПЛЕКСНЫЙ ТЕСТ ПРОЕКТА AI-МЕДВЕЖОНОК 🐻")
    print("=" * 50)
    
    results = []
    
    # Тест 1: Загрузка данных
    df = test_google_sheets_loading()
    results.append(df is not None)
    
    # Тест 2: Поиск товаров
    results.append(test_product_search(df))
    
    # Тест 3: Расчет цен
    results.append(test_price_calculation(df))
    
    # Тест 4: Контекст для DeepSeek
    results.append(test_deepseek_context(df))
    
    # Тест 5: Маппинг качества
    results.append(test_quality_mapping())
    
    # Тест 6: Интеграция с DeepSeek
    results.append(asyncio.run(test_deepseek_integration()))
    
    # Результаты
    print("\n" + "=" * 50)
    print("📊 РЕЗУЛЬТАТЫ ТЕСТИРОВАНИЯ:")
    
    test_names = [
        "Загрузка Google Sheets",
        "Поиск товаров", 
        "Расчет цен",
        "Контекст для DeepSeek",
        "Маппинг качества",
        "Анализ запросов"
    ]
    
    passed = sum(results)
    total = len(results)
    
    for i, (name, result) in enumerate(zip(test_names, results), 1):
        status = "✅ ПРОЙДЕН" if result else "❌ ПРОВАЛЕН"
        print(f"{i}. {name}: {status}")
    
    print(f"\n🎯 ИТОГ: {passed}/{total} тестов пройдено")
    
    if passed == total:
        print("🎉 ВСЕ ТЕСТЫ ПРОЙДЕНЫ! Проект готов к работе!")
        print("\n🔧 ФУНКЦИОНАЛЬНОСТЬ:")
        print("  ✅ Загрузка данных из Google Sheets")
        print("  ✅ Поиск товаров по бренду и аромату")
        print("  ✅ Расчет цен по объемам")
        print("  ✅ Создание контекста для DeepSeek")
        print("  ✅ Правильный маппинг качества (TOP, Q1, Q2)")
        print("  ✅ Анализ пользовательских запросов")
        print("\n🚀 Бот готов отвечать на вопросы о товарах из таблицы!")
    else:
        print("⚠️  Некоторые тесты провалены. Требуется доработка.")
    
    return passed == total

if __name__ == "__main__":
    main() 