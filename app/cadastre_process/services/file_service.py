# app/cadastre_process/services/file_service.py

import pandas as pd
import io
import docx
import zipfile
from .data_service import get_apartments_for_house  # Импортируем из соседнего файла


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


def parse_cadastre_excel(file_storage):
    """Читает заполненный пользователем шаблон."""
    try:
        df = pd.read_excel(file_storage)
        if 'Номер квартиры' not in df.columns or 'КадастроваяПлощадь' not in df.columns:
            return None
        df.dropna(subset=['КадастроваяПлощадь'], inplace=True)
        df['Номер квартиры'] = df['Номер квартиры'].astype(str)
        return pd.Series(df.КадастроваяПлощадь.values, index=df['Номер квартиры']).to_dict()
    except Exception as e:
        print(f"Ошибка при чтении Excel файла: {e}")
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
    # Тексты уведомлений (эта логика дублируется, в будущем ее можно вынести)
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