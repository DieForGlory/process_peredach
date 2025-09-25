# /app/cadastre_process/services/export_service.py
import io
import xlsxwriter


def generate_checkerboard_excel(checkerboard_data: dict):
    """
    Создает Excel-файл с шахматкой и форматированием на основе данных.
    """
    output = io.BytesIO()
    # Создаем Excel-книгу в памяти
    workbook = xlsxwriter.Workbook(output, {'in_memory': True})
    worksheet = workbook.add_worksheet('Шахматка')

    # --- Определяем стили форматирования ---
    # Стиль для ячейки с номером этажа
    floor_label_format = workbook.add_format({
        'bold': True, 'align': 'center', 'valign': 'vcenter',
        'bg_color': '#e9ecef', 'border': 1
    })
    # Базовый стиль для ячеек с квартирами
    cell_format = {
        'align': 'center', 'valign': 'vcenter',
        'border': 1, 'text_wrap': True
    }
    # Стили для фона в зависимости от расхождения
    green_bg = {'bg_color': '#d1e7dd'}  # Положительное расхождение
    red_bg = {'bg_color': '#f8d7da'}  # Отрицательное расхождение

    # --- Настраиваем ширину и высоту колонок/строк ---
    worksheet.set_column(0, 0, 10)  # Ширина колонки "Этаж"
    max_apartments = max(len(apts) for apts in checkerboard_data.values()) if checkerboard_data else 0
    if max_apartments > 0:
        worksheet.set_column(1, max_apartments, 12)  # Ширина колонок квартир

    # --- Записываем данные в ячейки ---
    row = 0
    for floor, apartments in checkerboard_data.items():
        worksheet.set_row(row, 30)  # Высота строки
        worksheet.write(row, 0, f'Этаж {floor}', floor_label_format)

        for col, deal in enumerate(apartments, start=1):
            diff = deal['area_diff']
            content = f"{deal['property_id']}\n({diff:+.2f})"  # Формируем текст ячейки

            # Выбираем фон и записываем данные
            current_format_props = cell_format.copy()
            if diff > 0.1:
                current_format_props.update(green_bg)
            elif diff < -0.1:
                current_format_props.update(red_bg)

            final_format = workbook.add_format(current_format_props)
            worksheet.write(row, col, content, final_format)
        row += 1

    workbook.close()
    output.seek(0)  # "Перематываем" файл в начало
    return output