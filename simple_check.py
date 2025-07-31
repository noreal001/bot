import pandas as pd
import requests
import io
import urllib3

# Отключаем SSL предупреждения
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def check_google_sheets():
    try:
        print("🔍 Проверяем Google Таблицы...")
        
        # URL Google Sheets
        url = "https://docs.google.com/spreadsheets/d/1J70LlZwh6g7JOryDG2br-weQrYfv6zTc/export?format=xlsx"
        
        # Загружаем данные
        session = requests.Session()
        session.verify = False
        response = session.get(url, timeout=30)
        
        if response.status_code != 200:
            print(f"❌ Ошибка доступа: {response.status_code}")
            return
        
        # Читаем Excel
        df = pd.read_excel(io.BytesIO(response.content), header=2, skiprows=[3])
        
        print(f"✅ Данные загружены: {len(df)} строк, {len(df.columns)} столбцов")
        
        # Показываем названия столбцов
        print(f"\n📋 Столбцы:")
        for i, col in enumerate(df.columns):
            print(f"{i}: {col}")
        
        # Ищем столбец со ссылками
        link_col = None
        for i, col in enumerate(df.columns):
            if 'ссылка' in str(col).lower():
                link_col = i
                print(f"\n🔗 Найден столбец ссылок: {col} (индекс {i})")
                break
        
        if link_col is None:
            print("\n❌ Столбец со ссылками не найден!")
            return
        
        # Проверяем ссылки в первых 10 строках
        print(f"\n🔍 Проверяем ссылки:")
        valid_links = 0
        
        for idx, row in df.head(10).iterrows():
            brand = row.iloc[5] if len(row) > 5 else 'N/A'  # Столбец 5 - Бренд
            aroma = row.iloc[6] if len(row) > 6 else 'N/A'  # Столбец 6 - Аромат
            link = row.iloc[link_col] if link_col < len(row) else None
            
            if pd.notna(link) and str(link).strip() and str(link).strip().startswith('http'):
                print(f"✅ {brand} - {aroma}: {link}")
                valid_links += 1
            elif pd.notna(link) and str(link).strip():
                print(f"⚠️  {brand} - {aroma}: {link} (не http)")
            else:
                print(f"❌ {brand} - {aroma}: ссылка отсутствует")
        
        print(f"\n📊 Статистика: {valid_links}/10 валидных ссылок")
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")

if __name__ == "__main__":
    check_google_sheets() 