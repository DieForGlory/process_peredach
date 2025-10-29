# /app/cadastre_process/services/export_service.py
import io
import xlsxwriter


def _create_simple_checkerboard(workbook, sheet_name, checkerboard_data):
    """Вспомогательная функция для создания простого листа шахматки (номер и площадь)."""
    worksheet = workbook.add_worksheet(sheet_name)

    # Стили
    floor_format = workbook.add_format(
        {'bold': True, 'align': 'center', 'valign': 'vcenter', 'bg_color': '#e9ecef', 'border': 1})
    cell_format = workbook.add_format({'align': 'center', 'valign': 'vcenter', 'border': 1, 'text_wrap': True})

    # Ширина колонок
    worksheet.set_column(0, 0, 10)
    max_apartments = max(len(apts) for apts in checkerboard_data.values()) if checkerboard_data else 0
    if max_apartments > 0:
        worksheet.set_column(1, max_apartments, 12)

    # Запись данных
    row = 0
    for floor, apartments in checkerboard_data.items():
        worksheet.set_row(row, 30)
        worksheet.write(row, 0, f'Этаж {floor}', floor_format)
        for col, deal in enumerate(apartments, start=1):
            content = f"{deal['property_id']}\n({deal['area']:.2f} м²)"
            worksheet.write(row, col, content, cell_format)
        row += 1


def _create_diff_checkerboard(workbook, sheet_name, checkerboard_data):
    """Создает лист шахматки с расхождениями и цветовой индикацией."""
    worksheet = workbook.add_worksheet(sheet_name)

    # Стили
    floor_format = workbook.add_format(
        {'bold': True, 'align': 'center', 'valign': 'vcenter', 'bg_color': '#e9ecef', 'border': 1})
    base_cell_format = {'align': 'center', 'valign': 'vcenter', 'border': 1, 'text_wrap': True}
    green_bg = workbook.add_format({**base_cell_format, 'bg_color': '#d1e7dd'})
    red_bg = workbook.add_format({**base_cell_format, 'bg_color': '#f8d7da'})
    default_bg = workbook.add_format(base_cell_format)

    # Ширина и высота
    worksheet.set_column(0, 0, 10)
    max_apartments = max(len(apts) for apts in checkerboard_data.values()) if checkerboard_data else 0
    if max_apartments > 0:
        worksheet.set_column(1, max_apartments, 12)

    # Запись данных
    row = 0
    for floor, apartments in checkerboard_data.items():
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
        row += 1


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