# app/cadastre_process/services/file_service.py

import pandas as pd
import io
import docx
import zipfile
import re
from .data_service import get_apartments_for_house
from docxtpl import DocxTemplate
import os
from datetime import datetime, timedelta
from flask import current_app
from app import db
from ..models import DealStatus

def get_russian_month(month_num):
    months = [
        'января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
        'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря'
    ]
    return months[month_num - 1]


def _get_or_create_notification_data(deal_id):
    """
    Генерирует или возвращает существующий номер уведомления и дату.
    Гарантирует, что номер не изменится при повторном скачивании.
    """
    status = DealStatus.query.get(deal_id)
    if not status:
        return None, None

    # Если номер уже есть, возвращаем его
    if status.notification_number:
        return status.notification_number, status.notification_date

    # Если номера нет, генерируем новый
    # Простой способ генерации уникального номера: Берем максимальный существующий + 1
    max_num = db.session.query(db.func.max(DealStatus.notification_number)).scalar() or 1000  # Стартуем с 1000
    new_num = max_num + 1

    # Дата - завтрашний день
    next_day = datetime.now().date() + timedelta(days=1)

    status.notification_number = new_num
    status.notification_date = next_day
    db.session.commit()

    return new_num, next_day
def generate_apartment_template(house_id: int):
    """Создает Excel-шаблон на основе данных из БД."""
    apartments_result = get_apartments_for_house(house_id)
    if not apartments_result:
        return None

    apartments = [row.geo_flatnum_postoffice for row in apartments_result]
    df = pd.DataFrame({'Номер квартиры': apartments, 'КадастроваяПлощадь': ''})

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Кадастр')
        worksheet = writer.sheets['Кадастр']
        worksheet.set_column('A:A', 20)
        worksheet.set_column('B:B', 25)
    output.seek(0)
    return output


def _parse_template_format(df):
    """Разбирает стандартный формат шаблона."""
    if 'Номер квартиры' not in df.columns or 'КадастроваяПлощадь' not in df.columns:
        return None
    df.dropna(subset=['КадастроваяПлощадь'], inplace=True)
    if df.empty:
        return {}
    df['Номер квартиры'] = df['Номер квартиры'].astype(str)
    return pd.Series(df.КадастроваяПлощадь.values, index=df['Номер квартиры']).to_dict()


def _parse_xonadon_format(df):
    """Разбирает формат с заголовками 'X-Xonadon', включая промежуточные блоки 'Zinapoya'."""
    print("\n--- Логирование: Начата обработка формата 'Xonadon' ---")
    cadastre_data = {}

    # --- ИЗМЕНЕННАЯ ЛОГИКА ---
    # 1. Находим все маркеры секций (Xonadon, Zinapoya) и их индексы
    markers = []
    for idx, value in df[0].astype(str).dropna().items():
        if 'Xonadon' in value:
            markers.append({'index': idx, 'type': 'Xonadon', 'value': value})
        elif 'Zinapoya' in value:
            markers.append({'index': idx, 'type': 'Zinapoya', 'value': value})

    if not markers:
        print("!!! Ошибка: Не найдено ни одной строки-заголовка с 'Xonadon'.")
        return None

    print(f"Найдено {len(markers)} маркеров секций.")

    # 2. Добавляем фиктивный маркер конца файла, чтобы обработать последний блок
    markers.append({'index': len(df), 'type': 'EOF', 'value': 'EOF'})

    # 3. Итерируемся по маркерам для определения границ
    for i in range(len(markers) - 1):
        current_marker = markers[i]
        next_marker = markers[i + 1]

        # Нас интересуют только блоки, которые начинаются с 'Xonadon'
        if current_marker['type'] == 'Xonadon':
            start_idx = current_marker['index']
            end_idx = next_marker['index'] - 1  # Конец блока - строка перед следующим маркером

            print(f"\n--- Обработка блока '{current_marker['value']}' (строки с {start_idx} по {end_idx}) ---")

            # Извлекаем номер квартиры из заголовка
            header_text = current_marker['value']
            match = re.match(r'(\d+)', header_text)
            if not match:
                print(f"!!! Предупреждение: Не удалось извлечь номер квартиры из заголовка: '{header_text}'")
                continue
            apartment_number = match.group(1)
            print(f"Из заголовка '{header_text}' извлечен номер квартиры: {apartment_number}")

            # Площадь находится в последней строке блока, в колонке O (индекс 14)
            area_val = df.iloc[end_idx, 14]
            print(
                f"Для квартиры {apartment_number} ищем площадь в строке {end_idx + 1}, колонка O. Найдено значение: '{area_val}'")

            try:
                if pd.isna(area_val):
                    print(
                        f"!!! Предупреждение: Пропускаем квартиру {apartment_number}, так как значение площади пустое.")
                    continue

                if isinstance(area_val, str):
                    area = float(area_val.replace(',', '.'))
                else:
                    area = float(area_val)
                cadastre_data[apartment_number] = area
                print(f"УСПЕХ: Для квартиры {apartment_number} сохранена площадь: {area}")
            except (ValueError, TypeError) as e:
                print(
                    f"!!! ОШИБКА: Не удалось преобразовать значение площади '{area_val}' для квартиры {apartment_number}. Ошибка: {e}")
                continue
    # --- КОНЕЦ ИЗМЕНЕННОЙ ЛОГИКИ ---

    print("\n----------------------------------------------------")
    print(f"ИТОГО: Успешно обработано {len(cadastre_data)} квартир из формата 'Xonadon'.")
    print(f"Результат: {cadastre_data}")
    print("--- Логирование: Конец обработки формата 'Xonadon' ---\n")
    return cadastre_data if cadastre_data else None


def parse_cadastre_excel(file_storage):
    """
    Определяет формат Excel-файла и разбирает его.
    Поддерживает стандартный шаблон и новый формат с 'Xonadon'.
    """
    try:
        # 1. Попытка разбора как стандартный шаблон
        df_template = pd.read_excel(file_storage)
        template_data = _parse_template_format(df_template.copy())
        if template_data is not None and template_data:
            print("Обнаружен и успешно обработан стандартный формат шаблона.")
            return template_data
        else:
            print("Стандартный шаблон не распознан или пуст. Переход к следующему формату.")

        file_storage.seek(0)

        # 2. Попытка разбора как формат 'Xonadon'
        df_new = pd.read_excel(file_storage, header=None)
        new_format_data = _parse_xonadon_format(df_new)
        if new_format_data is not None:
            return new_format_data

        print("\n!!! КРИТИЧЕСКАЯ ОШИБКА: Не удалось определить формат файла или извлечь данные.")
        return None

    except Exception as e:
        print(f"\n!!! КРИТИЧЕСКАЯ ОШИБКА при чтении Excel файла: {e}")
        return None


# app/cadastre_process/services/file_service.py

def generate_archive_for_group(deals: list, group_key: str):
    """
    Создает ZIP-архив с уведомлениями + Excel-отчет для проверки данных.
    """
    archive_buffer = io.BytesIO()

    # Список для сбора данных отчета
    report_data = []

    with zipfile.ZipFile(archive_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for deal in deals:
            # 1. Генерируем сам документ Word
            doc_buffer = generate_single_document(deal, group_key)

            # --- ИСПРАВЛЕНИЕ ЗДЕСЬ ---
            # Используем "or 'Client'", чтобы обработать случай, когда client_name=None
            client_name_str = deal.get('client_name') or 'Client'
            safe_name = re.sub(r'[^\w\s-]', '', client_name_str)

            filename = f"{deal['property_id']}_{safe_name}.docx"

            # Записываем Word в архив
            zip_file.writestr(filename, doc_buffer.read())

            # 2. Собираем данные для отчета
            report_data.append({
                'Deal ID': deal.get('deal_id'),
                'Квартира': deal.get('property_id'),
                'ФИО Клиента': deal.get('client_name'),
                'Номер договора': deal.get('agreement_number'),
                'Дата договора': deal.get('agreement_date'),
                'Адрес клиента (исходный)': deal.get('client_address'),
                'Адрес дома (исходный)': deal.get('house_address'),
                'Полный адрес (сборный)': deal.get('complex_address'),
                'Разница площади': deal.get('area_diff'),
                'Сумма доплаты/возврата': deal.get('area_increase_payment_amount') or 0
            })

        # 3. Генерируем Excel-файл с отчетом
        if report_data:
            df = pd.DataFrame(report_data)
            excel_buffer = io.BytesIO()

            with pd.ExcelWriter(excel_buffer, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False, sheet_name='DataCheck')

                worksheet = writer.sheets['DataCheck']
                for i, col in enumerate(df.columns):
                    max_len = max(
                        df[col].astype(str).map(len).max(),
                        len(col)
                    ) + 2
                    worksheet.set_column(i, i, max_len)

            excel_buffer.seek(0)
            zip_file.writestr(f"CHECK_REPORT_{group_key}.xlsx", excel_buffer.read())

    archive_buffer.seek(0)
    return archive_buffer


def generate_single_document(deal: dict, group_key: str):
    """
    Выбирает шаблон в зависимости от группы и генерирует документ.
    """
    # 1. Получаем строгие данные уведомления
    notif_id, notif_date = _get_or_create_notification_data(deal['deal_id'])

    if not notif_date:
        notif_date = datetime.now() + timedelta(days=1)

    agr_date_str = "___________"
    if deal.get('agreement_date'):
        agr_date_str = str(deal['agreement_date'])

    # 2. Определяем имя шаблона
    template_filename = 'readiness_template.docx'

    if group_key in ['3_debt_and_increase', '5_increase_only']:
        template_filename = 'increase_template.docx'
    elif group_key in ['4_debt_and_decrease', '6_decrease_only']:
        template_filename = 'decrease_template.docx'

    # 3. Подготавливаем контекст
    area_delta = abs(deal.get('area_diff', 0))

    context = {
        'notification_id': notif_id,
        'next_day': notif_date.day,
        'month': get_russian_month(notif_date.month),
        'year': notif_date.year,
        'client_fio': deal.get('client_name') or 'ФИО не указано',
        'client_adress': deal.get('client_address') or 'Адрес не указан',
        # Для переменной house_adress в шаблоне (старый шаблон готовности) можем оставить просто geo_house или полный
        'house_adress': deal.get('complex_address') or deal.get('house_address') or 'Адрес дома не найден',

        'agreement_number': deal.get('agreement_number') or 'б/н',
        'agreement_date': agr_date_str,

        # --- ИСПОЛЬЗУЕМ НОВОЕ ПОЛЕ ДЛЯ ПЕРЕМЕННОЙ В ШАБЛОНЕ ---
        'complex_address': deal.get('complex_address') or 'Адрес не найден',

        'area_delta': f"{area_delta:.2f}"
    }

    # 4. Загружаем шаблон
    template_path = os.path.join(current_app.root_path, 'templates', 'docx', template_filename)

    try:
        doc = DocxTemplate(template_path)
        doc.render(context)

        doc_buffer = io.BytesIO()
        doc.save(doc_buffer)
        doc_buffer.seek(0)
        return doc_buffer
    except Exception as e:
        print(f"Ошибка генерации документа ({template_filename}): {e}")
        return io.BytesIO()