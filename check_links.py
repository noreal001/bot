import pandas as pd
import requests
import io
import urllib3

# Отключаем SSL предупреждения
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# URL Google Sheets
GOOGLE_SHEETS_URL = "https://docs.google.com/spreadsheets/d/1J70LlZwh6g7JOryDG2br-weQrYfv6zTc/export?format=xlsx"

def check_links_in_excel():
    try:
        print("🔍 Загружаем данные из Google Sheets...")
        
        # Загружаем данные
        session = requests.Session()
        session.verify = False
        response = session.get(GOOGLE_SHEETS_URL, timeout=30)
        response.raise_for_status()
        
        # Читаем Excel
        df = pd.read_excel(io.BytesIO(response.content), header=2, skiprows=[3])
        
        print(f"📊 Всего строк: {len(df)}")
        print(f"📊 Всего столбцов: {len(df.columns)}")
        
        # Показываем названия столбцов
        print(f"\n📋 Названия столбцов:")
        for i, col in enumerate(df.columns):
            print(f"{i}: {col}")
        
        # Ищем столбец "Ссылка"
        link_column = None
        for i, col in enumerate(df.columns):
            if 'ссылка' in str(col).lower():
                link_column = i
                print(f"\n✅ Найден столбец 'Ссылка': {col} (индекс {i})")
                break
        
        if link_column is None:
            print("\n❌ Столбец 'Ссылка' не найден!")
            return
        
        # Проверяем ссылки в первых 20 строках
        print(f"\n🔗 Проверяем ссылки в первых 20 строках:")
        valid_links = 0
        total_checked = 0
        
        for idx, row in df.head(20).iterrows():
            brand = row.get('Бренд', 'N/A')
            aroma = row.get('Аромат', 'N/A')
            link = row.iloc[link_column] if link_column < len(row) else None
            
            total_checked += 1
            
            if pd.notna(link) and str(link).strip() and str(link).strip().startswith('http'):
                print(f"✅ {brand} - {aroma}: {link}")
                valid_links += 1
            elif pd.notna(link) and str(link).strip():
                print(f"⚠️  {brand} - {aroma}: {link} (не http)")
            else:
                print(f"❌ {brand} - {aroma}: ссылка отсутствует")
        
        print(f"\n📈 Статистика:")
        print(f"Проверено строк: {total_checked}")
        print(f"Валидных ссылок: {valid_links}")
        print(f"Процент валидных: {(valid_links/total_checked)*100:.1f}%")
        
        # Проверяем конкретные ароматы
        print(f"\n🔍 Ищем конкретные ароматы:")
        search_aromas = ['Escada Moon Sparkle', 'Escada Joyful', 'Tom Ford', 'Nasomatto']
        
        for search_aroma in search_aromas:
            for idx, row in df.iterrows():
                brand = row.get('Бренд', '')
                aroma = row.get('Аромат', '')
                link = row.iloc[link_column] if link_column < len(row) else None
                
                if search_aroma.lower() in f"{brand} {aroma}".lower():
                    print(f"🎯 Найден: {brand} - {aroma}")
                    if pd.notna(link) and str(link).strip() and str(link).strip().startswith('http'):
                        print(f"   ✅ Ссылка: {link}")
                    else:
                        print(f"   ❌ Ссылка: {link}")
                    break
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")

if __name__ == "__main__":
    check_links_in_excel() 