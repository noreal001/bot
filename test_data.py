#!/usr/bin/env python3

import sys
import os
import importlib.util

# Загружаем модуль 1.py
spec = importlib.util.spec_from_file_location("module", "1.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

def test_data_loading():
    try:
        print("🔍 Тестируем загрузку данных...")
        
        # Загружаем данные
        data = module.load_excel_data()
        
        if data is None:
            print("❌ Данные не загружены")
            return
        
        print(f"✅ Данные загружены: {len(data)} строк")
        print(f"📋 Столбцы: {list(data.columns)}")
        
        # Проверяем столбец "Ссылка"
        if 'Ссылка' in data.columns:
            print(f"\n🔗 Проверяем ссылки:")
            
            # Показываем первые 5 строк с ссылками
            for idx, row in data.head(5).iterrows():
                brand = row.get('Бренд', 'N/A')
                aroma = row.get('Аромат', 'N/A')
                link = row.get('Ссылка', '')
                
                if pd.notna(link) and str(link).strip() and str(link).strip().startswith('http'):
                    print(f"✅ {brand} - {aroma}: {link}")
                elif pd.notna(link) and str(link).strip():
                    print(f"⚠️  {brand} - {aroma}: {link} (не http)")
                else:
                    print(f"❌ {brand} - {aroma}: ссылка отсутствует")
        else:
            print("❌ Столбец 'Ссылка' не найден в данных")
            
    except Exception as e:
        print(f"❌ Ошибка: {e}")

if __name__ == "__main__":
    test_data_loading() 