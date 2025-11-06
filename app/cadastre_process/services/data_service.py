# app/cadastre_process/services/data_service.py

from collections import defaultdict
from datetime import datetime, timedelta

from sqlalchemy import text

from app import db
from app.database import MysqlSession
from ..models import DealStatus


def get_complexes_and_houses():
    """Получает список всех ЖК и домов из MySQL для UI фильтров."""
    db_session = MysqlSession()
    houses_data = defaultdict(list)
    try:
        query = text(
            "SELECT id, complex_name, name FROM estate_houses WHERE complex_name IS NOT NULL AND name IS NOT NULL ORDER BY complex_name, name;")
        result = db_session.execute(query).fetchall()
        for row in result:
            houses_data[row.complex_name].append({'id': row.id, 'name': row.name})
        return houses_data
    finally:
        MysqlSession.remove()


def get_apartments_for_house(house_id: int):
    """Получает номера квартир из MySQL для генерации Excel-шаблона."""
    db_session = MysqlSession()
    try:
        query = text("""
            SELECT es.geo_flatnum FROM estate_sells es
            WHERE es.house_id = :h_id 
              AND es.estate_sell_category = 'flat'
            ORDER BY CAST(es.geo_flatnum AS UNSIGNED);
        """)
        return db_session.execute(query, {'h_id': house_id}).fetchall()
    finally:
        MysqlSession.remove()


def get_deals_data(db_session, property_ids: list, house_id: int):
    """
    (Обновлено: добавлен d.deal_sum)
    """
    query = text("""
        SELECT
            es.geo_flatnum,
            es.estate_floor,
            es.geo_house_entrance,
            es.estate_sell_status_name,
            es.estate_area,
            d.id as deal_id,
            d.deal_area,
            d.deal_status_name,
            d.seller_contacts_id,
            d.deal_sum, -- <-- ДОБАВЛЕНО ПОЛЕ СУММЫ ДОГОВОРА
            edc.contacts_buy_name,

            (SELECT 1 FROM finances p
             WHERE p.deal_id = d.id
               AND p.status_name = 'К оплате'
               AND p.date_to < NOW()
             LIMIT 1
            ) IS NOT NULL AS has_debt

        FROM estate_sells es
        LEFT JOIN estate_deals d ON es.id = d.estate_sell_id AND d.deal_status_name IN ('Сделка в работе', 'Сделка проведена')
        LEFT JOIN estate_deals_contacts edc ON d.contacts_buy_id = edc.id
        WHERE es.house_id = :h_id
          AND es.geo_flatnum IN :p_ids
          AND es.estate_sell_category = 'flat';
    """)
    result = db_session.execute(query, {'p_ids': property_ids, 'h_id': house_id}).fetchall()

    properties_data = {}
    for row in result:
        contract_area = row.deal_area if row.deal_area is not None else row.estate_area

        properties_data[str(row.geo_flatnum)] = {
            'deal_id': row.deal_id,
            'deal_sum': row.deal_sum or 0,  # <-- ДОБАВЛЕНО ПОЛЕ
            'contract_area': contract_area or 0,
            'client_id': row.seller_contacts_id,
            'floor': row.estate_floor,
            'section': row.geo_house_entrance,
            'has_debt': bool(row.has_debt),
            'client_name': row.contacts_buy_name,
            'deal_status_name': row.deal_status_name,
            'sell_status_name': row.estate_sell_status_name
        }
    return properties_data
def check_increase_payment(deal_id: int, required_amount: float):
    """
    Проверяет, был ли платеж "Проведено" на сумму доплаты за метры.
    """
    db_session_mysql = MysqlSession()
    try:
        # Ищем платеж, который соответствует сделке, статусу и сумме (с погрешностью 0.01)
        query = text("""
            SELECT 1
            FROM finances
            WHERE deal_id = :deal_id
              AND status_name = 'Проведено'
              AND ABS(amount - :amount) < 0.01
            LIMIT 1;
        """)
        result = db_session_mysql.execute(
            query,
            {'deal_id': deal_id, 'amount': required_amount}
        ).scalar_one_or_none()
        return bool(result)
    finally:
        MysqlSession.remove()

def get_filtered_deals(filters: dict, page: int, per_page: int):
    """
    Получает сделки из MySQL, а затем обогащает их статусами из SQLite.
    (Использует 'finances' для 'last_overdue_payment_date')
    """
    db_session_mysql = MysqlSession()
    deals_for_page = []
    total_count = 0
    try:
        # ИСПОЛЬЗУЕМ 'finances' ВМЕСТО 'estate_deals_payments'
        base_query = """
            FROM estate_deals d
            JOIN estate_sells es ON d.estate_sell_id = es.id
            JOIN estate_houses h ON d.house_id = h.id
            LEFT JOIN estate_deals_contacts edc ON d.contacts_buy_id = edc.id
            LEFT JOIN (
                SELECT deal_id, MIN(date_to) as first_overdue_payment_date
                FROM finances
                WHERE status_name = 'К оплате'
                  AND date_to < NOW()
                GROUP BY deal_id
            ) p ON d.id = p.deal_id
        """
        where_clauses = ["es.estate_sell_category = 'flat'"]
        params = {}

        if filters.get('complex_name'):
            where_clauses.append("h.complex_name = :complex_name")
            params['complex_name'] = filters['complex_name']
        if filters.get('house_id'):
            where_clauses.append("d.house_id = :house_id")
            params['house_id'] = filters['house_id']

        where_sql = " WHERE " + " AND ".join(where_clauses)

        count_query = text(f"SELECT COUNT(d.id) {base_query} {where_sql}")
        total_count = db_session_mysql.execute(count_query, params).scalar_one()

        offset = (page - 1) * per_page
        data_query_str = f"""
            SELECT d.id as deal_id, d.deal_status_name, es.geo_flatnum, 
                   h.complex_name, h.name as house_name, d.finances_income_reserved,
                   edc.contacts_buy_name, edc.contacts_buy_phones,
                   d.deal_sum, p.first_overdue_payment_date
            {base_query} {where_sql}
            ORDER BY d.id DESC
            LIMIT :limit OFFSET :offset
        """
        params.update({'limit': per_page, 'offset': offset})
        deals_for_page_raw = db_session_mysql.execute(text(data_query_str), params).fetchall()
        deals_for_page = [dict(row._mapping) for row in deals_for_page_raw]
    finally:
        MysqlSession.remove()

    # Шаг 2: Обогащаем данные статусами из локальной SQLite базы
    if deals_for_page:
        deal_ids = [d['deal_id'] for d in deals_for_page]
        statuses = DealStatus.query.filter(DealStatus.deal_id.in_(deal_ids)).all()
        status_map = {s.deal_id: s for s in statuses}

        # Шаг 3: Объединяем данные
        for deal in deals_for_page:
            status_obj = status_map.get(deal['deal_id'])
            deal['status_obj'] = status_obj
            deal['is_timed_out'] = False
            deal['deadline_iso'] = None

            if status_obj and status_obj.documents_delivered_at and status_obj.status == 'pending_arrival':
                deadline = status_obj.documents_delivered_at + timedelta(days=30)
                deal['is_timed_out'] = datetime.utcnow() > deadline
                deal['deadline_iso'] = deadline.isoformat()

    return deals_for_page, total_count


def get_single_deal_details(deal_id: int):
    """Получает детальную информацию по одной сделке из MySQL по ее ID."""
    db_session_mysql = MysqlSession()
    try:
        query = text("""
            SELECT d.id as deal_id, es.geo_flatnum as property_id, edc.contacts_buy_name as client_name
            FROM estate_deals d
            JOIN estate_sells es ON d.estate_sell_id = es.id
            LEFT JOIN estate_deals_contacts edc ON d.contacts_buy_id = edc.id
            WHERE d.id = :deal_id
        """)
        result = db_session_mysql.execute(query, {'deal_id': deal_id}).fetchone()
        return dict(result._mapping) if result else None
    finally:
        MysqlSession.remove()


def get_single_deal_details_for_workflow(deal_id: int):
    """
    Получает детальную информацию (включая финансы) для фонового обработчика.
    (Использует 'finances')
    """
    db_session_mysql = MysqlSession()
    try:
        # ИСПОЛЬЗУЕМ 'finances' ВМЕСТО 'estate_deals_payments'
        query = text("""
            SELECT 
                d.id as deal_id, 
                es.geo_flatnum as property_id, 
                edc.contacts_buy_name as client_name,
                d.deal_sum,
                p.first_overdue_payment_date
            FROM estate_deals d
            JOIN estate_sells es ON d.estate_sell_id = es.id
            LEFT JOIN estate_deals_contacts edc ON d.contacts_buy_id = edc.id
            LEFT JOIN (
                SELECT 
                    deal_id,
                    MIN(date_to) as first_overdue_payment_date
                FROM finances
                WHERE status_name = 'К оплате'
                  AND date_to < NOW()
                GROUP BY deal_id
            ) p ON d.id = p.deal_id
            WHERE d.id = :deal_id
        """)
        result = db_session_mysql.execute(query, {'deal_id': deal_id}).fetchone()
        return dict(result._mapping) if result else {}
    finally:
        MysqlSession.remove()


def check_debt_status_from_mysql(deal_id: int):
    """
    Быстро проверяет ТОЛЬКО статус долга в MySQL по новой логике.
    (Использует 'finances')
    """
    db_session_mysql = MysqlSession()
    try:
        # ИСПОЛЬЗУЕМ 'finances' ВМЕСТО 'estate_deals_payments'
        query = text("""
            SELECT 1
            FROM finances
            WHERE deal_id = :deal_id
              AND status_name = 'К оплате'
              AND date_to < NOW()
            LIMIT 1;
        """)
        result = db_session_mysql.execute(query, {'deal_id': deal_id}).scalar_one_or_none()
        return bool(result)
    finally:
        MysqlSession.remove()


def update_deal_status(deal_id: int, action: str, data=None):
    """
    Центральная функция для обновления статуса сделки в SQLite.
    (Обновлена логика 'mark_delivered' и 'mark_arrived')
    """
    try:
        status = DealStatus.query.get(deal_id)
        if not status: return False

        if action == 'mark_delivered':
            # --- ОБНОВЛЕННАЯ ЛОГИКА ЗАПУСКА ТАЙМЕРОВ ---
            current_time = datetime.utcnow()

            if status.group_key in ('3_debt_and_increase', '5_increase_only'):
                # Группы 3 и 5 (Увеличение): Запускаем 10-дневный таймер на подписание ДС
                status.status = 'pending_increase_signing'
                status.area_increase_agreement_deadline = current_time + timedelta(days=10)

            elif status.group_key == '2_debt_only':
                # Группа 2 (Долг): Запускаем 10-дневный таймер на погашение долга
                status.status = 'pending_debt_payment'
                status.debt_payment_deadline = current_time + timedelta(days=10)

            else:
                # Группа 1 (Без проблем): Запускаем 30-дневный таймер на визит
                status.documents_delivered_at = current_time
                status.status = 'pending_arrival'

        elif action == 'mark_arrived':
            # Если клиент пришел, он переходит на этап приемки,
            # все таймеры (долг, ДС) больше не нужны.
            status.client_arrived_at = datetime.utcnow()
            status.status = 'acceptance_pending'
            status.debt_payment_deadline = None
            status.penalty_check_deadline = None
            status.area_increase_agreement_deadline = None
            status.area_increase_payment_deadline = None
            status.area_increase_penalty_deadline = None

        # --- НОВЫЙ БЛОК ДЛЯ СЦЕНАРИЯ УВЕЛИЧЕНИЯ ПЛОЩАДИ ---
        elif action == 'mark_increase_agreement_signed':
            status.area_increase_signed_at = datetime.utcnow()
            status.area_increase_scan_path = data.get('filepath')
            status.status = 'pending_increase_payment'
            # Запускаем 30-дневный таймер на оплату доплаты
            status.area_increase_payment_deadline = datetime.utcnow() + timedelta(days=30)
            # Сбрасываем 10-дневный таймер подписания
            status.area_increase_agreement_deadline = None

        # --- (Остальные actions 'acceptance_act_downloaded' и т.д. без изменений) ---
        elif action == 'acceptance_act_downloaded':
            status.acceptance_act_downloaded_at = datetime.utcnow()

        elif action == 'process_acceptance':
            # ... (без изменений)
            is_signed = data.get('is_signed')
            has_defects = data.get('has_defects')
            status.is_act_signed = is_signed
            status.has_defect_list = has_defects
            if is_signed is False and has_defects is False:
                status.status = 'unilateral_pending'

        elif action == 'upload_signed_act':
            # ... (без изменений)
            status.signed_act_uploaded_path = data
            if not status.has_defect_list:
                status.status = 'completed'
        elif action == 'upload_defect_list':
            # ... (без изменений)
            status.defect_list_uploaded_path = data
            if status.signed_act_uploaded_path:
                status.status = 'completed'

        elif action == 'act_downloaded':
            # ... (без изменений)
            status.unilateral_act_downloaded_at = datetime.utcnow()
        elif action == 'act_uploaded':
            # ... (без изменений)
            status.unilateral_act_uploaded_path = data
            status.status = 'completed'

        db.session.commit()
        return True
    except Exception as e:
        db.session.rollback()
        print(f"Ошибка при обновлении статуса: {e}")
        return False


def get_statuses_for_deals(deal_ids: list):
    """
    Получает из SQLite статусы для конкретного списка ID сделок.
    """
    if not deal_ids:
        return {}
    from ..models import DealStatus
    statuses = DealStatus.query.filter(DealStatus.deal_id.in_(deal_ids)).all()
    return {s.deal_id: s for s in statuses}