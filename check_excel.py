import pandas as pd
import requests
import io
import urllib3

# Отключаем SSL предупреждения
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# URL Google Sheets (замените на ваш)
GOOGLE_SHEETS_URL = "https://docs.google.com/spreadsheets/d/1J70LlZwh6g7JOryDG2br-weQrYfv6zTc/export?format=xlsx"

def check_excel_data():
    try:
        print("Загружаем данные из Google Sheets...")
        
        # Загружаем данные
        session = requests.Session()
        session.verify = False
        response = session.get(GOOGLE_SHEETS_URL, timeout=30)
        response.raise_for_status()
        
        # Читаем Excel
        df = pd.read_excel(io.BytesIO(response.content), header=2, skiprows=[3])
        
        print(f"Всего строк: {len(df)}")
        print(f"Всего столбцов: {len(df.columns)}")
        
        # Показываем первые 10 строк
        print("\nПервые 10 строк:")
        print(df.head(10))
        
        # Ищем Genetic Bliss
        print("\nИщем 'Genetic Bliss' или 'genetic':")
        for idx, row in df.iterrows():
            for col_idx, value in enumerate(row):
                if pd.notna(value) and 'genetic' in str(value).lower():
                    print(f"Строка {idx+1}, Столбец {col_idx}: {value}")
                    if col_idx == 1:  # Столбец B
                        print(f"  Ссылка в столбце B: {value}")
        
        # Проверяем столбец B (ссылки)
        print(f"\nСтолбец B (ссылки) - первые 10 значений:")
        if len(df.columns) > 1:
            for idx, value in enumerate(df.iloc[:10, 1]):
                print(f"Строка {idx+1}: {value}")
        
    except Exception as e:
        print(f"Ошибка: {e}")

if __name__ == "__main__":
    check_excel_data() 