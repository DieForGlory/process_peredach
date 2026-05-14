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
    status = DealStatus.query.get(deal_id)
    if not status:
        return None, None

    if status.notification_number:
        return status.notification_number, status.notification_date

    max_num = db.session.query(db.func.max(DealStatus.notification_number)).scalar() or 1000
    new_num = max_num + 1

    next_day = datetime.now().date() + timedelta(days=1)

    status.notification_number = new_num
    status.notification_date = next_day
    db.session.commit()

    return new_num, next_day

def generate_apartment_template(house_id: int):
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
    if 'Номер квартиры' not in df.columns or 'КадастроваяПлощадь' not in df.columns:
        return None
    df.dropna(subset=['КадастроваяПлощадь'], inplace=True)
    if df.empty:
        return {}
    df['Номер квартиры'] = df['Номер квартиры'].astype(str)
    return pd.Series(df.КадастроваяПлощадь.values, index=df['Номер квартиры']).to_dict()


def _parse_xonadon_format(df):
    print("\n--- Логирование: Начата обработка формата 'Xonadon/Хонадон' ---")
    cadastre_data = {}
    markers = []

    for idx, row in df.iterrows():
        row_str = ' '.join(row.dropna().astype(str))
        if re.search(r'(?i)(\d+)\s*-\s*(xonadon|хонадон)', row_str):
            markers.append({'index': idx, 'type': 'Xonadon', 'value': row_str})
        elif re.search(r'(?i)(zinapoya|ертўла|ертула)', row_str):
            markers.append({'index': idx, 'type': 'Zinapoya', 'value': row_str})

    if not markers:
        print("!!! Ошибка: Не найдено ни одной строки-заголовка с 'Xonadon' или 'Хонадон'.")
        return None

    print(f"Найдено {len(markers)} маркеров секций.")
    markers.append({'index': len(df), 'type': 'EOF', 'value': 'EOF'})

    for i in range(len(markers) - 1):
        current_marker = markers[i]
        next_marker = markers[i + 1]

        if current_marker['type'] == 'Xonadon':
            start_idx = current_marker['index']
            end_idx = next_marker['index'] - 1

            match = re.search(r'(\d+)', current_marker['value'])
            if not match:
                continue
            apartment_number = match.group(1)

            area_val = None
            for r_idx in range(start_idx + 1, end_idx + 1):
                row_vals = df.iloc[r_idx].astype(str).values
                row_str = ' '.join(row_vals)
                if re.search(r'(?i)(jami|жами)', row_str):
                    nums = [str(v) for v in row_vals if re.match(r'^\s*\d+([\.,]\d+)?\s*$', str(v))]
                    if nums:
                        area_val = nums[-1]
                    else:
                        non_empty = df.iloc[r_idx].dropna().values
                        if len(non_empty) > 0:
                            area_val = non_empty[-1]
                    break

            if area_val is None:
                try:
                    last_row = df.iloc[end_idx].dropna().values
                    if len(last_row) > 0:
                        area_val = last_row[-1]
                    else:
                        area_val = df.iloc[end_idx, 14]
                except IndexError:
                    pass

            try:
                if pd.isna(area_val) or str(area_val).strip() == '':
                    continue
                clean_val = re.sub(r'[^\d\.,]', '', str(area_val))
                area = float(clean_val.replace(',', '.'))
                cadastre_data[apartment_number] = area
                print(f"УСПЕХ: Для квартиры {apartment_number} сохранена площадь: {area}")
            except (ValueError, TypeError):
                continue

    print("\n----------------------------------------------------")
    print(f"ИТОГО: Успешно обработано {len(cadastre_data)} квартир из формата 'Xonadon/Хонадон'.")
    print(f"Результат: {cadastre_data}")
    print("--- Логирование: Конец обработки формата 'Xonadon' ---\n")
    return cadastre_data if cadastre_data else None


def parse_cadastre_excel(file_storage):
    try:
        df_template = pd.read_excel(file_storage)
        template_data = _parse_template_format(df_template.copy())
        if template_data:
            print("Обнаружен стандартный формат шаблона.")
            return template_data

        file_storage.seek(0)
        df_raw = pd.read_excel(file_storage, header=None)

        hisobi_data = _parse_hisobi_format(df_raw.copy())
        if hisobi_data:
            return hisobi_data

        xonadon_data = _parse_xonadon_format(df_raw.copy())
        if xonadon_data:
            return xonadon_data

        print("\n!!! КРИТИЧЕСКАЯ ОШИБКА: Не удалось определить формат файла.")
        return None

    except Exception as e:
        print(f"\n!!! КРИТИЧЕСКАЯ ОШИБКА при чтении файла: {e}")
        return None


def _parse_hisobi_format(df):
    print("\n--- Логирование: Начата обработка формата 'HISOBI' ---")
    cadastre_data = {}
    current_apartment = None

    for idx, row in df.iterrows():
        cell_val = str(row[5]) if pd.notna(row[5]) else ""
        match = re.search(r'(\d+)-(?:хонадон|xonadon)', cell_val, re.IGNORECASE)

        if match:
            current_apartment = match.group(1)
            print(f"Обнаружена квартира: {current_apartment}")
            continue

        if current_apartment:
            row_label = str(row[3]) if pd.notna(row[3]) else ""
            if "Жами:" in row_label or "Total:" in row_label:
                area_val = row[9]
                try:
                    if pd.notna(area_val):
                        area = float(str(area_val).replace(',', '.'))
                        cadastre_data[current_apartment] = area
                        print(f"УСПЕХ: Для кв {current_apartment} сохранена площадь: {area}")
                        current_apartment = None
                except (ValueError, TypeError) as e:
                    print(f"!!! ОШИБКА: Не удалось преобразовать площадь '{area_val}' для кв {current_apartment}")
                    continue

    print(f"ИТОГО: Обработано {len(cadastre_data)} квартир в формате 'HISOBI'.")
    return cadastre_data if cadastre_data else None

def generate_archive_for_group(deals: list, group_key: str):
    archive_buffer = io.BytesIO()
    report_data = []

    with zipfile.ZipFile(archive_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for deal in deals:
            doc_buffer = generate_single_document(deal, group_key)
            client_name_str = deal.get('client_name') or 'Client'
            safe_name = re.sub(r'[^\w\s-]', '', client_name_str)

            filename = f"{deal['property_id']}_{safe_name}.docx"
            zip_file.writestr(filename, doc_buffer.read())

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
    notif_id, notif_date = _get_or_create_notification_data(deal['deal_id'])

    if not notif_date:
        notif_date = datetime.now() + timedelta(days=1)

    agr_date_str = "___________"
    if deal.get('agreement_date'):
        agr_date_str = str(deal['agreement_date'])

    template_filename = 'readiness_template.docx'

    if group_key in ['3_debt_and_increase', '5_increase_only']:
        template_filename = 'increase_template.docx'
    elif group_key in ['4_debt_and_decrease', '6_decrease_only']:
        template_filename = 'decrease_template.docx'

    area_delta = abs(deal.get('area_diff', 0))

    context = {
        'notification_id': notif_id,
        'next_day': notif_date.day,
        'month': get_russian_month(notif_date.month),
        'year': notif_date.year,
        'client_fio': deal.get('client_name') or 'ФИО не указано',
        'client_adress': deal.get('client_address') or 'Адрес не указан',
        'house_adress': deal.get('complex_address') or deal.get('house_address') or 'Адрес дома не найден',
        'agreement_number': deal.get('agreement_number') or 'б/н',
        'agreement_date': agr_date_str,
        'complex_address': deal.get('complex_address') or 'Адрес не найден',
        'area_delta': f"{area_delta:.2f}"
    }

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