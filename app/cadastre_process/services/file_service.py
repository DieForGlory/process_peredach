# app/cadastre_process/services/file_service.py

import pandas as pd
import io
import docx
import zipfile
import re
from .data_service import get_apartments_for_house


def generate_apartment_template(house_id: int):
    """Создает Excel-шаблон на основе данных из БД."""
    apartments_result = get_apartments_for_house(house_id)
    if not apartments_result:
        return None

    apartments = [row.geo_flatnum for row in apartments_result]
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


def generate_archive_for_group(deals: list, group_key: str):
    """Создает ZIP-архив с Word-документами."""
    # Тексты уведомлений
    notification_texts = {
        '1_no_issues': "Уважаемый(ая) {client_name}, по вашей квартире №{apartment_id} нет расхождений по площади и отсутствуют задолженности. Приглашаем вас для получения ключей.",
        '2_debt_only': "Уважаемый(ая) {client_name}, по вашей квартире №{apartment_id} нет расхождений по площади, однако имеется задолженность. Просим вас погасить её перед получением ключей.",
        # ... добавьте тексты для остальных групп
    }
    default_text = "Уведомление для клиента {client_name} по квартире №{apartment_id}."
    notification_template = notification_texts.get(group_key, default_text)

    archive_buffer = io.BytesIO()
    with zipfile.ZipFile(archive_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for deal in deals:
            doc = docx.Document()
            doc.add_paragraph(notification_template.format(
                client_name=deal.get('client_name', 'Клиент'),
                apartment_id=deal['property_id']
            ))
            doc_buffer = io.BytesIO()
            doc.save(doc_buffer)
            doc_buffer.seek(0)
            zip_file.writestr(f"{deal['property_id']}.docx", doc_buffer.read())

    archive_buffer.seek(0)
    return archive_buffer


def generate_single_document(deal: dict, group_key: str):
    """
    Создает один Word-документ в памяти для конкретной сделки.
    """
    notification_texts = {
        '1_no_issues': "Уважаемый(ая) {client_name}, по вашей квартире №{apartment_id} нет расхождений по площади и отсутствуют задолженности. Приглашаем вас для получения ключей.",
        '2_debt_only': "Уважаемый(ая) {client_name}, по вашей квартире №{apartment_id} нет расхождений по площади, однако имеется задолженность. Просим вас погасить её перед получением ключей.",
        '3_debt_and_increase': "Уважаемый(ая) {client_name}, по вашей квартире №{apartment_id} имеется задолженность и зафиксировано увеличение площади более чем на 2 кв.м. Просим вас обратиться в офис для проведения доплаты и получения ключей.",
        '4_debt_and_decrease': "Уважаемый(ая) {client_name}, по вашей квартире №{apartment_id} имеется задолженность и зафиксировано уменьшение площади более чем на 2 кв.м. Просим вас обратиться в офис для проведения взаиморасчетов и получения ключей.",
        '5_increase_only': "Уважаемый(ая) {client_name}, по вашей квартире №{apartment_id} отсутствуют задолженности, но зафиксировано увеличение площади более чем на 2 кв.м. Просим вас обратиться в офис для проведения доплаты и получения ключей.",
        '6_decrease_only': "Уважаемый(ая) {client_name}, по вашей квартире №{apartment_id} отсутствуют задолженности, но зафиксировано уменьшение площади более чем на 2 кв.м. Просим вас обратиться в офис для проведения взаиморасчетов и получения ключей.",
    }
    default_text = "Уведомление для клиента {client_name} по квартире №{apartment_id}."
    notification_template = notification_texts.get(group_key, default_text)

    doc = docx.Document()
    doc.add_paragraph(notification_template.format(
        client_name=deal.get('client_name', 'Клиент'),
        apartment_id=deal['property_id']
    ))

    doc_buffer = io.BytesIO()
    doc.save(doc_buffer)
    doc_buffer.seek(0)
    return doc_buffer