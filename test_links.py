import sys
import os

# Добавляем текущую директорию в путь
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Импортируем функцию загрузки данных
import importlib.util
spec = importlib.util.spec_from_file_location("module", "1.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
load_excel_data = module.load_excel_data

def test_links():
    print("🔍 Тестируем загрузку данных и ссылок...")
    
    try:
        # Загружаем данные
        df = load_excel_data()
        
        if df is None or df.empty:
            print("❌ Данные не загружены")
            return
        
        print(f"✅ Данные загружены: {len(df)} строк")
        print(f"📋 Столбцы: {list(df.columns)}")
        
        # Проверяем столбец "Ссылка"
        if 'Ссылка' in df.columns:
            print(f"\n🔗 Проверяем ссылки:")
            
            # Показываем первые 10 строк с ссылками
            for idx, row in df.head(10).iterrows():
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
    test_links() 