import math
import os
from datetime import datetime, timedelta
from flask import (
    render_template, request, flash, redirect, url_for, send_file, session, jsonify
)
from werkzeug.utils import secure_filename
from collections import defaultdict # Убедитесь, что этот импорт есть
from .services.export_service import generate_checkerboard_excel
from . import cadastre_bp
from .services.data_service import (
    get_complexes_and_houses, get_single_deal_details,
    update_deal_status, get_statuses_for_deals
)
from .services.file_service import (
    parse_cadastre_excel, generate_apartment_template,
    generate_archive_for_group, generate_single_document
)
from .services.processing_service import process_cadastre_data
from .workflows.group_1_workflow import generate_unilateral_act
from collections import defaultdict
UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)


@cadastre_bp.route('/', methods=['GET'])
def upload_page():
    houses_data = get_complexes_and_houses()
    return render_template('upload.html', houses_data=houses_data)


@cadastre_bp.route('/download-checkerboard')
def download_checkerboard():
    """Готовит данные для 3-х шахматок и отдает Excel-файл."""
    categorized_results = session.get('categorized_results')
    raw_cadastre_data = session.get('raw_cadastre_data')  # Получаем сырые данные

    if not categorized_results or not raw_cadastre_data:
        flash('Данные для генерации файла не найдены...', 'warning')
        return redirect(url_for('cadastre_process.upload_page'))

    # --- ГОТОВИМ ДАННЫЕ ДЛЯ ВСЕХ ШАХМАТОК ---

    # 1. Собираем все сделки и создаем карту "квартира -> этаж"
    all_deals = [deal for deals_in_group in categorized_results.values() for deal in deals_in_group]
    floor_map = {str(d['property_id']): d.get('floor') or 'N/A' for d in all_deals}

    # 2. Готовим данные для шахматки "Расхождения" (как и раньше)
    diff_checkerboard = defaultdict(list)
    for deal in all_deals:
        diff_checkerboard[deal.get('floor') or 'N/A'].append(deal)

    # 3. Готовим данные для шахматки "Данные из файла"
    file_checkerboard = defaultdict(list)
    for prop_id, area in raw_cadastre_data.items():
        floor = floor_map.get(str(prop_id), 'N/A')
        file_checkerboard[floor].append({'property_id': prop_id, 'area': area})

    # 4. Готовим данные для шахматки "Данные из БД"
    db_checkerboard = defaultdict(list)
    for deal in all_deals:
        # Используем contract_area, которая уже содержит правильную площадь из БД
        db_checkerboard[deal.get('floor') or 'N/A'].append({
            'property_id': deal['property_id'],
            'area': deal.get('contract_area', 0)
        })

    # --- СОРТИРОВКА ВСЕХ ШАХМАТОК ---
    def sort_checkerboard(data):
        for floor in data:
            try:
                data[floor].sort(key=lambda x: int(x['property_id']))
            except ValueError:
                data[floor].sort(key=lambda x: x['property_id'])

        sorted_floors = sorted(
            data.keys(),
            key=lambda x: (isinstance(x, str), -float(x) if isinstance(x, (int, float)) else 0),
            reverse=False
        )
        return {floor: data[floor] for floor in sorted_floors}

    # --- ВЫЗЫВАЕМ ФУНКЦИЮ ЭКСПОРТА С ТРЕМЯ НАБОРАМИ ДАННЫХ ---
    excel_buffer = generate_checkerboard_excel(
        sort_checkerboard(diff_checkerboard),
        sort_checkerboard(file_checkerboard),
        sort_checkerboard(db_checkerboard)
    )

    return send_file(
        excel_buffer,
        as_attachment=True,
        download_name='checkerboard_report.xlsx',  # Дал файлу более осмысленное имя
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

@cadastre_bp.route('/process-upload', methods=['POST'])
def process_upload():
    """
    Обрабатывает загруженный пользователем файл, сохраняет результат в сессию
    и перенаправляет на страницу со списком сделок.
    """
    if 'cadastre_file' not in request.files or not request.form.get('house_id'):
        flash('Не все поля заполнены. Выберите дом и файл.', 'danger')
        return redirect(url_for('cadastre_process.upload_page'))

    file = request.files['cadastre_file']
    house_id = request.form.get('house_id')

    if file.filename == '':
        flash('Файл не выбран', 'danger')
        return redirect(url_for('cadastre_process.upload_page'))

    cadastre_data = parse_cadastre_excel(file)
    if cadastre_data is None:
        flash('Ошибка чтения Excel файла. Убедитесь, что вы загружаете корректно заполненный шаблон.', 'danger')
        return redirect(url_for('cadastre_process.upload_page'))

    results = process_cadastre_data(cadastre_data, house_id)

    session['raw_cadastre_data'] = cadastre_data
    session['categorized_results'] = results
    return redirect(url_for('cadastre_process.show_results'))


@cadastre_bp.route('/results')
def show_results():
    """Отображает страницу с первоначальной категоризацией (для справки)."""
    results = session.get('categorized_results')
    if not results:
        flash('Нет данных для отображения. Пожалуйста, загрузите файл заново.', 'info')
        return redirect(url_for('cadastre_process.upload_page'))

    # --- НОВЫЙ КОД ДЛЯ ПОДГОТОВКИ ДАННЫХ ---
    all_deals = [deal for deals_in_group in results.values() for deal in deals_in_group]
    total_apartments = len(all_deals)

    checkerboard_data = defaultdict(list)
    for deal in all_deals:
        floor = deal.get('floor') or 'N/A'  # Группируем квартиры без этажа в отдельную категорию
        checkerboard_data[floor].append(deal)

    # Сортируем квартиры внутри каждого этажа по номеру
    for floor in checkerboard_data:
        # Пытаемся сортировать номера как числа, если не получается - как строки
        try:
            checkerboard_data[floor].sort(key=lambda x: int(x['property_id']))
        except ValueError:
            checkerboard_data[floor].sort(key=lambda x: x['property_id'])

    # Сортируем сами этажи (сначала числовые по убыванию, потом 'N/A')
    sorted_floors = sorted(
        checkerboard_data.keys(),
        key=lambda x: (isinstance(x, str), -float(x) if isinstance(x, (int, float)) else 0),
        reverse=False
    )

    sorted_checkerboard = {floor: checkerboard_data[floor] for floor in sorted_floors}
    # --- КОНЕЦ НОВОГО КОДА ---

    return render_template(
        'results.html',
        results=results,
        total_apartments=total_apartments,
        checkerboard=sorted_checkerboard
    )


@cadastre_bp.route('/deals')
def deals_list():
    PER_PAGE = 20
    page = request.args.get('page', 1, type=int)

    categorized_results = session.get('categorized_results', {})
    if not categorized_results:
        flash('Нет обработанных данных для отображения. Пожалуйста, загрузите файл.', 'info')
        return redirect(url_for('cadastre_process.upload_page'))

    all_deals_unfiltered = []
    for group_key, deals_in_group in categorized_results.items():
        for deal in deals_in_group:
            deal['group_key'] = group_key
            all_deals_unfiltered.append(deal)

    # --- ИСПРАВЛЕННЫЙ БЛОК ФИЛЬТРАЦИИ ---
    # Теперь мы отбираем в список все квартиры, у которых есть ID сделки.
    # Это гораздо надежнее, чем фильтровать по текстовому статусу.
    all_deals = [
        d for d in all_deals_unfiltered
        if d.get('deal_id') is not None
    ]
    # --- КОНЕЦ ИСПРАВЛЕННОГО БЛОКА ---

    all_deal_ids = [d['deal_id'] for d in all_deals]
    statuses_map = get_statuses_for_deals(all_deal_ids)

    for deal in all_deals:
        status_obj = statuses_map.get(deal['deal_id'])
        deal['status_obj'] = status_obj
        deal['is_timed_out'] = False
        deal['deadline_iso'] = None
        if status_obj and status_obj.documents_delivered_at:
            deadline = status_obj.documents_delivered_at + timedelta(days=30)
            deal['is_timed_out'] = datetime.utcnow() > deadline
            deal['deadline_iso'] = deadline.isoformat()

    active_group_filter = request.args.get('group_key', '')
    if active_group_filter:
        filtered_deals = [d for d in all_deals if d.get('group_key') == active_group_filter]
    else:
        filtered_deals = all_deals

    total_deals = len(filtered_deals)
    start = (page - 1) * PER_PAGE
    end = start + PER_PAGE
    deals_for_page = filtered_deals[start:end]
    total_pages = math.ceil(total_deals / PER_PAGE)

    group_names = {
        '1_no_issues': '1) Без обременений', '2_debt_only': '2) С долгом, без изм. площади',
        '3_debt_and_increase': '3) С долгом, с увел. площади', '4_debt_and_decrease': '4) С долгом, с уменьш. площади',
        '5_increase_only': '5) Без долга, с увел. площади', '6_decrease_only': '6) Без долга, с уменьш. площади',
    }

    return render_template(
        'deals_list.html',
        deals=deals_for_page,
        group_names=group_names,
        active_group_filter=active_group_filter,
        current_page=page,
        total_pages=total_pages
    )


@cadastre_bp.route('/download-template/<int:house_id>')
def download_template(house_id):
    excel_buffer = generate_apartment_template(house_id)
    if excel_buffer is None:
        flash('Не удалось сгенерировать шаблон: в выбранном доме нет квартир с активными сделками.', 'warning')
        return redirect(url_for('cadastre_process.upload_page'))

    return send_file(
        excel_buffer, as_attachment=True,
        download_name=f'template_house_{house_id}.xlsx',
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )


@cadastre_bp.route('/download-archive/<group_key>')
def download_archive(group_key):
    results = session.get('categorized_results')
    if not results or group_key not in results:
        flash('Данные для генерации архива не найдены или сессия истекла.', 'danger')
        return redirect(url_for('cadastre_process.upload_page'))

    archive_buffer = generate_archive_for_group(results[group_key], group_key)

    return send_file(
        archive_buffer, as_attachment=True,
        download_name=f'archive_{group_key}.zip', mimetype='application/zip'
    )


@cadastre_bp.route('/download-document/<group_key>/<property_id>')
def download_document(group_key, property_id):
    results = session.get('categorized_results', {})
    deal = next((d for d in results.get(group_key, []) if d['property_id'] == property_id), None)
    if not deal:
        flash(f'Сделка с номером квартиры {property_id} не найдена.', 'danger')
        return redirect(url_for('cadastre_process.deals_list'))

    doc_buffer = generate_single_document(deal, group_key)

    return send_file(
        doc_buffer, as_attachment=True,
        download_name=f'Уведомление_кв_{property_id}.docx',
        mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    )


@cadastre_bp.route('/mark-delivered/<int:deal_id>', methods=['POST'])
def mark_delivered(deal_id):
    success = update_deal_status(deal_id, 'mark_delivered')
    return jsonify({'status': 'success' if success else 'error'}), 200 if success else 500


@cadastre_bp.route('/mark-arrived/<int:deal_id>', methods=['POST'])
def mark_arrived(deal_id):
    success = update_deal_status(deal_id, 'mark_arrived')
    return jsonify({'status': 'success' if success else 'error'}), 200 if success else 500


@cadastre_bp.route('/download-unilateral-act/<int:deal_id>')
def download_unilateral_act(deal_id):
    deal_data = get_single_deal_details(deal_id)
    if not deal_data:
        flash('Информация о сделке не найдена в CRM.', 'danger')
        return redirect(url_for('cadastre_process.deals_list'))

    update_deal_status(deal_id, 'act_downloaded')
    doc_buffer = generate_unilateral_act(deal_data)

    return send_file(
        doc_buffer, as_attachment=True,
        download_name=f'Односторонний_акт_кв_{deal_data["property_id"]}.docx',
        mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    )


@cadastre_bp.route('/upload-unilateral-act/<int:deal_id>', methods=['POST'])
def upload_unilateral_act(deal_id):
    if 'scan' not in request.files:
        flash('Файл для загрузки не найден.', 'danger')
        return redirect(url_for('cadastre_process.deals_list'))

    file = request.files['scan']
    if file.filename == '':
        flash('Файл не выбран.', 'danger')
        return redirect(url_for('cadastre_process.deals_list'))

    filename = secure_filename(f"unilateral_act_deal_{deal_id}.pdf")
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    file.save(filepath)

    update_deal_status(deal_id, 'act_uploaded', data=filepath)
    flash('Скан одностороннего акта успешно загружен.', 'success')
    return redirect(url_for('cadastre_process.deals_list'))


@cadastre_bp.route('/download-acceptance-act/<int:deal_id>')
def download_acceptance_act(deal_id):
    update_deal_status(deal_id, 'acceptance_act_downloaded')
    deal_data = get_single_deal_details(deal_id)
    # ЗАМЕНИТЬ НА ГЕНЕРАЦИЮ ОБЫЧНОГО АКТА
    doc_buffer = generate_unilateral_act(deal_data)
    return send_file(
        doc_buffer, as_attachment=True,
        download_name=f'Акт_приема-передачи_кв_{deal_data["property_id"]}.docx',
        mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    )


@cadastre_bp.route('/process-acceptance/<int:deal_id>', methods=['POST'])
def process_acceptance(deal_id):
    data = request.json
    success = update_deal_status(deal_id, 'process_acceptance', data=data)
    return jsonify({'status': 'success' if success else 'error'}), 200 if success else 500


@cadastre_bp.route('/upload-final-docs/<int:deal_id>', methods=['POST'])
def upload_final_docs(deal_id):
    signed_act = request.files.get('signed_act')
    defect_list = request.files.get('defect_list')

    if signed_act:
        filename = f"signed_act_deal_{deal_id}.pdf"
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        signed_act.save(filepath)
        update_deal_status(deal_id, 'upload_signed_act', data=filepath)

    if defect_list:
        filename = f"defect_list_deal_{deal_id}.pdf"
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        defect_list.save(filepath)
        update_deal_status(deal_id, 'upload_defect_list', data=filepath)

    flash('Файлы успешно загружены.', 'success')
    return redirect(url_for('cadastre_process.deals_list'))