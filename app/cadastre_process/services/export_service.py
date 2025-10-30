# /app/cadastre_process/services/export_service.py
import io
import xlsxwriter


def _create_simple_checkerboard(workbook, sheet_name, checkerboard_data):
    """
    Создает простой лист шахматки (номер и площадь).
    Данные сгруппированы [section][floor] -> [apartments].
    """
    worksheet = workbook.add_worksheet(sheet_name)

    # Стили
    floor_format = workbook.add_format(
        {'bold': True, 'align': 'center', 'valign': 'vcenter', 'bg_color': '#e9ecef', 'border': 1})
    cell_format = workbook.add_format({'align': 'center', 'valign': 'vcenter', 'border': 1, 'text_wrap': True})
    # --- НОВЫЙ СТИЛЬ ДЛЯ ЗАГОЛОВКА ПОДЪЕЗДА ---
    section_header_format = workbook.add_format(
        {'bold': True, 'font_size': 14, 'align': 'center', 'valign': 'vcenter', 'bg_color': '#dee2e6', 'border': 1})

    # Ширина колонки этажа
    worksheet.set_column(0, 0, 10)

    row = 0
    # --- НАЧАЛО ОБНОВЛЕННОГО ЦИКЛА (СНАЧАЛА ПОДЪЕЗДЫ) ---
    for section, floors in checkerboard_data.items():  # sections - это OrderedDict

        # 1. Определяем макс. кол-во квартир для этого подъезда
        max_apartments = 0
        if floors:
            max_apartments = max(len(apts) for apts in floors.values()) if floors.values() else 0

        # 2. Пишем заголовок подъезда
        worksheet.set_row(row, 25)
        # Мержим ячейку на ширину (Этаж + макс. квартиры)
        if max_apartments > 0:
            worksheet.merge_range(row, 0, row, max_apartments, f'Подъезд {section}', section_header_format)
        else:
            worksheet.write(row, 0, f'Подъезд {section}', section_header_format)
        row += 1

        # 3. Пишем этажи и квартиры для этого подъезда
        for floor, apartments in floors.items():
            worksheet.set_row(row, 30)
            worksheet.write(row, 0, f'Этаж {floor}', floor_format)

            for col, deal in enumerate(apartments, start=1):
                content = f"{deal['property_id']}\n({deal['area']:.2f} м²)"
                worksheet.write(row, col, content, cell_format)
                worksheet.set_column(col, col, 12)  # Устанавливаем ширину

            row += 1

        # 4. Добавляем пустую строку-отступ
        row += 1
    # --- КОНЕЦ ОБНОВЛЕННОГО ЦИКЛА ---


def _create_diff_checkerboard(workbook, sheet_name, checkerboard_data):
    """
    Создает лист шахматки с расхождениями и цветовой индикацией.
    Данные сгруппированы [section][floor] -> [apartments].
    """
    worksheet = workbook.add_worksheet(sheet_name)

    # Стили
    floor_format = workbook.add_format(
        {'bold': True, 'align': 'center', 'valign': 'vcenter', 'bg_color': '#e9ecef', 'border': 1})
    base_cell_format = {'align': 'center', 'valign': 'vcenter', 'border': 1, 'text_wrap': True}
    green_bg = workbook.add_format({**base_cell_format, 'bg_color': '#d1e7dd'})
    red_bg = workbook.add_format({**base_cell_format, 'bg_color': '#f8d7da'})
    default_bg = workbook.add_format(base_cell_format)
    # --- НОВЫЙ СТИЛЬ ДЛЯ ЗАГОЛОВКА ПОДЪЕЗДА ---
    section_header_format = workbook.add_format(
        {'bold': True, 'font_size': 14, 'align': 'center', 'valign': 'vcenter', 'bg_color': '#dee2e6', 'border': 1})

    # Ширина и высота
    worksheet.set_column(0, 0, 10)

    row = 0
    # --- НАЧАЛО ОБНОВЛЕННОГО ЦИКЛА (СНАЧАЛА ПОДЪЕЗДЫ) ---
    for section, floors in checkerboard_data.items():  # sections - это OrderedDict

        # 1. Определяем макс. кол-во квартир для этого подъезда
        max_apartments = 0
        if floors:
            max_apartments = max(len(apts) for apts in floors.values()) if floors.values() else 0

        # 2. Пишем заголовок подъезда
        worksheet.set_row(row, 25)
        if max_apartments > 0:
            worksheet.merge_range(row, 0, row, max_apartments, f'Подъезд {section}', section_header_format)
        else:
            worksheet.write(row, 0, f'Подъезд {section}', section_header_format)
        row += 1

        # 3. Пишем этажи и квартиры для этого подъезда
        for floor, apartments in floors.items():
            worksheet.set_row(row, 30)
            worksheet.write(row, 0, f'Этаж {floor}', floor_format)

            for col, deal in enumerate(apartments, start=1):
                diff = deal['area_diff']
                content = f"{deal['property_id']}\n({diff:+.2f})"

                cell_format = default_bg
                if diff > 0.1:
                    cell_format = green_bg
                elif diff < -0.1:
                    cell_format = red_bg

                worksheet.write(row, col, content, cell_format)
                worksheet.set_column(col, col, 12)  # Устанавливаем ширину

            row += 1

        # 4. Добавляем пустую строку-отступ
        row += 1
    # --- КОНЕЦ ОБНОВЛЕННОГО ЦИКЛА ---


def generate_checkerboard_excel(diff_data, file_data, db_data):
    """Создает Excel-файл с тремя листами: расхождения, данные из файла, данные из БД."""
    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output, {'in_memory': True})

    # Создаем три листа
    _create_diff_checkerboard(workbook, '1. Расхождения', diff_data)
    _create_simple_checkerboard(workbook, '2. Данные из файла', file_data)
    _create_simple_checkerboard(workbook, '3. Данные из БД', db_data)

    workbook.close()
    output.seek(0)
    return output