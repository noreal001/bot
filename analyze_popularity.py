#!/usr/bin/env python3
"""
Скрипт для анализа самых популярных ароматов из прайса
"""

import pandas as pd
import sys
import os

# Добавляем путь к текущей директории
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Импортируем функцию загрузки данных из основного файла
from importlib import import_module
import importlib.util

# Загружаем модуль из 1.py
spec = importlib.util.spec_from_file_location("bot_module", "1.py")
bot_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bot_module)

def analyze_popularity():
    """Анализирует самые популярные ароматы"""
    try:
        # Загружаем данные
        print("📊 Загружаем данные из прайса...")
        df = bot_module.load_excel_data()
        
        if df is None or df.empty:
            print("❌ Не удалось загрузить данные")
            return
        
        print(f"✅ Загружено {len(df)} ароматов")
        
        # Проверяем наличие столбцов популярности
        if 'TOP LAST' not in df.columns or 'TOP ALL' not in df.columns:
            print("❌ Столбцы популярности не найдены")
            print(f"Доступные столбцы: {list(df.columns)}")
            return
        
        # Анализируем топ по последним 6 месяцам
        print("\n🔥 ТОП-10 самых популярных ароматов (последние 6 месяцев):")
        print("=" * 80)
        
        top_last = df.sort_values('TOP LAST', ascending=False).head(10)
        for i, (_, row) in enumerate(top_last.iterrows(), 1):
            brand = row.get('Бренд', 'N/A')
            aroma = row.get('Аромат', 'N/A')
            factory = row.get('Фабрика', 'N/A')
            quality = row.get('Качество', 'N/A')
            popularity = row.get('TOP LAST', 0)
            
            print(f"{i:2d}. {brand} - {aroma}")
            print(f"    🏭 {factory} | ⭐ {quality} | 📈 {popularity:.2f}%")
            print()
        
        # Анализируем топ за все время
        print("\n🌟 ТОП-10 самых популярных ароматов (за все время):")
        print("=" * 80)
        
        top_all = df.sort_values('TOP ALL', ascending=False).head(10)
        for i, (_, row) in enumerate(top_all.iterrows(), 1):
            brand = row.get('Бренд', 'N/A')
            aroma = row.get('Аромат', 'N/A')
            factory = row.get('Фабрика', 'N/A')
            quality = row.get('Качество', 'N/A')
            popularity = row.get('TOP ALL', 0)
            
            print(f"{i:2d}. {brand} - {aroma}")
            print(f"    🏭 {factory} | ⭐ {quality} | 📈 {popularity:.2f}%")
            print()
        
        # Анализ по фабрикам
        print("\n🏭 Популярность по фабрикам (TOP LAST):")
        print("=" * 50)
        factory_stats = df.groupby('Фабрика')['TOP LAST'].agg(['mean', 'sum', 'count']).sort_values('sum', ascending=False)
        for factory, stats in factory_stats.iterrows():
            print(f"{factory}: {stats['sum']:.2f}% (среднее: {stats['mean']:.2f}%, товаров: {stats['count']})")
        
        # Анализ по качеству
        print("\n⭐ Популярность по качеству (TOP LAST):")
        print("=" * 50)
        quality_stats = df.groupby('Качество')['TOP LAST'].agg(['mean', 'sum', 'count']).sort_values('sum', ascending=False)
        for quality, stats in quality_stats.iterrows():
            print(f"{quality}: {stats['sum']:.2f}% (среднее: {stats['mean']:.2f}%, товаров: {stats['count']})")
        
        # Самый популярный аромат
        most_popular_last = df.loc[df['TOP LAST'].idxmax()]
        most_popular_all = df.loc[df['TOP ALL'].idxmax()]
        
        print("\n🏆 САМЫЙ ПОПУЛЯРНЫЙ АРОМАТ:")
        print("=" * 50)
        print(f"📈 За последние 6 месяцев:")
        print(f"   {most_popular_last['Бренд']} - {most_popular_last['Аромат']}")
        print(f"   🏭 {most_popular_last['Фабрика']} | ⭐ {most_popular_last['Качество']}")
        print(f"   📊 Популярность: {most_popular_last['TOP LAST']:.2f}%")
        
        print(f"\n📈 За все время:")
        print(f"   {most_popular_all['Бренд']} - {most_popular_all['Аромат']}")
        print(f"   🏭 {most_popular_all['Фабрика']} | ⭐ {most_popular_all['Качество']}")
        print(f"   📊 Популярность: {most_popular_all['TOP ALL']:.2f}%")
        
    except Exception as e:
        print(f"❌ Ошибка при анализе: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    analyze_popularity() 