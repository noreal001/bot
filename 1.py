import logging
import sqlite3
import re
import requests
import nest_asyncio
import random
import os
import traceback
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import PlainTextResponse, JSONResponse
from pydantic import BaseModel
import aiohttp
import asyncio
import httpx
import sys
import uvicorn
from datetime import datetime, timedelta
import threading
import time
import pandas as pd
from openpyxl import load_workbook

print('=== [LOG] 1.py импортирован ===')
nest_asyncio.apply()

# --- Работа с Excel данными ---
GOOGLE_SHEETS_URL = "https://docs.google.com/spreadsheets/d/1rvb3QdanuukCyXnoQZZxz7HF6aJXm2de/export?format=xlsx&gid=1870986273"
excel_data = None

def load_excel_data():
    """Загружает данные из Google Sheets"""
    global excel_data
    try:
        logger.info("Loading data from Google Sheets...")
        
        import requests
        import io
        import ssl
        from openpyxl import load_workbook
        
        # Отключаем проверку SSL для Google Sheets
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        
        # Загружаем данные через requests
        session = requests.Session()
        session.verify = False  # Отключаем SSL проверку
        
        response = session.get(GOOGLE_SHEETS_URL, timeout=30)
        response.raise_for_status()
        
        # Сохраняем во временный файл для извлечения гиперссылок
        import tempfile
        import os
        
        with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp_file:
            tmp_file.write(response.content)
            tmp_file_path = tmp_file.name
        
        try:
            # Загружаем с помощью openpyxl для извлечения гиперссылок
            wb = load_workbook(tmp_file_path)
            ws = wb.active
            
            # Извлекаем гиперссылки из столбца B
            hyperlinks = {}
            for row in range(4, ws.max_row + 1):  # Начинаем с 4-й строки
                cell = ws.cell(row=row, column=2)  # Столбец B
                if cell.hyperlink:
                    hyperlinks[row] = cell.hyperlink.target
                    logger.info(f"Найдена гиперссылка в строке {row}: {cell.hyperlink.target}")
            
            wb.close()
            
        finally:
            # Удаляем временный файл
            os.unlink(tmp_file_path)
        
        # Читаем Excel из памяти через pandas
        df = pd.read_excel(io.BytesIO(response.content), header=2, skiprows=[3])
        
        # Очищаем данные
        df = df.dropna(how='all')
        
        # Фильтруем по наличию бренда и аромата (столбцы 5 и 6)
        if len(df.columns) > 6:
            df = df[df.iloc[:, 5].notna() & df.iloc[:, 6].notna()]
        else:
            logger.warning("Not enough columns in Google Sheets data")
            raise Exception("Invalid data structure")
        
        # Переименовываем столбцы для удобства (новая структура таблицы)
        if len(df.columns) >= 13:
            column_mapping = {
                df.columns[1]: 'Ссылка',     # Столбец B (ссылка на аромат)
                df.columns[5]: 'Бренд',      # Столбец 5
                df.columns[6]: 'Аромат',     # Столбец 6
                df.columns[7]: 'Пол',        # Столбец 7
                df.columns[8]: 'Фабрика',    # Столбец 8
                df.columns[9]: 'Качество',   # Столбец 9 (уже в формате TOP/Q1/Q2)
                df.columns[10]: '30 GR',     # Столбец 10
                df.columns[11]: '50 GR',     # Столбец 11
                df.columns[12]: '500 GR',    # Столбец 12
                df.columns[13]: '1 KG',      # Столбец 13
            }
            
            # Добавляем столбцы для нот и страны (если они есть)
            if len(df.columns) > 14:
                column_mapping[df.columns[14]] = 'Страна'
            if len(df.columns) > 15:
                column_mapping[df.columns[15]] = 'Верхние ноты'
            if len(df.columns) > 16:
                column_mapping[df.columns[16]] = 'Средние ноты'
            if len(df.columns) > 17:
                column_mapping[df.columns[17]] = 'Базовые ноты'
            
            # Добавляем столбцы TOP LAST и TOP ALL (сдвигаем индексы из-за добавленных столбцов)
            if len(df.columns) > 18:
                column_mapping[df.columns[18]] = 'TOP LAST'
            if len(df.columns) > 19:
                column_mapping[df.columns[19]] = 'TOP ALL'
            
            df = df.rename(columns=column_mapping)
        else:
            logger.warning(f"Not enough columns: {len(df.columns)}")
            raise Exception("Invalid column structure")
        
        # Добавляем гиперссылки к данным
        if hyperlinks:
            # Создаем столбец с гиперссылками
            df['Гиперссылка'] = ''
            for idx, row in df.iterrows():
                # Индекс строки в Excel (начиная с 4-й строки)
                excel_row = idx + 4
                if excel_row in hyperlinks:
                    df.at[idx, 'Гиперссылка'] = hyperlinks[excel_row]
                    logger.info(f"Добавлена гиперссылка для строки {idx}: {hyperlinks[excel_row]}")
        
        # Конвертируем типы данных
        price_columns = ['30 GR', '50 GR', '500 GR', '1 KG']
        for col in price_columns:
            if col in df.columns:
                # Убираем символы валюты и конвертируем в числа
                df[col] = df[col].astype(str).str.replace('₽', '').str.replace(' ', '').str.replace('nan', '')
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # Конвертируем столбцы популярности (данные уже в процентах)
        if 'TOP LAST' in df.columns:
            df['TOP LAST'] = pd.to_numeric(df['TOP LAST'], errors='coerce')
        
        if 'TOP ALL' in df.columns:
            df['TOP ALL'] = pd.to_numeric(df['TOP ALL'], errors='coerce')
        
        # Очищаем пробелы в качестве
        if 'Качество' in df.columns:
            df['Качество'] = df['Качество'].astype(str).str.strip()
        
        # Очищаем от строк без данных
        df = df[df['Бренд'].notna() & df['Аромат'].notna()]
        
        excel_data = df
        logger.info(f"Google Sheets data loaded: {len(df)} products")
        return df
        
    except Exception as e:
        logger.error(f"Failed to load Google Sheets data: {e}")
        # Fallback к локальному файлу
        try:
            logger.info("Falling back to local Excel file...")
            df = pd.read_excel("1.xlsx", header=2, skiprows=[3])
            df = df.dropna(how='all')
            df = df[~df['Бренд'].astype(str).str.contains('Column', na=False)]
            df = df[df['Бренд'].notna()]
            
            price_columns = ['30 GR', '50 GR', '500 GR', '1 KG', '5 KG', '10 KG']
            for col in price_columns:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            
            excel_data = df
            logger.info(f"Local Excel data loaded: {len(df)} products")
            return df
        except Exception as e2:
            logger.error(f"Failed to load local Excel data: {e2}")
            return None

def normalize_name(name):
    return str(name).lower().replace('-', '').replace("'", '').replace(' ', '')

def search_products(query, limit=None):
    global excel_data
    if excel_data is None:
        return []
    query_norm = normalize_name(query)
    # Точное совпадение по нормализованному названию
    exact_mask = excel_data['Аромат'].astype(str).apply(normalize_name) == query_norm
    if exact_mask.any():
        results = excel_data[exact_mask]
    else:
        # Частичное совпадение по нормализованному названию
        mask = excel_data['Аромат'].astype(str).apply(normalize_name).str.contains(query_norm, na=False)
        results = excel_data[mask]
    if limit:
        results = results.head(limit)
    return results.to_dict('records')

def calculate_price(product, volume_ml):
    """Рассчитывает цену за указанный объем"""
    try:
        volume_ml = float(volume_ml)
        
        # Определяем ценовую категорию согласно прайс-листу
        if volume_ml <= 49:
            price_per_ml = product.get('30 GR', 0)
            tier = '30-49 мл'
        elif volume_ml <= 499:
            price_per_ml = product.get('50 GR', 0)
            tier = '50-499 мл'
        elif volume_ml <= 999:
            price_per_ml = product.get('500 GR', 0)
            tier = '500-999 мл'
        else:
            price_per_ml = product.get('1 KG', 0)
            tier = '1000+ мл'
        
        if price_per_ml and not pd.isna(price_per_ml):
            total_price = float(price_per_ml) * volume_ml
            return {
                'volume_ml': volume_ml,
                'price_per_ml': float(price_per_ml),
                'total_price': total_price,
                'tier': tier,
                'currency': 'руб'
            }
    except (ValueError, TypeError):
        pass
    
    return None

def get_quality_name(quality_code):
    """Конвертирует код качества в название"""
    quality_map = {
        6: 'TOP',
        5: 'Q1', 
        4: 'Q2'
    }
    return quality_map.get(quality_code, f'{quality_code}')

def get_quality_description(quality_code):
    """Получает подробное описание качества"""
    quality_desc_map = {
        6: 'TOP (высшее качество)',
        5: 'Q1 (отличное качество)', 
        4: 'Q2 (хорошее качество)'
    }
    return quality_desc_map.get(quality_code, f'Качество {quality_code}')

def get_top_products(factory=None, quality=None, sort_by='TOP LAST', limit=None):
    """Получает топ продукты по статистике (без лимита по умолчанию)"""
    global excel_data
    if excel_data is None:
        return []
    df = excel_data.copy()
    # Фильтры
    if factory:
        df = df[df['Фабрика'].str.upper() == factory.upper()]
    if quality:
        df = df[df['Качество'] == quality]
    # Сортировка по популярности
    sort_column = 'TOP LAST' if sort_by == 'TOP LAST' else 'TOP ALL'
    df = df.sort_values(sort_column, ascending=False, na_position='last')
    if limit:
        df = df.head(limit)
    return df.to_dict('records')

def format_product_info(product, include_prices=True, for_chatgpt=True):
    """Форматирует информацию о продукте с улучшенной структурой"""
    return format_aroma_response_improved(product, include_prices)

def get_aroma_variants_stats(aroma_name):
    """Возвращает статистику по вариантам аромата (фабрика+качество)"""
    global excel_data
    if excel_data is None:
        return []
    mask = excel_data['Аромат'].str.lower().str.strip() == aroma_name.lower().strip()
    variants = excel_data[mask]
    if variants.empty:
        return []
    total_popularity = variants['TOP LAST'].sum()
    if total_popularity == 0:
        return []
    result = []
    for _, row in variants.iterrows():
        factory = row['Фабрика']
        quality = row['Качество']
        popularity = row['TOP LAST']
        percent = (popularity / total_popularity) * 100 if total_popularity else 0
        result.append({
            'factory': factory,
            'quality': quality,
            'popularity_percent': percent,
            'popularity_raw': popularity
        })
    return result

async def get_excel_context_for_chatgpt(query="", volume_ml=None, show_variants_stats=False):
    """Создает СТРОГО СТРУКТУРИРОВАННЫЙ контекст из Excel данных для ChatGPT, с расчетом цен и статистикой вариантов"""
    try:
        MAX_PRODUCTS_FOR_LLM = 20
        context = "\n=== АКТУАЛЬНЫЕ ДАННЫЕ ИЗ ПРАЙС-ЛИСТА ===\n"
        context += "ВНИМАНИЕ: Используй ТОЛЬКО эти цены и проценты, не придумывай свои значения!\n"
        PRAIS_URL = "http://clck.ru/jrimp"
        def format_prices(product):
            prices = []
            price_map = [
                ("30 GR", 30),
                ("50 GR", 50),
                ("500 GR", 500),
                ("1 KG", 1000)
            ]
            for col, vol in price_map:
                price_per_g = product.get(col)
                if price_per_g and not pd.isna(price_per_g):
                    total = int(price_per_g * vol)
                    prices.append(f"💧{vol} грамм = {total}₽ ({price_per_g}₽ - за 1 грамм)")
                else:
                    prices.append(f"• {vol} мл — Стоимость недоступна")
            return "\n".join(prices)
        def get_top_variant(variants, key):
            if not variants:
                return None
            top = max(variants, key=key)
            return top
        def get_rank(product, all_products, key):
            sorted_products = sorted(all_products, key=key, reverse=True)
            for idx, p in enumerate(sorted_products, 1):
                if p['Бренд'] == product['Бренд'] and p['Аромат'] == product['Аромат'] and p['Фабрика'] == product['Фабрика'] and p['Качество'] == product['Качество']:
                    return idx
            return None
        # Поиск по запросу
        if query:
            products = search_products(query, limit=None)
            total_found = len(products)
            if total_found > MAX_PRODUCTS_FOR_LLM:
                context += f"\n⚠️ Найдено {total_found} ароматов, показываю только первые {MAX_PRODUCTS_FOR_LLM}. Уточните запрос для более точного результата.\n"
                products = products[:MAX_PRODUCTS_FOR_LLM]
            if products:
                all_products_6m = get_top_products(sort_by='TOP LAST', limit=None)
                all_products_all = get_top_products(sort_by='TOP ALL', limit=None)
                # Группируем варианты по названию аромата
                aroma_name = products[0].get('Аромат', '')
                variants = [p for p in products if p.get('Аромат', '').strip().lower() == aroma_name.strip().lower()]
                show_variants_block = len(variants) > 1
                sum_last = sum(p.get('TOP LAST', 0) for p in variants)
                sum_all = sum(p.get('TOP ALL', 0) for p in variants)
                top_variant = get_top_variant(variants, lambda p: p.get('TOP LAST', 0))
                for i, product in enumerate(products, 1):
                    brand = product.get('Бренд', 'N/A')
                    aroma_raw = product.get('Аромат', 'N/A')
                    aroma = format_aroma_name(aroma_raw)
                    factory = product.get('Фабрика', 'N/A')
                    quality = product.get('Качество', 'N/A')
                    popularity_last = product.get('TOP LAST', 0)
                    popularity_all = product.get('TOP ALL', 0)
                    rank_6m = get_rank(product, all_products_6m, lambda p: p.get('TOP LAST', 0))
                    rank_all = get_rank(product, all_products_all, lambda p: p.get('TOP ALL', 0))
                                    # Используем гиперссылку из прайса, если она есть
                    hyperlink = product.get('Гиперссылка', '')
                    if hyperlink and not pd.isna(hyperlink) and str(hyperlink).strip() and str(hyperlink).strip().startswith('http'):
                        aroma_url = str(hyperlink).strip()
                        logger.info(f"Используем гиперссылку из прайса: {aroma_url}")
                    else:
                        # Проверяем обычную ссылку из прайса
                        link = product.get('Ссылка', '')
                        logger.info(f"Ссылка для {brand} - {aroma}: {link}")
                        if link and not pd.isna(link) and str(link).strip() and str(link).strip().startswith('http'):
                            aroma_url = str(link).strip()
                            logger.info(f"Используем ссылку из прайса: {aroma_url}")
                        else:
                            # Не генерируем ссылку, если её нет в прайсе
                            aroma_url = ""
                            logger.info(f"Ссылка из прайса не найдена для {brand} - {aroma}")
                    
                    if brand != 'N/A' and aroma != 'N/A':
                        if aroma_url and aroma_url.startswith('http'):
                            context += f"✨ <a href='{aroma_url}'>{brand} - {aroma}</a>\n\n"
                        else:
                            context += f"✨{brand} - {aroma}\n\n"
                    else:
                        context += f"✨{brand} - {aroma}\n\n"
                    
                    # Добавляем популярность
                    context += f"⚡️ TOP LAST: {popularity_last:.0f}% (№{rank_6m})\n"
                    context += f"🚀 TOP ALL: {popularity_all:.0f}% (№{rank_all})\n"
                    
                    # Добавляем пустую строку после популярности
                    context += "\n"
                    
                    # Добавляем TOP VERSION (процентное соотношение по фабрикам и качеству)
                    aroma_name = product.get('Аромат', '')
                    if aroma_name and not pd.isna(aroma_name):
                        all_versions = [p for p in excel_data if p.get('Аромат', '').strip().lower() == aroma_name.strip().lower()]
                        if len(all_versions) > 1:
                            total_popularity = sum(p.get('TOP LAST', 0) for p in all_versions)
                            if total_popularity > 0:
                                # Группируем по фабрикам и качеству
                                factory_stats = {}
                                for version in all_versions:
                                    factory = version.get('Фабрика', '')
                                    quality = version.get('Качество', '')
                                    popularity = version.get('TOP LAST', 0)
                                    key = f"{factory} {quality}"
                                    if key not in factory_stats:
                                        factory_stats[key] = 0
                                    factory_stats[key] += popularity
                                
                                # Формируем строку с процентами
                                version_percents = []
                                for factory_key, popularity in factory_stats.items():
                                    percent = (popularity / total_popularity) * 100
                                    version_percents.append(f"{factory_key}: {percent:.1f}%")
                    
                    if version_percents:
                        context += f"   ♾️ VERSION: {' | '.join(version_percents)}\n"
                    
                    # Добавляем информацию о нотах и стране
                    top_notes = product.get('Верхние ноты', '')
                    middle_notes = product.get('Средние ноты', '')
                    base_notes = product.get('Базовые ноты', '')
                    country = product.get('Страна', '')
                    
                    # Если ноты или страна не указаны в прайсе, пробуем получить через API
                    if (not top_notes or pd.isna(top_notes) or not str(top_notes).strip()) or \
                       (not country or pd.isna(country) or not str(country).strip()):
                        try:
                            api_data = await get_notes_from_api(f"{brand} {aroma}")
                            if api_data:
                                if not top_notes or pd.isna(top_notes) or not str(top_notes).strip():
                                    top_notes = api_data.get("top_notes", "")
                                if not middle_notes or pd.isna(middle_notes) or not str(middle_notes).strip():
                                    middle_notes = api_data.get("middle_notes", "")
                                if not base_notes or pd.isna(base_notes) or not str(base_notes).strip():
                                    base_notes = api_data.get("base_notes", "")
                                if not country or pd.isna(country) or not str(country).strip():
                                    country = api_data.get("country", "")
                                # Если ссылки нет в прайсе, берем из API
                                if not aroma_url or aroma_url == "":
                                    api_link = api_data.get("link", "")
                                    if api_link and api_link.startswith('http'):
                                        aroma_url = api_link
                        except Exception as e:
                            logger.error(f"Error getting API data: {e}")
                    
                    # Отображаем ноты
                    if top_notes and not pd.isna(top_notes) and str(top_notes).strip():
                        context += f"🌱 Верхние ноты: {str(top_notes).strip()}\n"
                    else:
                        context += f"🌱 Верхние ноты: Не указаны\n"
                    if middle_notes and not pd.isna(middle_notes) and str(middle_notes).strip():
                        context += f"🌿 Средние ноты: {str(middle_notes).strip()}\n"
                    else:
                        context += f"🌿 Средние ноты: Не указаны\n"
                    if base_notes and not pd.isna(base_notes) and str(base_notes).strip():
                        context += f"🍃 Базовые ноты: {str(base_notes).strip()}\n"
                    else:
                        context += f"🍃 Базовые ноты: Не указаны\n"
                    
                    # Добавляем пустую строку после нот
                    context += "\n"
                    
                    # Отображаем бренд и страну
                    context += f"® Бренд: {brand}\n"
                    logger.info(f"Страна для {brand} - {aroma}: '{country}'")
                    country_emoji = get_country_emoji(country)
                    logger.info(f"Эмоджи для страны '{country}': {country_emoji}")
                    if country and not pd.isna(country) and str(country).strip():
                        context += f"{country_emoji} Страна: {str(country).strip()}\n"
                    else:
                        context += f"{country_emoji} Страна: Не указана\n"
                    
                    # Добавляем пустую строку после страны
                    context += "\n"
                    # Статистика по вариантам (если есть варианты)
                    if show_variants_block and i == 1:
                        context += f"📊 Статистика по вариантам аромата '{aroma_name}':\n"
                        for v in variants:
                            percent_last = (v.get('TOP LAST', 0) / sum_last * 100) if sum_last else 0
                            percent_all = (v.get('TOP ALL', 0) / sum_all * 100) if sum_all else 0
                            mark = " (самый популярный)" if top_variant and v['Фабрика'] == top_variant['Фабрика'] and v['Качество'] == top_variant['Качество'] else ""
                            context += f"- {v['Фабрика']} ({v['Качество']}): {percent_last:.1f}% за 6 мес, {percent_all:.1f}% за всё время{mark}\n"
                    # Отступ перед стоимостью
                    context += "\n"
                    context += f"💵 Стоимость:\n{format_prices(product)}\n\n"
        # ТОП-ароматы (весь прайс, но с лимитом)
        all_products_6m = get_top_products(sort_by='TOP LAST', limit=MAX_PRODUCTS_FOR_LLM)
        all_products_all = get_top_products(sort_by='TOP ALL', limit=MAX_PRODUCTS_FOR_LLM)
        if all_products_6m:
            context += f"\n🔥 ТОП-{MAX_PRODUCTS_FOR_LLM} ПОПУЛЯРНЫХ АРОМАТОВ (последние 6 месяцев):\n"
            for i, product in enumerate(all_products_6m, 1):
                brand = product.get('Бренд', 'N/A')
                aroma = product.get('Аромат', 'N/A')
                factory = product.get('Фабрика', 'N/A')
                quality = product.get('Качество', 'N/A')
                popularity_last = product.get('TOP LAST', 0)
                popularity_all = product.get('TOP ALL', 0)
                rank_6m = i
                rank_all = get_rank(product, all_products_all, lambda p: p.get('TOP ALL', 0))
                # Используем ссылку из прайса, если она есть и валидна
                link = product.get('Ссылка', '')
                if link and not pd.isna(link) and str(link).strip() and str(link).strip().startswith('http'):
                    aroma_url = str(link).strip()
                else:
                    # Не генерируем ссылку, если её нет в прайсе
                    aroma_url = ""
                if brand != 'N/A' and aroma != 'N/A':
                    context += f"{i}. <a href='{aroma_url}'>{brand} - {aroma}</a>\n   🏭 {factory} ({quality})\n   📈 Популярность (6 мес): {popularity_last:.2f}% (№{rank_6m})\n   📊 Популярность (всё время): {popularity_all:.2f}% (№{rank_all})\n\n💰 Стоимость:\n{format_prices(product)}\n\n"
                else:
                    context += f"{i}. {brand} - {aroma}\n   🏭 {factory} ({quality})\n   �� Популярность (6 мес): {popularity_last:.2f}% (№{rank_6m})\n   📊 Популярность (всё время): {popularity_all:.2f}% (№{rank_all})\n\n💰 Стоимость:\n{format_prices(product)}\n\n"
        # Информация о фабриках
        context += "\n🏭 ДОСТУПНЫЕ ФАБРИКИ: EPS, LUZI, SELUZ, UNKNOWN\n"
        context += "⭐ КАЧЕСТВА: TOP > Q1 > Q2\n"
        context += "\n💰 ЦЕНОВЫЕ КАТЕГОРИИ:\n"
        context += "• 30-49 мл: цена из столбца '30 GR'\n"
        context += "• 50-499 мл: цена из столбца '50 GR'\n"
        context += "• 500-999 мл: цена из столбца '500 GR'\n"
        context += "• 1000+ мл: цена из столбца '1 KG'\n"
        return context
    except Exception as e:
        logger.error(f"Error creating Excel context: {e}")
        return "\n❌ Ошибка загрузки актуальных данных из прайс-листа\n"

# --- База данных SQLite ---
DB_NAME = "bot_users.db"

def init_database():
    """Инициализация базы данных"""
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        # Создаем таблицу пользователей
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                chat_id INTEGER NOT NULL,
                first_name TEXT,
                username TEXT,
                first_start_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_activity DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_weekly_message DATETIME,
                is_active BOOLEAN DEFAULT 1
            )
        ''')
        
        conn.commit()
        conn.close()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")

def add_user_to_db(user_id, chat_id, first_name=None, username=None):
    """Добавляет пользователя в базу данных или обновляет последнюю активность"""
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        # Проверяем, существует ли пользователь
        cursor.execute('SELECT user_id FROM users WHERE user_id = ?', (user_id,))
        exists = cursor.fetchone()
        
        if exists:
            # Обновляем последнюю активность
            cursor.execute('''
                UPDATE users 
                SET last_activity = CURRENT_TIMESTAMP, is_active = 1, chat_id = ?
                WHERE user_id = ?
            ''', (chat_id, user_id))
            logger.info(f"Updated user activity: {user_id}")
        else:
            # Добавляем нового пользователя
            cursor.execute('''
                INSERT INTO users (user_id, chat_id, first_name, username, first_start_date, last_activity)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ''', (user_id, chat_id, first_name, username))
            logger.info(f"Added new user to database: {user_id}")
        
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Failed to add/update user in database: {e}")

def get_users_for_weekly_message():
    """Получает пользователей, которым нужно отправить еженедельное сообщение"""
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        # Получаем пользователей, которым не отправляли сообщение больше недели
        week_ago = datetime.now() - timedelta(days=7)
        cursor.execute('''
            SELECT user_id, chat_id, first_name FROM users 
            WHERE is_active = 1 AND (
                last_weekly_message IS NULL OR 
                last_weekly_message < ?
            )
        ''', (week_ago,))
        
        users = cursor.fetchall()
        conn.close()
        return users
    except Exception as e:
        logger.error(f"Failed to get users for weekly message: {e}")
        return []

def update_weekly_message_sent(user_id):
    """Обновляет время отправки еженедельного сообщения"""
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE users 
            SET last_weekly_message = CURRENT_TIMESTAMP
            WHERE user_id = ?
        ''', (user_id,))
        
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Failed to update weekly message timestamp: {e}")

def deactivate_user(user_id):
    """Деактивирует пользователя (например, если заблокировал бота)"""
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE users 
            SET is_active = 0
            WHERE user_id = ?
        ''', (user_id,))
        
        conn.commit()
        conn.close()
        logger.info(f"Deactivated user: {user_id}")
    except Exception as e:
        logger.error(f"Failed to deactivate user: {e}")

# --- Еженедельная рассылка ---
def get_weekly_message():
    """Генерирует случайное еженедельное сообщение от медвежонка"""
    messages = [
        "🐆 Привет! Я соскучилась, поговори со мной! Может расскажешь, какие ароматы тебя сейчас интересуют? ✨",
        "🐾 Пантера скучает! Давай пообщаемся? Хочу узнать, какие духи ты сейчас носишь! 💫",
        "🐆 Привет, дорогая! Я так по тебе соскучилась! Может поболтаем об ароматах? У меня столько новостей! ✨",
        "🐆 Пантериное сердечко скучает! Поговори со мной, расскажи, какие новые ароматы хочешь попробовать? 🌟",
        "🐾 Привет-привет! Твоя ароматная пантера скучает! Давай обсудим что-нибудь интересное про духи? 💎",
        "🐆 Соскучилась безумно! Хочется поболтать с тобой об ароматах! Может что-то новенькое ищешь? ✨",
        "🐾 Пантера грустит без общения! Давай поговорим? Расскажи, какое у тебя сейчас настроение и какой аромат подойдет! 🌟"
    ]
    return random.choice(messages)

async def send_weekly_messages():
    """Отправляет еженедельные сообщения пользователям"""
    logger.info("Starting weekly message sending...")
    users = get_users_for_weekly_message()
    
    if not users:
        logger.info("No users need weekly messages")
        return
    
    sent_count = 0
    failed_count = 0
    
    for user_id, chat_id, first_name in users:
        try:
            message = get_weekly_message()
            success = await telegram_send_message(chat_id, message)
            
            if success:
                update_weekly_message_sent(user_id)
                sent_count += 1
                logger.info(f"Weekly message sent to user {user_id}")
            else:
                failed_count += 1
                # Возможно пользователь заблокировал бота
                logger.warning(f"Failed to send weekly message to user {user_id}")
                
            # Пауза между отправками, чтобы не нарушить лимиты API
            await asyncio.sleep(1)
            
        except Exception as e:
            failed_count += 1
            logger.error(f"Error sending weekly message to user {user_id}: {e}")
            # Если ошибка 403 (Forbidden), деактивируем пользователя
            if "403" in str(e) or "Forbidden" in str(e):
                deactivate_user(user_id)
    
    logger.info(f"Weekly messages completed: {sent_count} sent, {failed_count} failed")

def weekly_message_scheduler():
    """Планировщик еженедельных сообщений (работает в отдельном потоке)"""
    logger.info("Weekly message scheduler started")
    
    while True:
        try:
            # Проверяем каждый час
            time.sleep(3600)  # 1 hour
            
            # Отправляем сообщения в 7:00 по понедельникам
            now = datetime.now()
            if now.weekday() == 0 and now.hour == 7:  # Понедельник, 7:00
                # Создаем новый event loop для этого потока
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(send_weekly_messages())
                loop.close()
                
                # Спим еще час, чтобы не отправлять повторно
                time.sleep(3600)
                
        except Exception as e:
            logger.error(f"Error in weekly message scheduler: {e}")
            time.sleep(3600)  # При ошибке тоже ждем час

# Глобальная переменная для потока планировщика
scheduler_thread = None

def start_weekly_scheduler():
    """Запускает планировщик еженедельных сообщений"""
    global scheduler_thread
    if scheduler_thread is None or not scheduler_thread.is_alive():
        scheduler_thread = threading.Thread(target=weekly_message_scheduler, daemon=True)
        scheduler_thread.start()
        logger.info("Weekly scheduler thread started")

# --- Конфигурация ---
TOKEN = os.getenv('TOKEN')
BASE_WEBHOOK_URL = os.getenv('WEBHOOK_BASE_URL')
WEBHOOK_PATH = "/webhook/ai-bear-123456"
OPENAI_API = os.getenv('OPENAI_API_KEY')

# Проверяем переменные окружения с более мягкой обработкой
if not TOKEN:
    print("⚠️ WARNING: TOKEN environment variable not set!")
if not BASE_WEBHOOK_URL:
    print("⚠️ WARNING: WEBHOOK_BASE_URL environment variable not set!")
if not OPENAI_API:
    print("⚠️ WARNING: OPENAI_API_KEY environment variable not set!")
    print("⚠️ The bot will not be able to process AI requests without this key!")
    # Не прерываем выполнение, просто предупреждаем

# --- FastAPI app ---
print('=== [LOG] FastAPI app создаётся ===')
app = FastAPI()
print('=== [LOG] FastAPI app создан ===')

# Глобальный обработчик исключений
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Global exception handler: {exc}\n{traceback.format_exc()}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )

print(f'=== [LOG] WEBHOOK_PATH: {WEBHOOK_PATH} ===')

@app.on_event("startup")
async def log_routes():
    logger.info("=== ROUTES REGISTERED ===")
    for route in app.routes:
        logger.info(f"{route.path} [{','.join(route.methods or [])}]")
    logger.info(f"WEBHOOK_PATH: {WEBHOOK_PATH}")
    logger.info("=========================")

# --- ChatGPT и данные Bahur ---
def load_bahur_data():
    with open("bahur_data.txt", "r", encoding="utf-8") as f:
        return f.read()

BAHUR_DATA = load_bahur_data()

# --- Логирование ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Инициализация базы данных ---
init_database()

# --- Загрузка Excel данных ---
load_excel_data()

# --- Состояния пользователей для AI (in-memory, not persistent) ---
user_states = {}

# --- Постоянное хранение состояний пользователей ---
import json

def load_user_states():
    try:
        with open("user_states.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_user_states(states):
    with open("user_states.json", "w", encoding="utf-8") as f:
        json.dump(states, f, ensure_ascii=False, indent=2)

def set_user_state(user_id, state):
    global user_states
    if state:
        user_states[user_id] = state
    else:
        user_states.pop(user_id, None)
    save_user_states(user_states)

def get_user_state(user_id):
    global user_states
    return user_states.get(user_id)

# Загружаем состояния при запуске
user_states = load_user_states()

# --- Модели для FastAPI ---
class MessageModel(BaseModel):
    user_id: int
    text: str

class CallbackModel(BaseModel):
    user_id: int
    data: str

# --- Утилиты ---
def greet():
    return random.choice([
            "Привет! 🐾✨ Я AI-Пантера — эксперт по ароматам BAHUR! Спрашивай про любые духи, масла, доставку или цены — я найду всё в нашем каталоге! 🌟",
            "Здравствуй! 🐆💫 Готова помочь с выбором ароматов! Хочешь узнать про конкретные духи, масла, доставку или цены? Спрашивай — у меня есть полный каталог! ✨",
            "Привет, ароматный друг! 🐆✨ Я знаю всё о духах BAHUR! Спрашивай про любые ароматы, масла, доставку — найду в каталоге и расскажу подробно! 🌟",
            "Добро пожаловать! 🎯🐆 Я эксперт по ароматам BAHUR! Хочешь узнать про конкретные духи, масла, цены или доставку? Спрашивай — у меня есть все данные! ✨",
            "Привет! 🌟🐾 Я AI-Пантера — знаю всё о духах BAHUR! Спрашивай про любые ароматы, масла, доставку или цены — найду в каталоге и помогу с выбором! 💫"
    ])

def analyze_query_for_excel_data(question):
    """Анализирует запрос пользователя для определения нужности Excel данных"""
    question_lower = question.lower()
    
    # Ключевые слова, указывающие на необходимость ценовой информации
    price_keywords = ['цена', 'стоимость', 'стоит', 'сколько', 'руб', 'рубл', 'дорог', 'дешев', 'прайс']
    
    # Ключевые слова для поиска конкретных ароматов (более специфичные)
    search_keywords = ['найди аромат', 'покажи аромат', 'есть ли аромат', 'ищу аромат', 'поиск аромата', 'найди духи', 'покажи духи', 'есть ли духи', 'ищу духи', 'поиск духов', 'найди парфюм', 'покажи парфюм', 'есть ли парфюм', 'ищу парфюм', 'поиск парфюма']
    
    # Ключевые слова для статистики и рекомендаций
    stats_keywords = ['популярн', 'топ', 'лучш', 'рекоменд', 'посовет', 'модн', 'трендов']
    
    # Ключевые слова для фабрик и качества
    factory_keywords = ['eps', 'luzi', 'seluz', 'фабрика', 'качество', 'top', 'q1', 'q2']
    
    # Определяем, какие типы ключевых слов найдены
    found_price = [kw for kw in price_keywords if kw in question_lower]
    found_search = [kw for kw in search_keywords if kw in question_lower]
    found_stats = [kw for kw in stats_keywords if kw in question_lower]
    found_factory = [kw for kw in factory_keywords if kw in question_lower]
    
    # Проверяем на обычные разговоры (НЕ про ароматы)
    casual_keywords = ['как дела', 'как ты', 'привет', 'здравствуй', 'добрый день', 'добрый вечер', 'спасибо', 'хорошо', 'плохо', 'нормально', 'отлично', 'ужасно', 'погода', 'работа', 'семья', 'дети', 'муж', 'жена', 'друг', 'подруга', 'время', 'день', 'неделя', 'месяц', 'год', 'планы', 'мечты', 'цели', 'хобби', 'интересы', 'музыка', 'фильмы', 'книги', 'спорт', 'путешествия', 'еда', 'кухня', 'ресторан', 'кафе', 'магазин', 'покупки', 'деньги', 'бюджет', 'экономия', 'доходы', 'расходы', 'банк', 'кредит', 'ипотека', 'страхование', 'медицина', 'здоровье', 'врач', 'больница', 'лекарства', 'витамины', 'диета', 'похудение', 'фитнес', 'йога', 'бег', 'плавание', 'велосипед', 'лыжи', 'сноуборд', 'теннис', 'футбол', 'баскетбол', 'волейбол', 'хоккей', 'бокс', 'борьба', 'карате', 'дзюдо', 'самбо', 'аэробика', 'пилатес', 'стретчинг', 'массаж', 'сауна', 'баня', 'бассейн', 'спортзал', 'тренажеры', 'гантели', 'штанга', 'турник', 'брусья', 'скакалка', 'обруч', 'коврик', 'коврик для йоги', 'спортивная одежда', 'кроссовки', 'шорты', 'футболка', 'спортивные штаны', 'куртка', 'шапка', 'перчатки', 'носки', 'трусы', 'лифчик', 'бюстгальтер', 'трусики', 'плавки', 'купальник', 'парео', 'полотенце', 'мыло', 'шампунь', 'гель', 'дезодорант', 'зубная паста', 'щетка', 'расческа', 'зеркало', 'полотенце', 'простыня', 'одеяло', 'подушка', 'матрас', 'кровать', 'диван', 'кресло', 'стол', 'стул', 'шкаф', 'комод', 'тумбочка', 'лампа', 'светильник', 'люстра', 'торшер', 'настольная лампа', 'бра', 'спот', 'трек', 'подсветка', 'гирлянда', 'свечи', 'аромасвечи', 'благовония', 'ладан', 'мирра', 'сандал', 'пачули', 'лаванда', 'розмарин', 'мята', 'эвкалипт', 'чайное дерево', 'лимон', 'апельсин', 'грейпфрут', 'бергамот', 'лайм', 'мандарин', 'клементин', 'помело', 'кумкват', 'каламондин', 'юзу', 'судза', 'юдзу', 'каффир', 'макрут', 'кафрский лайм', 'кафрский лимон', 'кафрский апельсин', 'кафрский мандарин', 'кафрский клементин', 'кафрский помело', 'кафрский кумкват', 'кафрский каламондин', 'кафрский юзу', 'кафрский судза', 'кафрский юдзу', 'кафрский каффир', 'кафрский макрут', 'кафрский кафрский лайм', 'кафрский кафрский лимон', 'кафрский кафрский апельсин', 'кафрский кафрский мандарин', 'кафрский кафрский клементин', 'кафрский кафрский помело', 'кафрский кафрский кумкват', 'кафрский кафрский каламондин', 'кафрский кафрский юзу', 'кафрский кафрский судза', 'кафрский кафрский юдзу', 'кафрский кафрский каффир', 'кафрский кафрский макрут']
    
    # Если это обычный разговор - НЕ нужны Excel данные, но бот может аккуратно перевести на ароматы
    is_casual = any(keyword in question_lower for keyword in casual_keywords)
    if is_casual:
        return False, ""  # Не загружаем Excel данные, но бот может дружелюбно ответить
    
    needs_excel = any(keyword in question_lower for keyword in 
                     price_keywords + search_keywords + stats_keywords + factory_keywords)
    
    # Логируем детали анализа
    if needs_excel:
        logger.info(f"    🔍 ДЕТАЛИ АНАЛИЗА:")
        if found_price:
            logger.info(f"      💰 Ценовые ключевые слова: {found_price}")
        if found_search:
            logger.info(f"      🔎 Поисковые ключевые слова: {found_search}")
        if found_stats:
            logger.info(f"      📊 Статистические ключевые слова: {found_stats}")
        if found_factory:
            logger.info(f"      🏭 Фабричные ключевые слова: {found_factory}")
    
    # Извлекаем потенциальные названия ароматов для поиска
    search_query = ""
    words = question_lower.split()
    for i, word in enumerate(words):
        if word in search_keywords and i + 1 < len(words):
            # Берем следующие 1-3 слова как потенциальный запрос
            search_query = " ".join(words[i+1:i+4])
            break
    
    # Также ищем известные бренды в вопросе
    common_brands = ['ajmal', 'bvlgari', 'kilian', 'creed', 'tom ford', 'dior', 'chanel', 'ysl', 'afnan']
    found_brands = [brand for brand in common_brands if brand in question_lower]
    if found_brands and not search_query:
        search_query = found_brands[0]
        logger.info(f"      🏷️ Найден бренд в запросе: {found_brands[0]}")
    
    return needs_excel, search_query

async def ask_chatgpt(question):
    # Проверяем наличие API ключа
    if not OPENAI_API:
        logger.error("❌ OPENAI_API_KEY not set! Cannot process AI requests.")
        return "Извините, сервис AI временно недоступен. Пожалуйста, попробуйте позже или обратитесь к администратору."
    
    try:
        logger.info(f"🧠 ЗАПРОС К CHATGPT")
        logger.info(f"  ❓ Вопрос пользователя: '{question}'")
        # Анализируем запрос для определения необходимости Excel данных
        needs_excel, search_query = analyze_query_for_excel_data(question)
        
        # --- Новый блок: определение объема из вопроса ---
        volume_ml = None
        volume_match = re.search(r'(\d{2,4})\s*(мл|ml|г|гр|грамм|грамма|граммов)', question.lower())
        if volume_match:
            volume_ml = int(volume_match.group(1))
            logger.info(f"  📦 Найден объем в запросе: {volume_ml} мл/г")
        else:
            logger.info(f"  📦 Объем в запросе не найден")
        
        # --- Новый блок: определение необходимости статистики по вариантам ---
        show_variants_stats = False
        if needs_excel and search_query:
            # Если найдено несколько вариантов одного аромата, показываем статистику
            products = search_products(search_query, limit=10)
            aroma_names = set(p['Аромат'].strip().lower() for p in products)
            if len(products) > 1 and len(aroma_names) == 1:
                show_variants_stats = True
                logger.info(f"  📊 Включена статистика по вариантам аромата '{search_query}'")
        
        system_content = (
            "Ты - AI-Пантера (менеджер по продажам), эксперт по ароматам от компании BAHUR. "
            "У тебя есть доступ к полному каталогу и актуальным ценам.\n"
            "Ты веселая, дружелюбная и общительная пантера, которая любит шутить и помогать людям! 🐾\n"
            "Всегда отвечай с юмором, используй смайлы и будь кратким и по делу.\n"
            "\nШАБЛОН ОТВЕТА:\n"
            "✨[Бренд] [Аромат] (с ссылкой из прайса)\n" 
            
            "® Бренд: [данные из прайса]\n"
            "[флаг страны] Страна: [данные из прайса]\n"
            
            "🌱 Верхние ноты: [данные из прайса]\n"
            "🌿 Средние ноты: [данные из прайса]\n"
            "🍃 Базовые ноты: [данные из прайса]\n"
            
            "⚡️ TOP LAST: [реальный % из прайса]% (№[ранг])\n"
            "🚀 TOP ALL: [реальный % из прайса]% (№[ранг])\n"
            "♾️ VERSION: [фабрика качество: процент% | фабрика качество: процент%] (только если есть >1 версии)\n"
            
            "💵 Стоимость:\n"
            "💧[объем] грамм = [цена]₽ ([цена за грамм]₽ - 1 грамм)\n"
        )
        # Добавляем историю диалога
        history_block = ""
        base_context_length = len(system_content)
        logger.info(f"  📄 БАЗОВЫЙ КОНТЕКСТ: {base_context_length} символов")
        
        # Добавляем Excel данные если нужно
        if needs_excel:
            logger.info(f"  📊 Загружаем данные из Excel таблицы...")
            excel_context = await get_excel_context_for_chatgpt(search_query, volume_ml=volume_ml, show_variants_stats=show_variants_stats)
            system_content += excel_context
            excel_context_length = len(excel_context)
            logger.info(f"  📈 КОНТЕКСТ ИЗ EXCEL: {excel_context_length} символов")
        else:
            logger.info(f"  ℹ️ Excel данные не требуются для этого запроса")
        
        system_content += (
            "\nПРАВИЛА ОТВЕТОВ:\n"
            "1. При написании названия аромата каждое слово пиши с большой буквы\n"
            "2. Вставляй красивый и интересный смайлик в начале кнопки\n"
            "3. Если делаешь подборку ароматов, используй только те ароматы которые есть в прайсе\n"
            "4. Отвечай КОНКРЕТНО на вопрос клиента, используя данные из каталога\n"
            "5. Если клиент спрашивает про аромат - найди его в данных и опиши подробно с ценами\n"
            "6. Если клиент спрашивает про цены - рассчитай точную стоимость для нужного объема\n"
            "7. Если есть подходящая ссылка из данных, обязательно включи её в ответ\n"
            "9. Отвечай на русском языке, с эмодзи, но БЕЗ markdown\n"
            "11. Когда вставляешь ссылку, используй HTML-формат: <a href='ССЫЛКА'>ТЕКСТ</a>\n"
            "12. При расчете цен учитывай объемные скидки согласно прайс-листу, посчитай но скажи им пройти по ссылке на товар или в магазин\n"
            "13. Упоминай фабрику и качество товара когда это релевантно\n"
            "14. В ответах не используй слова для обозначение качества: DELUXE, PREMIUM, помни у нас только три категории качества: TOP, Q1, Q2\n"
            "17. Используй только красивые, уникальные смайлы, без цифр-смайлов: 1️⃣ 2️⃣ 3️⃣ 4️⃣ 5️⃣ 6️⃣ 7️⃣ 8️⃣ 9️⃣ 0️⃣ и все с таким фоном\n"
            "18. Когда пишешь текст с названием ароматов то каждая букву нового слова в аромате пиши с большой буквы или если через дефис то, тоже первая буква с большой буквы\n"
            "19. ВАЖНО: никогда не упоминай никакие ароматы которых нет у нас в прайсе. Если аромата нет в прайсе - говори что его нет\n"
            "20. Пиши коротко, красиво, ясно, со стилем, используй смайлы, твоя основа это данные которые есть в bahur_data.txt без фантазий и выдумок\n"
            "21. При поиске клиент может ошибаться и написать аромат неточно. Если совпадение 50% или больше - найди все похожие варианты и покажи клиенту, переспрашивая: 'Этот аромат? Да/Нет?' для каждого варианта\n"
            "22. Будь дружелюбным и общительным. Если человек спрашивает не про ароматы - отвечай на его вопрос нормально, но старайся держаться темы разговоров о парфюмерном бизнесе\n"
            "23. Не давай сразу ссылки на ароматы, если человек не спрашивал конкретно про них\n"
            "24. Всегда используй юмор и смайлы! Отвечай как веселая, пародистая, пантера, а не как скучный учебник\n"
            "25. На вопросы про изготовление спреев отвечай кратко и с юмором, НЕ давай инструкций по смешиванию с водой или химическими веществами. Просто скажи, что это сложный процесс, требующий специальных знаний и оборудования\n"
            "26. Не упоминай алкоголь или другие химические вещества в контексте ароматов\n"
            "27. Будь краткой и по делу, не растягивай ответы на целые параграфы\n"
            "28. НИКОГДА не давай инструкций по смешиванию ароматов с водой, спиртом или другими веществами. Это может быть опасно!\n"
            "29. Помни, что наши клиенты — это 99,9% перепродавцы! Мы работаем в B2B сегменте как оптовые поставщики, а не розничные продавцы 🐾\n"
            "30. ВСЕГДА используй правильный сайт bahur.store (НЕ bahur.com)! Если нужно дать ссылку на сайт - используй только https://www.bahur.store/ 🐾\n"
            "31. При вопросах о заказе используй информацию из bahur_data.txt: минимальная сумма 7000₽, масла должны составлять 50% от заказа, минимальный объём 30г, доставка 3-5 дней по России, стоимость доставки 183-1000₽, отправка из Грозного 🐾"
        )
        
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {OPENAI_API}",
            "Content-Type": "application/json"
        }
        data = {
            "model": "gpt-4",
            "messages": [
                {
                    "role": "system",
                    "content": system_content
                },
                {
                    "role": "user",
                    "content": f"{question}"
                }
            ],
            "temperature": 0.5
        }
        
        # Финальная статистика перед отправкой
        total_context_length = len(system_content)
        logger.info(f"  📊 ФИНАЛЬНАЯ СТАТИСТИКА:")
        logger.info(f"    - Общий размер контекста: {total_context_length} символов")
        logger.info(f"    - Использованы Excel данные: {needs_excel}")
        
        # Проверяем размер контекста
        if total_context_length > 8000:
            logger.warning(f"⚠️ Контекст слишком большой ({total_context_length} символов), обрезаем...")
            # Оставляем только базовый контекст и первые 4000 символов Excel данных
            system_content = system_content[:4000] + "\n\n[Данные обрезаны для ускорения ответа]"
            logger.info(f"  ✂️ Контекст обрезан до {len(system_content)} символов")
        
        logger.info(f"  🚀 Отправляем запрос в ChatGPT...")
        
        timeout = aiohttp.ClientTimeout(total=60)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, headers=headers, json=data) as resp:
                if resp.status != 200:
                    logger.error(f"❌ ChatGPT API error: {resp.status} - {await resp.text()}")
                    return "Извините, произошла ошибка при обработке вашего запроса. Попробуйте еще раз."
                
                result = await resp.json()
                if "choices" not in result or not result["choices"]:
                    logger.error(f"❌ ChatGPT API unexpected response: {result}")
                    return "Извините, произошла ошибка при обработке вашего запроса. Попробуйте еще раз."
                
                response_content = result["choices"][0]["message"]["content"].strip()
                
                logger.info(f"  ✅ ОТВЕТ ОТ CHATGPT ПОЛУЧЕН:")
                logger.info(f"    - Длина ответа: {len(response_content)} символов")
                logger.info(f"    - Первые 200 символов: '{response_content[:200]}{'...' if len(response_content) > 200 else ''}'")
                
                return response_content
                
    except asyncio.TimeoutError:
        logger.error(f"⏰ ChatGPT API timeout для вопроса: '{question}'")
        return "Извините, запрос занял слишком много времени. Попробуйте еще раз."
    except aiohttp.ClientError as e:
        logger.error(f"🌐 ChatGPT API client error для вопроса '{question}': {e}")
        return "Извините, произошла ошибка сети. Попробуйте еще раз."
    except Exception as e:
        logger.error(f"💥 ChatGPT API unexpected error для вопроса '{question}': {e}\n{traceback.format_exc()}")
        return "Извините, произошла неожиданная ошибка. Попробуйте еще раз."

async def search_note_api(note):
    try:
        url = f"https://api.alexander-dev.ru/bahur/search/?text={note}"
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    logger.error(f"Search API error: {resp.status} - {await resp.text()}")
                    return {"status": "error", "message": "Ошибка API"}
                
                result = await resp.json()
                return result
                
    except asyncio.TimeoutError:
        logger.error("Search API timeout")
        return {"status": "error", "message": "Таймаут запроса"}
    except aiohttp.ClientError as e:
        logger.error(f"Search API client error: {e}")
        return {"status": "error", "message": "Ошибка сети"}
    except Exception as e:
        logger.error(f"Search API unexpected error: {e}\n{traceback.format_exc()}")
        return {"status": "error", "message": "Неожиданная ошибка"}

def format_aroma_name(aroma_name):
    """Форматирует название аромата с большой буквы и дефисами"""
    if not aroma_name:
        return ""
    
    # Разбиваем на слова
    words = str(aroma_name).strip().split()
    formatted_words = []
    
    for word in words:
        # Если слово содержит дефис, каждую часть с большой буквы
        if '-' in word:
            parts = word.split('-')
            formatted_parts = [part.capitalize() for part in parts]
            formatted_words.append('-'.join(formatted_parts))
        else:
            # Обычное слово с большой буквы
            formatted_words.append(word.capitalize())
    
    return ' '.join(formatted_words)

def get_country_emoji(country_name):
    """Возвращает эмоджи флага страны по названию"""
    country_emojis = {
        'италия': '🇮🇹', 'italy': '🇮🇹',
        'франция': '🇫🇷', 'france': '🇫🇷',
        'германия': '🇩🇪', 'germany': '🇩🇪',
        'великобритания': '🇬🇧', 'uk': '🇬🇧', 'england': '🇬🇧',
        'испания': '🇪🇸', 'spain': '🇪🇸',
        'португалия': '🇵🇹', 'portugal': '🇵🇹',
        'нидерланды': '🇳🇱', 'netherlands': '🇳🇱', 'holland': '🇳🇱',
        'бельгия': '🇧🇪', 'belgium': '🇧🇪',
        'швейцария': '🇨🇭', 'switzerland': '🇨🇭',
        'австрия': '🇦🇹', 'austria': '🇦🇹',
        'турция': '🇹🇷', 'turkey': '🇹🇷',
        'россия': '🇷🇺', 'russia': '🇷🇺',
        'сша': '🇺🇸', 'usa': '🇺🇸', 'america': '🇺🇸',
        'канада': '🇨🇦', 'canada': '🇨🇦',
        'япония': '🇯🇵', 'japan': '🇯🇵',
        'китай': '🇨🇳', 'china': '🇨🇳',
        'корея': '🇰🇷', 'korea': '🇰🇷',
        'индия': '🇮🇳', 'india': '🇮🇳',
        'бразилия': '🇧🇷', 'brazil': '🇧🇷',
        'аргентина': '🇦🇷', 'argentina': '🇦🇷',
        'мексика': '🇲🇽', 'mexico': '🇲🇽',
        'австралия': '🇦🇺', 'australia': '🇦🇺',
        'новая зеландия': '🇳🇿', 'new zealand': '🇳🇿',
        'южная африка': '🇿🇦', 'south africa': '🇿🇦',
        'египет': '🇪🇬', 'egypt': '🇪🇬',
        'марокко': '🇲🇦', 'morocco': '🇲🇦',
        'дубай': '🇦🇪', 'uae': '🇦🇪', 'эмираты': '🇦🇪',
        'саудовская аравия': '🇸🇦', 'saudi arabia': '🇸🇦',
        'катар': '🇶🇦', 'qatar': '🇶🇦',
        'кувейт': '🇰🇼', 'kuwait': '🇰🇼',
        'бахрейн': '🇧🇭', 'bahrain': '🇧🇭',
        'оман': '🇴🇲', 'oman': '🇴🇲',
        'иордания': '🇯🇴', 'jordan': '🇯🇴',
        'ливан': '🇱🇧', 'lebanon': '🇱🇧',
        'сирия': '🇸🇾', 'syria': '🇸🇾',
        'ирак': '🇮🇶', 'iraq': '🇮🇶',
        'иран': '🇮🇷', 'iran': '🇮🇷',
        'пакистан': '🇵🇰', 'pakistan': '🇵🇰',
        'афганистан': '🇦🇫', 'afghanistan': '🇦🇫',
        'узбекистан': '🇺🇿', 'uzbekistan': '🇺🇿',
        'казахстан': '🇰🇿', 'kazakhstan': '🇰🇿',
        'киргизия': '🇰🇬', 'kyrgyzstan': '🇰🇬',
        'таджикистан': '🇹🇯', 'tajikistan': '🇹🇯',
        'туркменистан': '🇹🇲', 'turkmenistan': '🇹🇲',
        'азербайджан': '🇦🇿', 'azerbaijan': '🇦🇿',
        'грузия': '🇬🇪', 'georgia': '🇬🇪',
        'армения': '🇦🇲', 'armenia': '🇦🇲',
        'молдова': '🇲🇩', 'moldova': '🇲🇩',
        'украина': '🇺🇦', 'ukraine': '🇺🇦',
        'беларусь': '🇧🇾', 'belarus': '🇧🇾',
        'латвия': '🇱🇻', 'latvia': '🇱🇻',
        'литва': '🇱🇹', 'lithuania': '🇱🇹',
        'эстония': '🇪🇪', 'estonia': '🇪🇪',
        'польша': '🇵🇱', 'poland': '🇵🇱',
        'чехия': '🇨🇿', 'czech republic': '🇨🇿',
        'словакия': '🇸🇰', 'slovakia': '🇸🇰',
        'венгрия': '🇭🇺', 'hungary': '🇭🇺',
        'румыния': '🇷🇴', 'romania': '🇷🇴',
        'болгария': '🇧🇬', 'bulgaria': '🇧🇬',
        'греция': '🇬🇷', 'greece': '🇬🇷',
        'хорватия': '🇭🇷', 'croatia': '🇭🇷',
        'сербия': '🇷🇸', 'serbia': '🇷🇸',
        'черногория': '🇲🇪', 'montenegro': '🇲🇪',
        'албания': '🇦🇱', 'albania': '🇦🇱',
        'македония': '🇲🇰', 'macedonia': '🇲🇰',
        'словения': '🇸🇮', 'slovenia': '🇸🇮',
        'босния': '🇧🇦', 'bosnia': '🇧🇦',
        'кипр': '🇨🇾', 'cyprus': '🇨🇾',
        'мальта': '🇲🇹', 'malta': '🇲🇹',
        'исландия': '🇮🇸', 'iceland': '🇮🇸',
        'норвегия': '🇳🇴', 'norway': '🇳🇴',
        'швеция': '🇸🇪', 'sweden': '🇸🇪',
        'финляндия': '🇫🇮', 'finland': '🇫🇮',
        'дания': '🇩🇰', 'denmark': '🇩🇰',
        'ирландия': '🇮🇪', 'ireland': '🇮🇪',
        'люксембург': '🇱🇺', 'luxembourg': '🇱🇺',
        'монaco': '🇲🇨', 'monaco': '🇲🇨',
        'андорра': '🇦🇩', 'andorra': '🇦🇩',
        'сан-марино': '🇸🇲', 'san marino': '🇸🇲',
        'ватикан': '🇻🇦', 'vatican': '🇻🇦',
        'лихтенштейн': '🇱🇮', 'liechtenstein': '🇱🇮'
    }
    
    if not country_name:
        return "🌍"
    
    country_lower = str(country_name).lower().strip()
    return country_emojis.get(country_lower, "🌍")

async def get_notes_from_api(aroma_name):
    """Получает ноты аромата через API"""
    try:
        result = await search_note_api(aroma_name)
        if result.get("status") == "success" and "data" in result:
            data = result["data"]
            if isinstance(data, list) and len(data) > 0:
                aroma_data = data[0]  # Берем первый результат
                return {
                    "top_notes": aroma_data.get("top_notes", ""),
                    "middle_notes": aroma_data.get("middle_notes", ""),
                    "base_notes": aroma_data.get("base_notes", ""),
                    "country": aroma_data.get("country", ""),
                    "link": aroma_data.get("link", "")
                }
        return None
    except Exception as e:
        logger.error(f"Error getting notes from API: {e}")
        return None

# --- Telegram sendMessage ---
async def telegram_send_message(chat_id, text, reply_markup=None, parse_mode="HTML"):
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        
        timeout = httpx.Timeout(30.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code != 200:
                logger.error(f"Telegram API error: {resp.status_code} - {resp.text}")
                return False
            return True
            
    except httpx.TimeoutException:
        logger.error("Telegram API timeout")
        return False
    except httpx.RequestError as e:
        logger.error(f"Telegram API request error: {e}")
        return False
    except Exception as e:
        logger.error(f"Telegram API unexpected error: {e}\n{traceback.format_exc()}")
        return False

# --- Telegram editMessage ---
async def telegram_edit_message(chat_id, message_id, text, reply_markup=None, parse_mode="HTML"):
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/editMessageText"
        payload = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": parse_mode
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        
        timeout = httpx.Timeout(30.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code != 200:
                logger.error(f"Telegram editMessage API error: {resp.status_code} - {resp.text}")
                return False
            return True
            
    except httpx.TimeoutException:
        logger.error("Telegram editMessage API timeout")
        return False
    except httpx.RequestError as e:
        logger.error(f"Telegram editMessage API request error: {e}")
        return False
    except Exception as e:
        logger.error(f"Telegram editMessage API unexpected error: {e}\n{traceback.format_exc()}")
        return False

# --- Telegram answerCallbackQuery ---
async def telegram_answer_callback_query(callback_query_id, text=None, show_alert=False):
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/answerCallbackQuery"
        payload = {
            "callback_query_id": callback_query_id
        }
        if text:
            payload["text"] = text
        if show_alert:
            payload["show_alert"] = show_alert
        
        timeout = httpx.Timeout(10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code != 200:
                logger.error(f"Telegram answerCallbackQuery API error: {resp.status_code} - {resp.text}")
                return False
            return True
            
    except httpx.TimeoutException:
        logger.error("Telegram answerCallbackQuery API timeout")
        return False
    except httpx.RequestError as e:
        logger.error(f"Telegram answerCallbackQuery API request error: {e}")
        return False
    except Exception as e:
        logger.error(f"Telegram answerCallbackQuery API unexpected error: {e}\n{traceback.format_exc()}")
        return False

# --- Поиск по ID аромата ---
async def search_by_id_api(aroma_id):
    try:
        url = f"https://api.alexander-dev.ru/bahur/search/?id={aroma_id}"
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    logger.error(f"Search by ID API error: {resp.status} - {await resp.text()}")
                    return {"status": "error", "message": "Ошибка API"}
                
                result = await resp.json()
                return result
                
    except asyncio.TimeoutError:
        logger.error("Search by ID API timeout")
        return {"status": "error", "message": "Таймаут запроса"}
    except aiohttp.ClientError as e:
        logger.error(f"Search by ID API client error: {e}")
        return {"status": "error", "message": "Ошибка сети"}
    except Exception as e:
        logger.error(f"Search by ID API unexpected error: {e}\n{traceback.format_exc()}")
        return {"status": "error", "message": "Неожиданная ошибка"}

# --- Обработка голосовых сообщений ---
async def recognize_voice_content(file_content, chat_id=None):
    """Распознаёт речь из байтового содержимого ogg-файла. Возвращает текст или строку-ошибку."""
    try:
        import speech_recognition as sr
        from pydub import AudioSegment
        import tempfile
        import math
        
        recognizer = sr.Recognizer()
        
        with tempfile.NamedTemporaryFile(suffix='.ogg') as temp_ogg, tempfile.NamedTemporaryFile(suffix='.wav') as temp_wav:
            temp_ogg.write(file_content)
            temp_ogg.flush()
            
            try:
                audio = AudioSegment.from_file(temp_ogg.name)
                
                # Проверяем длительность (в миллисекундах)
                duration_seconds = len(audio) / 1000.0
                logger.info(f"Voice message duration: {duration_seconds:.1f} seconds")
                
                # Если файл слишком длинный (больше 2 минут), разбиваем на части
                if duration_seconds > 120:
                    return await recognize_long_audio(audio, chat_id)
                
                # Для коротких файлов - обычная обработка
                audio.export(temp_wav.name, format='wav')
                temp_wav.flush()
                
            except Exception as audio_error:
                logger.error(f"Audio conversion error: {audio_error}")
                return "Ошибка при обработке аудио файла. Попробуйте еще раз или напишите текст."
            
            try:
                with sr.AudioFile(temp_wav.name) as source:
                    # Устанавливаем настройки для лучшего распознавания
                    recognizer.energy_threshold = 300
                    recognizer.pause_threshold = 0.8
                    recognizer.phrase_threshold = 0.3
                    recognizer.non_speaking_duration = 0.5
                    
                    audio_data = recognizer.record(source)
                    text_content = recognizer.recognize_google(audio_data, language='ru-RU')
                    logger.info(f"Voice recognized: '{text_content}'")
                    return text_content
                    
            except sr.UnknownValueError:
                logger.error("Speech recognition could not understand audio")
                return "Не удалось разобрать речь. Попробуйте говорить четче или напишите текст."
            except sr.RequestError as e:
                logger.error(f"Speech recognition service error: {e}")
                return "Ошибка сервиса распознавания речи. Попробуйте еще раз или напишите текст."
                
    except Exception as e:
        logger.error(f"Speech recognition error: {e}\n{traceback.format_exc()}")
        return "Ошибка при обработке голосового сообщения."

async def recognize_long_audio(audio_segment, chat_id=None):
    """Распознает длинные аудио файлы, разбивая их на части"""
    try:
        import speech_recognition as sr
        import tempfile
        
        recognizer = sr.Recognizer()
        recognizer.energy_threshold = 300
        recognizer.pause_threshold = 0.8
        
        # Разбиваем на части по 55 секунд с перекрытием 5 секунд
        chunk_length = 55 * 1000  # 55 секунд в миллисекундах
        overlap = 5 * 1000        # 5 секунд перекрытия
        
        total_length = len(audio_segment)
        total_duration = total_length / 1000.0
        recognized_texts = []
        
        # Подсчитываем количество частей
        chunks_count = len(list(range(0, total_length - overlap, chunk_length - overlap)))
        current_chunk = 0
        
        for start in range(0, total_length - overlap, chunk_length - overlap):
            end = min(start + chunk_length, total_length)
            chunk = audio_segment[start:end]
            current_chunk += 1
            
            logger.info(f"Processing audio chunk {current_chunk}/{chunks_count}: {start/1000:.1f}s - {end/1000:.1f}s")
            
            # Отправляем уведление о прогрессе
            if chat_id and current_chunk % 3 == 0:  # Каждую третью часть
                progress_percent = int((current_chunk / chunks_count) * 100)
                await send_progress_message(chat_id, 
                    f"🔄 Обрабатываю часть {current_chunk}/{chunks_count} ({progress_percent}%)")
            
            with tempfile.NamedTemporaryFile(suffix='.wav') as temp_chunk:
                chunk.export(temp_chunk.name, format='wav')
                temp_chunk.flush()
                
                try:
                    with sr.AudioFile(temp_chunk.name) as source:
                        audio_data = recognizer.record(source)
                        text = recognizer.recognize_google(audio_data, language='ru-RU')
                        if text.strip():
                            recognized_texts.append(text.strip())
                            logger.info(f"Chunk {current_chunk} recognized: '{text[:50]}...'")
                        
                except sr.UnknownValueError:
                    logger.warning(f"Could not understand audio chunk {current_chunk} ({start/1000:.1f}s - {end/1000:.1f}s)")
                    continue
                except sr.RequestError as e:
                    logger.error(f"Speech recognition error for chunk {current_chunk}: {e}")
                    continue
                
                # Пауза между запросами к API
                await asyncio.sleep(0.5)
        
        if not recognized_texts:
            return "Не удалось распознать речь в длинном голосовом сообщении. Попробуйте записать более короткое сообщение или напишите текст."
        
        # Уведомляем о завершении обработки
        if chat_id:
            await send_progress_message(chat_id, "✅ Распознавание завершено, формирую ответ...")
        
        # Объединяем все распознанные части
        full_text = " ".join(recognized_texts)
        logger.info(f"Full recognized text: '{full_text[:100]}...'")
        
        return full_text
        
    except Exception as e:
        logger.error(f"Long audio recognition error: {e}\n{traceback.format_exc()}")
        return "Ошибка при обработке длинного голосового сообщения."

async def process_voice_message(voice, chat_id):
    try:
        # Получаем информацию о файле
        file_id = voice["file_id"]
        file_unique_id = voice["file_unique_id"]
        duration = voice.get("duration", 0)
        
        # Получаем файл
        file_url = f"https://api.telegram.org/bot{TOKEN}/getFile?file_id={file_id}"
        async with httpx.AsyncClient() as client:
            resp = await client.get(file_url)
            if resp.status_code != 200:
                logger.error(f"Failed to get file info: {resp.status_code}")
                return None
            
            file_info = resp.json()
            if not file_info.get("ok"):
                logger.error(f"File info error: {file_info}")
                return None
            
            file_path = file_info["result"]["file_path"]
            file_url = f"https://api.telegram.org/file/bot{TOKEN}/{file_path}"
            
            # Скачиваем файл
            async with client.stream("GET", file_url) as response:
                if response.status_code != 200:
                    logger.error(f"Failed to download file: {response.status_code}")
                    return None
                
                # Читаем содержимое файла
                file_content = await response.aread()
                
                # Распознаем речь с использованием tempfile
                text_content = await recognize_voice_content(file_content, chat_id)
                # Если результат не ошибка, отправляем в ChatGPT
                if text_content and not any(err in text_content for err in ["Ошибка", "Не удалось", "недоступно"]):
                    ai_answer = await ask_chatgpt(text_content)
                    return ai_answer
                else:
                    return text_content
                
    except Exception as e:
        logger.error(f"Voice processing error: {e}\n{traceback.format_exc()}")
        return "Ошибка при обработке голосового сообщения."

# --- Альтернативная обработка голосовых сообщений (без aifc) ---
async def process_voice_message_alternative(voice, chat_id):
    """Альтернативная обработка голосовых сообщений без aifc"""
    try:
        # Получаем информацию о файле
        file_id = voice["file_id"]
        file_unique_id = voice["file_unique_id"]
        duration = voice.get("duration", 0)
        
        # Если голосовое сообщение слишком короткое
        if duration < 1:
            return "Голосовое сообщение слишком короткое. Попробуйте записать более длинное сообщение."
        
        # Получаем файл
        file_url = f"https://api.telegram.org/bot{TOKEN}/getFile?file_id={file_id}"
        async with httpx.AsyncClient() as client:
            resp = await client.get(file_url)
            if resp.status_code != 200:
                logger.error(f"Failed to get file info: {resp.status_code}")
                return None
            
            file_info = resp.json()
            if not file_info.get("ok"):
                logger.error(f"File info error: {file_info}")
                return None
            
            file_path = file_info["result"]["file_path"]
            file_url = f"https://api.telegram.org/file/bot{TOKEN}/{file_path}"
            
            # Скачиваем файл
            async with client.stream("GET", file_url) as response:
                if response.status_code != 200:
                    logger.error(f"Failed to download file: {response.status_code}")
                    return None
                
                # Читаем содержимое файла
                file_content = await response.aread()
                
                # Пытаемся распознать речь без aifc
                text_content = await recognize_voice_content(file_content, chat_id)
                if text_content and not any(err in text_content for err in ["Ошибка", "Не удалось", "недоступно"]):
                    ai_answer = await ask_chatgpt(text_content)
                    return ai_answer
                else:
                    return text_content
                
    except Exception as e:
        logger.error(f"Alternative voice processing error: {e}\n{traceback.format_exc()}")
        return "Ошибка при обработке голосового сообщения."

# --- Упрощенная обработка голосовых сообщений (без распознавания) ---
async def process_voice_message_simple(voice, chat_id):
    """Упрощенная обработка голосовых сообщений без сложных зависимостей"""
    try:
        # Получаем информацию о файле
        file_id = voice["file_id"]
        duration = voice.get("duration", 0)
        
        # Если голосовое сообщение слишком короткое
        if duration < 1:
            return "Голосовое сообщение слишком короткое. Попробуйте записать более длинное сообщение."
        
        # Получаем файл
        file_url = f"https://api.telegram.org/bot{TOKEN}/getFile?file_id={file_id}"
        async with httpx.AsyncClient() as client:
            resp = await client.get(file_url)
            if resp.status_code != 200:
                logger.error(f"Failed to get file info: {resp.status_code}")
                return None
            
            file_info = resp.json()
            if not file_info.get("ok"):
                logger.error(f"File info error: {file_info}")
                return None
            
            # Просто возвращаем информацию о голосовом сообщении
            return f"Получено голосовое сообщение длительностью {duration} секунд. Для распознавания речи напишите ваш вопрос текстом."
                
    except Exception as e:
        logger.error(f"Simple voice processing error: {e}\n{traceback.format_exc()}")
        return "Ошибка при обработке голосового сообщения."

# --- Функция "печатает" ---
async def send_typing_action(chat_id):
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/sendChatAction"
        payload = {
            "chat_id": chat_id,
            "action": "typing"
        }
        timeout = httpx.Timeout(5.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code != 200:
                logger.error(f"Failed to send typing action: {resp.status_code} - {resp.text}")
    except Exception as e:
        logger.error(f"Failed to send typing action: {e}")

async def send_progress_message(chat_id, text):
    """Отправляет сообщение о прогрессе обработки"""
    try:
        success = await telegram_send_message(chat_id, text)
        if success:
            logger.info(f"[TG] Sent progress message to {chat_id}")
        return success
    except Exception as e:
        logger.error(f"Failed to send progress message: {e}")
        return False

# --- Умное распознавание нот ---
def is_likely_note(text):
    """Определяет, похож ли текст на название ноты"""
    if not text:
        return False
    
    # Список популярных нот
    common_notes = [
        'ваниль', 'лаванда', 'роза', 'жасмин', 'сандал', 'мускус', 'амбра', 'пачули',
        'бергамот', 'лимон', 'апельсин', 'мандарин', 'грейпфрут', 'лайм',
        'клубника', 'малина', 'черника', 'вишня', 'персик', 'абрикос', 'яблоко',
        'груша', 'ананас', 'манго', 'банан', 'кокос', 'карамель', 'шоколад',
        'кофе', 'чай', 'мята', 'базилик', 'розмарин', 'тимьян', 'орегано',
        'корица', 'кардамон', 'имбирь', 'куркума', 'перец', 'гвоздика',
        'кедр', 'сосна', 'ель', 'дуб', 'береза', 'иланг-иланг', 'нероли',
        'ирис', 'фиалка', 'ландыш', 'сирень', 'жасмин', 'гардения',
        'морская соль', 'морской бриз', 'дождь', 'снег', 'земля', 'мох',
        'дым', 'кожа', 'табак', 'виски', 'коньяк', 'ром', 'вино',
        'мед', 'сливки', 'молоко', 'йогурт', 'сыр', 'масло'
    ]
    
    text_lower = text.lower().strip()
    
    # Проверяем точное совпадение
    if text_lower in common_notes:
        return True
    
    # Проверяем частичное совпадение
    for note in common_notes:
        if note in text_lower or text_lower in note:
            return True
    
    # Проверяем по длине и характеру (короткие слова часто бывают нотами)
    if len(text_lower) <= 15 and not any(char.isdigit() for char in text_lower):
        # Если текст короткий и не содержит цифр, возможно это нота
        return True
    
    return False

# --- Обработка ссылок в тексте ---
import re

def convert_to_nominative_case(text):
    """Приводит текст к именительному падежу (базовая реализация для наиболее частых случаев)"""
    text = text.strip().lower()
    
    # Словарь наиболее частых преобразований
    nominative_dict = {
        # Винительный падеж -> Именительный
        'прайс': 'прайс',
        'каталог': 'каталог', 
        'магазин': 'магазин',
        'сайт': 'сайт',
        'страницу': 'страница',
        'страничку': 'страничка',
        'товар': 'товар',
        'товары': 'товары',
        'духи': 'духи',
        'аромат': 'аромат',
        'ароматы': 'ароматы',
        'парфюм': 'парфюм',
        'масло': 'масло',
        'масла': 'масла',
        'флакон': 'флакон',
        'флаконы': 'флаконы',
        'бренд': 'бренд',
        'бренды': 'бренды',
        'коллекцию': 'коллекция',
        'коллекция': 'коллекция',
        'новинки': 'новинки',
        'новинку': 'новинка',
        'скидки': 'скидки',
        'скидку': 'скидка',
        'акции': 'акции',
        'акцию': 'акция',
        'отзывы': 'отзывы',
        'отзыв': 'отзыв',
        'статьи': 'статьи',
        'статью': 'статья',
        'информацию': 'информация',
        'описание': 'описание',
        'характеристики': 'характеристики',
        'подробности': 'подробности',
        'детали': 'детали',
        'доставку': 'доставка',
        'оплату': 'оплата',
        'заказ': 'заказ',
        'корзину': 'корзина',
        'покупки': 'покупки',
        'покупку': 'покупка',
        
        # Родительный падеж -> Именительный  
        'прайса': 'прайс',
        'каталога': 'каталог',
        'магазина': 'магазин',
        'сайта': 'сайт',
        'товара': 'товар',
        'аромата': 'аромат',
        'парфюма': 'парфюм',
        'масла': 'масло',
        'флакона': 'флакон',
        'бренда': 'бренд',
        
        # Дательный падеж -> Именительный
        'прайсу': 'прайс',
        'каталогу': 'каталог',
        'магазину': 'магазин',
        'сайту': 'сайт',
        'товару': 'товар',
        'аромату': 'аромат',
        
        # Творительный падеж -> Именительный
        'прайсом': 'прайс',
        'каталогом': 'каталог',
        'магазином': 'магазин',
        'сайтом': 'сайт',
        'товаром': 'товар',
        'ароматом': 'аромат',
        
        # Предложный падеж -> Именительный
        'прайсе': 'прайс',
        'каталоге': 'каталог', 
        'магазине': 'магазин',
        'сайте': 'сайт',
        'товаре': 'товар',
        'аромате': 'аромат',
        
        # Частые готовые фразы
        'подробнее': 'подробнее',
        'больше': 'больше',
        'далее': 'далее',
        'читать': 'читать',
        'смотреть': 'смотреть',
        'перейти': 'перейти',
        'посмотреть': 'посмотреть',
        'узнать': 'узнать',
        'выбрать': 'выбрать',
        'купить': 'купить',
        'заказать': 'заказать',
        'оформить': 'оформить'
    }
    
    # Проверяем точное совпадение в словаре
    if text in nominative_dict:
        result = nominative_dict[text]
    else:
        # Базовые правила для окончаний
        if text.endswith('ую'):
            result = text[:-2] + 'ая'
        elif text.endswith('ию'):
            result = text[:-2] + 'ия'  
        elif text.endswith('ую'):
            result = text[:-2] + 'ая'
        elif text.endswith('ой'):
            result = text[:-2] + 'ый'
        elif text.endswith('ей'):
            result = text[:-2] + 'ий'
        elif text.endswith('ом'):
            result = text[:-2]
        elif text.endswith('ем'):
            result = text[:-2]
        elif text.endswith('ами'):
            result = text[:-3] + 'ы'
        elif text.endswith('ями'):
            result = text[:-3] + 'и'
        else:
            result = text
    
    # Делаем первую букву заглавной
    return result.capitalize()

def extract_links_from_text(text):
    """Извлекает ссылки из HTML-текста и создает кнопки"""
    # Ищем ссылки в формате <a href='URL'>ТЕКСТ</a>
    link_pattern = r"<a\s+href=['\"]([^'\"]+)['\"][^>]*>([^<]+)</a>"
    links = re.findall(link_pattern, text)
    
    if not links:
        return None
    
    # Создаем кнопки для каждой ссылки
    buttons = []
    for url, button_text in links:
        # Приводим текст кнопки к именительному падежу
        button_text_nominative = convert_to_nominative_case(button_text)
        buttons.append([{"text": button_text_nominative, "url": url}])
    
    return {"inline_keyboard": buttons}

def remove_html_links(text):
    """Удаляет HTML-ссылки из текста, оставляя только текст"""
    # Удаляем ссылки в формате <a href='URL'>ТЕКСТ</a>, оставляя только ТЕКСТ
    link_pattern = r"<a\s+href=['\"][^'\"]+['\"][^>]*>([^<]+)</a>"
    return re.sub(link_pattern, r"\1", text)

# --- Telegram webhook endpoint ---
print('=== [LOG] Объявляю эндпоинт webhook... ===')
@app.post("/webhook/ai-bear-123456")
async def telegram_webhook(update: dict, request: Request):
    logger.info(f"=== WEBHOOK CALLED ===")
    logger.info(f"Request from: {request.client.host}")
    logger.info(f"Update type: {list(update.keys()) if update else 'None'}")
    
    try:
        result = await telegram_webhook_impl(update, request)
        logger.info(f"=== WEBHOOK COMPLETED SUCCESSFULLY ===")
        return result
    except Exception as e:
        logger.error(f"=== WEBHOOK FAILED: {e} ===")
        logger.error(traceback.format_exc())
        return {"ok": False, "error": str(e)}

# --- Переносим вашу логику webhook сюда ---
async def telegram_webhook_impl(update: dict, request: Request):
    print(f'[WEBHOOK] Called: {request.url} from {request.client.host}')
    print(f'[WEBHOOK] Body: {update}')
    logger.info(f"[WEBHOOK] Called: {request.url} from {request.client.host}")
    logger.info(f"[WEBHOOK] Body: {update}")
    try:
        if "message" in update:
            print('[WEBHOOK] message detected')
            message = update["message"]
            chat_id = message["chat"]["id"]
            user_id = message["from"]["id"]
            text = message.get("text", "").strip()
            voice = message.get("voice")
            state = get_user_state(user_id)
            logger.info(f"[TG] user_id: {user_id}, text: {text}, state: {state}")
            
            try:
                # Обновляем активность пользователя для любого сообщения
                first_name = message["from"].get("first_name")
                username = message["from"].get("username")
                add_user_to_db(user_id, chat_id, first_name, username)
                
                # Обработка голосовых сообщений
                if voice:
                    logger.info(f"[TG] Voice message received from {user_id}")
                    await send_typing_action(chat_id)
                    
                    file_id = voice["file_id"]
                    file_unique_id = voice["file_unique_id"]
                    duration = voice.get("duration", 0)
                    file_size = voice.get("file_size", 0)
                    
                    # Проверка максимальной длительности (1 час)
                    if duration > 3600:
                        await telegram_send_message(chat_id, 
                            "🎙️ Голосовое сообщение слишком длинное (больше 1 часа). "
                            "Пожалуйста, запишите более короткое сообщение или напишите текст.")
                        return {"ok": True}
                    
                    # Проверка размера файла (50MB максимум)
                    if file_size > 50 * 1024 * 1024:
                        await telegram_send_message(chat_id, 
                            "🎙️ Голосовое сообщение слишком большое (больше 50MB). "
                            "Пожалуйста, запишите более короткое сообщение.")
                        return {"ok": True}
                    
                    try:
                        file_url = f"https://api.telegram.org/bot{TOKEN}/getFile?file_id={file_id}"
                        
                        # Устанавливаем таймауты для длинных файлов
                        timeout = httpx.Timeout(
                            connect=10.0,
                            read=300.0,  # Увеличенный таймаут для чтения очень больших файлов (до часа)
                            write=10.0,
                            pool=10.0
                        )
                        
                        async with httpx.AsyncClient(timeout=timeout) as client:
                            resp = await client.get(file_url)
                            if resp.status_code != 200:
                                logger.error(f"Failed to get file info: {resp.status_code}")
                                await telegram_send_message(chat_id, "Ошибка при получении информации о голосовом файле.")
                                return {"ok": True}
                            
                            file_info = resp.json()
                            if not file_info.get("ok"):
                                logger.error(f"File info error: {file_info}")
                                await telegram_send_message(chat_id, "Ошибка при получении информации о голосовом файле.")
                                return {"ok": True}
                            
                            file_path = file_info["result"]["file_path"]
                            download_url = f"https://api.telegram.org/file/bot{TOKEN}/{file_path}"
                            
                            logger.info(f"[TG] Downloading voice file: duration={duration}s, size={file_size}bytes")
                            
                            async with client.stream("GET", download_url) as response:
                                if response.status_code != 200:
                                    logger.error(f"Failed to download file: {response.status_code}")
                                    await telegram_send_message(chat_id, "Ошибка при скачивании голосового файла.")
                                    return {"ok": True}
                                
                                # Читаем файл по частям для больших файлов
                                file_content = await response.aread()
                                
                                logger.info(f"[TG] Voice file downloaded, recognizing speech...")
                                
                                # Уведомляем о начале обработки для длинных файлов
                                if duration > 120:
                                    minutes = duration // 60
                                    seconds = duration % 60
                                    duration_str = f"{minutes}м {seconds}с" if minutes > 0 else f"{duration}с"
                                    await send_progress_message(chat_id, 
                                        f"🎙️ Обрабатываю длинное голосовое сообщение ({duration_str}). "
                                        "Это может занять некоторое время...")
                                
                                text_content = await recognize_voice_content(file_content, chat_id if duration > 120 else None)
                                logger.info(f"[TG] Voice recognized text: {text_content[:100]}...")
                                
                                if text_content and not any(err in text_content for err in ["Ошибка", "Не удалось", "недоступно"]):
                                    ai_answer = await ask_chatgpt(text_content)
                                    ai_answer = ai_answer.replace('*', '')
                                    buttons = extract_links_from_text(ai_answer)
                                    ai_answer_clean = remove_html_links(ai_answer)
                                    success = await telegram_send_message(chat_id, ai_answer_clean, buttons if buttons else None)
                                    if success:
                                        logger.info(f"[TG] Sent AI answer to voice message for {chat_id}")
                                    else:
                                        logger.error(f"[TG] Failed to send AI answer to voice message for {chat_id}")
                                else:
                                    await telegram_send_message(chat_id, text_content)
                                    
                    except httpx.TimeoutException:
                        logger.error("Voice file download timeout")
                        await telegram_send_message(chat_id, 
                            "⏰ Время обработки голосового сообщения истекло. "
                            "Попробуйте записать более короткое сообщение или напишите текст.")
                    except Exception as voice_error:
                        logger.error(f"Voice processing error: {voice_error}\n{traceback.format_exc()}")
                        await telegram_send_message(chat_id, 
                            "Произошла ошибка при обработке голосового сообщения. "
                            "Попробуйте еще раз или напишите текст.")
                    
                    return {"ok": True}
                
                if text == "/start":
                    # Добавляем пользователя в базу данных
                    first_name = message["from"].get("first_name")
                    username = message["from"].get("username")
                    add_user_to_db(user_id, chat_id, first_name, username)
                    
                    welcome = (
                        '<b>Здравствуйте!\n\n'
                        'Я — ваш ароматный помощник от BAHUR.\n'
                        '🍓 Ищу ноты и 🐆 отвечаю на вопросы с любовью. ❤\n\n'
                        '💡 <i>Используйте /menu для возврата в главное меню</i></b>'
                    )
                    main_menu = {
                        "inline_keyboard": [
                            [{"text": "🐆 Ai-Пантера", "callback_data": "ai"}],
                            [
                                {"text": "🍦 Прайс", "url": "https://drive.google.com/file/d/1J70LlZwh6g7JOryDG2br-weQrYfv6zTc/view?usp=sharing"},
                                {"text": "🍿 Магазин", "url": "https://www.bahur.store/m/"},
                                {"text": "♾️ Вопросы", "url": "https://vk.com/@bahur_store-optovye-praisy-ot-bahur"}
                            ],
                            [
                                {"text": "🎮 Чат", "url": "https://t.me/+VYDZEvbp1pce4KeT"},
                                {"text": "💎 Статьи", "url": "https://vk.com/bahur_store?w=app6326142_-133936126%2523w%253Dapp6326142_-133936126"},
                                {"text": "🏆 Отзывы", "url": "https://vk.com/@bahur_store"}
                            ],
                            [{"text": "🍓 Ноты", "callback_data": "instruction"}]
                        ]
                    }
                    success = await telegram_send_message(chat_id, welcome, main_menu)
                    if success:
                        logger.info(f"[TG] Sent welcome to {chat_id}")
                    else:
                        logger.error(f"[TG] Failed to send welcome to {chat_id}")
                    set_user_state(user_id, None)  # Сбрасываем состояние при /start
                    return {"ok": True}
                elif text == "/menu":
                    # Команда для выхода из режима AI и возврата в главное меню
                    welcome = (
                        '<b>Здравствуйте!\n\n'
                        'Я — ваш ароматный помощник от BAHUR.\n'
                        '🍓 Ищу ноты и 🐾 отвечаю на вопросы с любовью. ❤\n\n'
                        '💡 <i>Используйте /menu для возврата в главное меню</i></b>'
                    )
                    main_menu = {
                        "inline_keyboard": [
                            [{"text": "🐆 AI-Пантера", "callback_data": "ai"}],
                            [
                                {"text": "🍦 Прайс", "url": "https://drive.google.com/file/d/1J70LlZwh6g7JOryDG2br-weQrYfv6zTc/view?usp=sharing"},
                                {"text": "🍿 Магазин", "url": "https://www.bahur.store/m/"},
                                {"text": "♾️ Вопросы", "url": "https://vk.com/@bahur_store-optovye-praisy-ot-bahur"}
                            ],
                            [
                                {"text": "🎮 Чат", "url": "https://t.me/+VYDZEvbp1pce4KeT"},
                                {"text": "💎 Статьи", "url": "https://vk.com/bahur_store?w=app6326142_-133936126%2523w%253Dapp6326142_-133936126"},
                                {"text": "🏆 Отзывы", "url": "https://vk.com/@bahur_store"}
                            ],
                            [{"text": "🍓 Ноты", "callback_data": "instruction"}]
                        ]
                    }
                    success = await telegram_send_message(chat_id, welcome, main_menu)
                    if success:
                        logger.info(f"[TG] Sent menu to {chat_id}")
                    else:
                        logger.error(f"[TG] Failed to send menu to {chat_id}")
                    set_user_state(user_id, None)  # Сбрасываем состояние
                    return {"ok": True}
                if state == 'awaiting_ai_question':
                    logger.info(f"[TG] Processing AI question for user {user_id}")
                    # Отправляем индикатор "печатает"
                    await send_typing_action(chat_id)
                    ai_answer = await ask_chatgpt(text)
                    ai_answer = ai_answer.replace('*', '')
                    
                    # Извлекаем ссылки из ответа и создаем кнопки
                    buttons = extract_links_from_text(ai_answer)
                    ai_answer_clean = remove_html_links(ai_answer)
                    
                    success = await telegram_send_message(chat_id, ai_answer_clean, buttons if buttons else None)
                    if success:
                        logger.info(f"[TG] Sent ai_answer to {chat_id}")
                    else:
                        logger.error(f"[TG] Failed to send ai_answer to {chat_id}")
                    # НЕ сбрасываем состояние - остаемся в режиме AI
                    return {"ok": True}
                if state == 'awaiting_note_search':
                    logger.info(f"[TG] Processing note search for user {user_id}")
                    # Отправляем индикатор "печатает"
                    await send_typing_action(chat_id)
                    result = await search_note_api(text)
                    if result.get("status") == "success":
                        msg = f'✨ {result.get("brand")} {result.get("aroma")}\n\n{result.get("description")}'
                        # Добавляем кнопки "Подробнее" и "Повторить"
                        reply_markup = {
                            "inline_keyboard": [
                                [
                                    {"text": "🚀 Подробнее", "url": result.get("url", "")},
                                    {"text": "♾️ Повторить", "callback_data": f"repeatapi_{result.get('ID', '')}"}
                                ]
                            ]
                        }
                        success = await telegram_send_message(chat_id, msg, reply_markup)
                        if success:
                            logger.info(f"[TG] Sent note result to {chat_id}")
                        else:
                            logger.error(f"[TG] Failed to send note result to {chat_id}")
                    else:
                        success = await telegram_send_message(chat_id, "Ничего не найдено по этой ноте 😢")
                        if success:
                            logger.info(f"[TG] Sent not found to {chat_id}")
                        else:
                            logger.error(f"[TG] Failed to send not found to {chat_id}")
                    set_user_state(user_id, None)  # Сбрасываем состояние
                    return {"ok": True}
                # Если нет состояния, проверяем, похож ли текст на ноту
                if is_likely_note(text):
                    logger.info(f"[TG] Text '{text}' looks like a note, searching...")
                    # Отправляем индикатор "печатает"
                    await send_typing_action(chat_id)
                    result = await search_note_api(text)
                    if result.get("status") == "success":
                        msg = f'✨ {result.get("brand")} {result.get("aroma")}\n\n{result.get("description")}'
                        # Добавляем кнопки "Подробнее" и "Повторить"
                        reply_markup = {
                            "inline_keyboard": [
                                [
                                    {"text": "🚀 Подробнее", "url": result.get("url", "")},
                                    {"text": "♾️ Повторить", "callback_data": f"repeatapi_{result.get('ID', '')}"}
                                ]
                            ]
                        }
                        success = await telegram_send_message(chat_id, msg, reply_markup)
                        if success:
                            logger.info(f"[TG] Auto-found note result for {chat_id}")
                        else:
                            logger.error(f"[TG] Failed to send auto-found note result to {chat_id}")
                    else:
                        success = await telegram_send_message(chat_id, f"По запросу '{text}' ничего не найдено 😢\n\nПопробуйте другие ноты или выберите режим поиска.")
                        if success:
                            logger.info(f"[TG] Sent auto-search not found to {chat_id}")
                        else:
                            logger.error(f"[TG] Failed to send auto-search not found to {chat_id}")
                else:
                    # Если не похоже на ноту, предлагаем выбрать режим
                    menu = {
                        "inline_keyboard": [
                            [{"text": "🐆 AI-Пантера", "callback_data": "ai"}],
                            [{"text": "🍓 Ноты", "callback_data": "instruction"}]
                        ]
                    }
                    success = await telegram_send_message(chat_id, "Выберите режим: 🐆 AI-Пантера или 🍓 Ноты", reply_markup=menu)
                    if success:
                        logger.info(f"[TG] Sent menu to {chat_id}")
                    else:
                        logger.error(f"[TG] Failed to send menu to {chat_id}")
                set_user_state(user_id, None)  # Сбрасываем состояние
                return {"ok": True}
            except Exception as e:
                logger.error(f"[TG] Exception in message processing: {e}\n{traceback.format_exc()}")
                try:
                    await telegram_send_message(chat_id, "Произошла ошибка при обработке сообщения. Попробуйте еще раз.")
                except:
                    logger.error("Failed to send error message to user")
                return {"ok": False, "error": str(e)}
                
        elif "callback_query" in update:
            print('[WEBHOOK] callback_query detected')
            callback = update["callback_query"]
            data = callback["data"]
            chat_id = callback["message"]["chat"]["id"]
            user_id = callback["from"]["id"]
            message_id = callback["message"]["message_id"]
            callback_id = callback["id"]
            logger.info(f"[TG] Callback: {data} from {user_id}")
            
            try:
                # Обновляем активность пользователя для callback'ов
                first_name = callback["from"].get("first_name")
                username = callback["from"].get("username")
                add_user_to_db(user_id, chat_id, first_name, username)
                
                if data == "instruction":
                    set_user_state(user_id, 'awaiting_note_search')
                    success = await telegram_edit_message(chat_id, message_id, '🍉 Напиши любую ноту (например, апельсин, клубника) — я найду ароматы с этой нотой!')
                    if success:
                        logger.info(f"[TG] Set state awaiting_note_search for {user_id}")
                    else:
                        logger.error(f"[TG] Failed to edit instruction message for {chat_id}")
                    await telegram_answer_callback_query(callback_id)
                    return {"ok": True}
                elif data == "ai":
                    set_user_state(user_id, 'awaiting_ai_question')
                    ai_greeting = greet()
                    
                    # Извлекаем ссылки из приветствия и создаем кнопки
                    buttons = extract_links_from_text(ai_greeting)
                    ai_greeting_clean = remove_html_links(ai_greeting)
                    
                    success = await telegram_edit_message(chat_id, message_id, ai_greeting_clean, buttons if buttons else None)
                    if success:
                        logger.info(f"[TG] Set state awaiting_ai_question for {user_id}")
                    else:
                        logger.error(f"[TG] Failed to edit ai greeting for {chat_id}")
                    await telegram_answer_callback_query(callback_id)
                    return {"ok": True}
                elif data.startswith("repeatapi_"):
                    aroma_id = data.split('_', 1)[1]
                    result = await search_by_id_api(aroma_id)
                    if result.get("status") == "success":
                        msg = f'✨ {result.get("brand")} {result.get("aroma")}\n\n{result.get("description")}'
                        # Добавляем кнопки обратно при повторном показе
                        reply_markup = {
                            "inline_keyboard": [
                                [
                                    {"text": "🚀 Подробнее", "url": result.get("url", "")},
                                    {"text": "♾️ Повторить", "callback_data": f"repeatapi_{result.get('ID', '')}"}
                                ]
                            ]
                        }
                        success = await telegram_edit_message(chat_id, message_id, msg, reply_markup)
                        if success:
                            logger.info(f"[TG] Edited repeatapi result for {chat_id}")
                        else:
                            logger.error(f"[TG] Failed to edit repeatapi result for {chat_id}")
                    else:
                        success = await telegram_edit_message(chat_id, message_id, "Ничего не найдено по этой ноте 😢")
                        if success:
                            logger.info(f"[TG] Edited repeatapi not found for {chat_id}")
                        else:
                            logger.error(f"[TG] Failed to edit repeatapi not found for {chat_id}")
                    await telegram_answer_callback_query(callback_id)
                    return {"ok": True}
                else:
                    success = await telegram_send_message(chat_id, "Callback обработан.")
                    if success:
                        logger.info(f"[TG] Sent generic callback to {chat_id}")
                    else:
                        logger.error(f"[TG] Failed to send generic callback to {chat_id}")
                    return {"ok": True}
            except Exception as e:
                logger.error(f"[TG] Exception in callback processing: {e}\n{traceback.format_exc()}")
                try:
                    await telegram_send_message(chat_id, "Произошла ошибка при обработке callback. Попробуйте еще раз.")
                except:
                    logger.error("Failed to send error message to user")
                return {"ok": False, "error": str(e)}
        else:
            print('[WEBHOOK] unknown update type')
            logger.warning("[TG] Unknown update type")
            return {"ok": False}
    except Exception as e:
        print(f'[WEBHOOK] Exception: {e}')
        logger.error(f"[TG] Exception in webhook: {e}\n{traceback.format_exc()}")
        # Не пытаемся отправлять сообщение пользователю здесь, так как у нас нет chat_id
        return {"ok": False, "error": str(e)}
print('=== [LOG] Эндпоинт webhook объявлен ===')

# --- Установка Telegram webhook ---
async def set_telegram_webhook(base_url: str):
    url = f"https://api.telegram.org/bot{TOKEN}/setWebhook"
    webhook_url = f"{base_url}{WEBHOOK_PATH}"
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, data={"url": webhook_url})
        logger.info(f"Set webhook response: {resp.text}")
        return resp.json()

# --- Эндпоинты FastAPI ---
@app.on_event("startup")
async def startup_event():
    logger.info("=== STARTUP EVENT ===")
    
    # Запускаем планировщик еженедельных сообщений
    start_weekly_scheduler()
    
    base_url = os.getenv("WEBHOOK_BASE_URL")
    if not base_url:
        logger.warning("WEBHOOK_BASE_URL не задан, webhook не будет установлен!")
        return
    try:
        result = await set_telegram_webhook(base_url)
        logger.info(f"Webhook set result: {result}")
    except Exception as e:
        logger.error(f"Failed to set webhook: {e}\n{traceback.format_exc()}")
    logger.info("=== STARTUP EVENT COMPLETE ===")

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("=== SHUTDOWN EVENT ===")
    logger.info("Application is shutting down gracefully...")
    logger.info("=== SHUTDOWN EVENT COMPLETE ===")

@app.get("/")
async def healthcheck():
    logger.info("Healthcheck requested")
    return PlainTextResponse("OK")

@app.post("/message")
async def handle_message(msg: MessageModel):
    user_id = msg.user_id
    text = msg.text.strip()
    ai_answer = await ask_chatgpt(text)
    ai_answer = ai_answer.replace('*', '')
    return JSONResponse({"answer": ai_answer, "parse_mode": "HTML"})

@app.post("/callback")
async def handle_callback(cb: CallbackModel):
    user_id = cb.user_id
    data = cb.data
    logger.info(f"[SUPERLOG] Callback data: {data}, user_id: {user_id}")
    try:
        if data != 'ai' and user_id in user_states:
            user_states.pop(user_id, None)
        if data == 'instruction':
            set_user_state(user_id, 'awaiting_note_search')
            return JSONResponse({"text": '🍉 Напиши любую ноту (например, апельсин, клубника) — я найду ароматы с этой нотой!'} )
        elif data == 'ai':
            set_user_state(user_id, 'awaiting_ai_question')
            result = greet()
            return JSONResponse({"text": result})
        elif data.startswith('repeatapi_'):
            aroma_id = data.split('_', 1)[1]
            result = await search_by_id_api(aroma_id)
            if result.get("status") == "success":
                return JSONResponse({
                    "brand": result.get("brand"),
                    "aroma": result.get("aroma"),
                    "description": result.get("description"),
                    "url": result.get("url"),
                    "aroma_id": result.get("ID")
                })
            else:
                return JSONResponse({"error": "Ничего не найдено по этой ноте 😢"})
        else:
            return JSONResponse({"info": "Callback обработан."})
    except Exception as e:
        logger.error(f"[SUPERLOG] Exception in handle_callback: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/start")
async def cmd_start(msg: MessageModel):
    logger.info(f"/start command from user {msg.user_id}")
    
    # Добавляем пользователя в базу данных (chat_id = user_id для API endpoint)
    add_user_to_db(msg.user_id, msg.user_id)
    
    text = (
        '<b>Здравствуйте!\n\n'
        'Я — ваш ароматный помощник от BAHUR.\n'
                                '🍓 Ищу ноты и 🐆 отвечаю на вопросы с любовью. ❤</b>'
    )
    return JSONResponse({"text": text, "parse_mode": "HTML"})

@app.post("/send-weekly-messages")
async def manual_weekly_send():
    """Ручной запуск еженедельной рассылки (для тестирования)"""
    try:
        await send_weekly_messages()
        return JSONResponse({"status": "success", "message": "Weekly messages sent"})
    except Exception as e:
        logger.error(f"Manual weekly send failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/users-stats")
async def get_users_stats():
    """Получить статистику пользователей"""
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        # Общее количество пользователей
        cursor.execute('SELECT COUNT(*) FROM users')
        total_users = cursor.fetchone()[0]
        
        # Активные пользователи
        cursor.execute('SELECT COUNT(*) FROM users WHERE is_active = 1')
        active_users = cursor.fetchone()[0]
        
        # Пользователи, добавленные за последнюю неделю
        week_ago = datetime.now() - timedelta(days=7)
        cursor.execute('SELECT COUNT(*) FROM users WHERE first_start_date > ?', (week_ago,))
        new_users_week = cursor.fetchone()[0]
        
        # Пользователи, которым нужно отправить еженедельное сообщение
        cursor.execute('''
            SELECT COUNT(*) FROM users 
            WHERE is_active = 1 AND (
                last_weekly_message IS NULL OR 
                last_weekly_message < ?
            )
        ''', (week_ago,))
        pending_weekly = cursor.fetchone()[0]
        
        conn.close()
        
        return JSONResponse({
            "total_users": total_users,
            "active_users": active_users,
            "new_users_this_week": new_users_week,
            "pending_weekly_messages": pending_weekly
        })
        
    except Exception as e:
        logger.error(f"Failed to get users stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/users-list")
async def get_users_list():
    """Получить список пользователей (только для администраторов)"""
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT user_id, chat_id, first_name, username, first_start_date, 
                   last_activity, last_weekly_message, is_active 
            FROM users 
            ORDER BY first_start_date DESC 
            LIMIT 100
        ''')
        
        users = []
        for row in cursor.fetchall():
            users.append({
                "user_id": row[0],
                "chat_id": row[1],
                "first_name": row[2],
                "username": row[3],
                "first_start_date": row[4],
                "last_activity": row[5],
                "last_weekly_message": row[6],
                "is_active": bool(row[7])
            })
        
        conn.close()
        return JSONResponse({"users": users})
        
    except Exception as e:
        logger.error(f"Failed to get users list: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# --- Endpoints для работы с Excel данными ---

@app.get("/products/search")
async def search_products_api(q: str, limit: int = 10):
    """Поиск товаров по названию бренда или аромата"""
    try:
        products = search_products(q, limit)
        return JSONResponse({
            "query": q,
            "count": len(products),
            "products": products
        })
    except Exception as e:
        logger.error(f"Search products error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/products/calculate-price")
async def calculate_price_api(brand: str, aroma: str, volume: float):
    """Рассчитать цену для конкретного товара и объема"""
    try:
        # Ищем товар
        query = f"{brand} {aroma}"
        products = search_products(query, limit=1)
        
        if not products:
            return JSONResponse({
                "error": f"Товар '{query}' не найден",
                "suggestions": search_products(brand, limit=3)
            }, status_code=404)
        
        product = products[0]
        price_info = calculate_price(product, volume)
        
        if not price_info:
            return JSONResponse({
                "error": "Не удалось рассчитать цену для указанного объема",
                "product": product
            }, status_code=400)
        
        # Добавляем описание к качеству
        quality_raw = product.get('Качество', 'N/A')
        quality_descriptions = {
            'TOP': 'TOP (высшее качество)',
            'Q1': 'Q1 (отличное качество)',
            'Q2': 'Q2 (хорошее качество)'
        }
        quality_with_desc = quality_descriptions.get(quality_raw, quality_raw)
        
        return JSONResponse({
            "product": {
                "brand": product.get('Бренд'),
                "aroma": product.get('Аромат'),
                "factory": product.get('Фабрика'),
                "quality": quality_with_desc
            },
            "price_calculation": price_info
        })
        
    except Exception as e:
        logger.error(f"Price calculation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/products/top")
async def get_top_products_api(
    factory: str = None, 
    quality: int = None, 
    sort_by: str = "TOP LAST", 
    limit: int = 10
):
    """Получить топ товары по популярности"""
    try:
        products = get_top_products(factory, quality, sort_by, limit)
        
        # Форматируем данные для API
        formatted_products = []
        quality_descriptions = {
            'TOP': 'TOP (высшее качество)',
            'Q1': 'Q1 (отличное качество)',
            'Q2': 'Q2 (хорошее качество)'
        }
        
        for product in products:
            quality_raw = product.get('Качество', 'N/A')
            quality_with_desc = quality_descriptions.get(quality_raw, quality_raw)
            
            formatted_products.append({
                "brand": product.get('Бренд'),
                "aroma": product.get('Аромат'),
                "factory": product.get('Фабрика'),
                "quality": quality_with_desc,
                "quality_code": product.get('Качество'),
                "prices": {
                    "30_49_ml": product.get('30 GR'),
                    "50_499_ml": product.get('50 GR'),
                    "500_999_ml": product.get('500 GR'),
                    "1000_plus_ml": product.get('1 KG')
                },
                "popularity": {
                    "last_6_months": float(product.get('TOP LAST', 0)) * 100,
                    "all_time": float(product.get('TOP ALL', 0)) * 100
                }
            })
        
        return JSONResponse({
            "filters": {
                "factory": factory,
                "quality": quality,
                "sort_by": sort_by
            },
            "count": len(formatted_products),
            "products": formatted_products
        })
        
    except Exception as e:
        logger.error(f"Get top products error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/products/stats")
async def get_products_stats():
    """Получить общую статистику по товарам"""
    try:
        global excel_data
        if excel_data is None:
            load_excel_data()
        
        if excel_data is None:
            raise HTTPException(status_code=500, detail="Excel data not available")
        
        # Статистика по фабрикам
        factory_stats = excel_data['Фабрика'].value_counts().to_dict()
        
        # Статистика по качеству
        quality_stats = excel_data['Качество'].value_counts().to_dict()
        
        # Ценовые диапазоны
        price_stats = {}
        for col in ['30 GR', '50 GR', '500 GR', '1 KG']:
            if col in excel_data.columns:
                prices = excel_data[col].dropna()
                if len(prices) > 0:
                    price_stats[col] = {
                        "min": float(prices.min()),
                        "max": float(prices.max()),
                        "avg": float(prices.mean()),
                        "count": len(prices)
                    }
        
        return JSONResponse({
            "total_products": len(excel_data),
            "factories": factory_stats,
            "qualities": quality_stats,
            "price_ranges": price_stats,
            "last_updated": datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Get products stats error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/products/reload")
async def reload_excel_data():
    """Перезагрузить данные из Excel файла"""
    try:
        df = load_excel_data()
        if df is not None:
            return JSONResponse({
                "status": "success",
                "message": "Excel data reloaded successfully",
                "products_count": len(df)
            })
        else:
            raise HTTPException(status_code=500, detail="Failed to reload Excel data")
    except Exception as e:
        logger.error(f"Reload Excel data error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# --- Для запуска: uvicorn 1:app --reload ---
if __name__ == "__main__":
    import signal
    
    def signal_handler(signum, frame):
        logger.info("Received shutdown signal, gracefully shutting down...")
        sys.exit(0)
    
    # Регистрируем обработчики сигналов
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    port = int(os.environ.get("PORT", 8000))
    print(f"[INFO] Starting uvicorn on 0.0.0.0:{port}")
    uvicorn.run("1:app", host="0.0.0.0", port=port)

def format_aroma_response_improved(product, include_prices=True):
    """Улучшенная функция форматирования ответа об аромате с правильными отступами"""
    try:
        brand = product.get('Бренд', 'N/A')
        aroma_raw = product.get('Аромат', 'N/A')
        aroma = format_aroma_name(aroma_raw)
        factory = product.get('Фабрика', 'N/A')
        quality = product.get('Качество', 'N/A')
        
        # Получаем ссылку (гиперссылка или обычная)
        hyperlink = product.get('Гиперссылка', '')
        link = product.get('Ссылка', '')
        aroma_url = ""
        
        if hyperlink and not pd.isna(hyperlink) and str(hyperlink).strip().startswith('http'):
            aroma_url = str(hyperlink).strip()
        elif link and not pd.isna(link) and str(link).strip().startswith('http'):
            aroma_url = str(link).strip()
        
        # Формируем ответ с правильными отступами
        response = ""
        
        # Название аромата
        if aroma_url:
            response += f"✨ <a href='{aroma_url}'>{brand} {aroma}</a>\n\n"
        else:
            response += f"✨ {brand} {aroma}\n\n"
        
        # Бренд и страна
        response += f"® Бренд: {brand}\n"
        country = product.get('Страна', '')
        country_emoji = get_country_emoji(country)
        if country and not pd.isna(country) and str(country).strip():
            response += f"{country_emoji} Страна: {str(country).strip()}\n"
        else:
            response += f"{country_emoji} Страна: Не указана\n"
        
        response += "\n"
        
        # Ноты (из прайса, не из API)
        top_notes = product.get('Верхние ноты', '')
        middle_notes = product.get('Средние ноты', '')
        base_notes = product.get('Базовые ноты', '')
        
        if top_notes and not pd.isna(top_notes) and str(top_notes).strip():
            response += f"🌱 Верхние ноты: {str(top_notes).strip()}\n"
        else:
            response += f"🌱 Верхние ноты: Не указаны\n"
            
        if middle_notes and not pd.isna(middle_notes) and str(middle_notes).strip():
            response += f"🌿 Средние ноты: {str(middle_notes).strip()}\n"
        else:
            response += f"🌿 Средние ноты: Не указаны\n"
            
        if base_notes and not pd.isna(base_notes) and str(base_notes).strip():
            response += f"🍃 Базовые ноты: {str(base_notes).strip()}\n"
        else:
            response += f"🍃 Базовые ноты: Не указаны\n"
        
        response += "\n"
        
        # Популярность
        top_last = product.get('TOP LAST', 0)
        top_all = product.get('TOP ALL', 0)
        if top_last and not pd.isna(top_last):
            response += f"⚡️ TOP LAST: {float(top_last):.2f}% (№{get_rank(product, get_top_products(sort_by='TOP LAST', limit=None), lambda p: p.get('TOP LAST', 0))})\n"
        if top_all and not pd.isna(top_all):
            response += f"🚀 TOP ALL: {float(top_all):.2f}% (№{get_rank(product, get_top_products(sort_by='TOP ALL', limit=None), lambda p: p.get('TOP ALL', 0))})\n"
        
        response += "\n"
        
        # VERSION (если есть варианты)
        aroma_name = product.get('Аромат', '')
        if aroma_name and not pd.isna(aroma_name):
            all_versions = [p for p in excel_data if p.get('Аромат', '').strip().lower() == aroma_name.strip().lower()]
            if len(all_versions) > 1:
                total_popularity = sum(p.get('TOP LAST', 0) for p in all_versions)
                if total_popularity > 0:
                    factory_stats = {}
                    for version in all_versions:
                        factory = version.get('Фабрика', '')
                        quality = version.get('Качество', '')
                        popularity = version.get('TOP LAST', 0)
                        key = f"{factory} {quality}"
                        if key not in factory_stats:
                            factory_stats[key] = 0
                        factory_stats[key] += popularity
                    
                    version_percents = []
                    for factory_key, popularity in factory_stats.items():
                        percent = (popularity / total_popularity) * 100
                        version_percents.append(f"{factory_key}: {percent:.2f}%")
                    
                    if version_percents:
                        response += f"♾️ VERSION: {' | '.join(version_percents)}\n\n"
        
        # Стоимость
        if include_prices:
            response += f"💵 Стоимость:\n"
            price_ranges = [
                ('30 GR', 30, '30 грамм'),
                ('50 GR', 50, '50 грамм'),
                ('500 GR', 500, '500 грамм'),
                ('1 KG', 1000, '1000 грамм')
            ]
            for col, volume, volume_text in price_ranges:
                price_per_g = product.get(col)
                if price_per_g and not pd.isna(price_per_g):
                    total_price = int(price_per_g * volume)
                    response += f"💧{volume_text} = {total_price}₽ ({price_per_g}₽ - за 1 грамм)\n"
        
        return response.strip()
        
    except Exception as e:
        logger.error(f"Error formatting aroma response: {e}")
        return f"❌ Ошибка форматирования данных о продукте"