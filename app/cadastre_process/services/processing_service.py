# /app/cadastre_process/services/processing_service.py

from collections import defaultdict

from app import db
from app.database import MysqlSession
from .data_service import get_deals_data
from ..models import DealStatus


def process_cadastre_data(cadastre_data: dict, house_id: int):
    property_ids = list(cadastre_data.keys())
    if not property_ids:
        return {}

    db_session_mysql = MysqlSession()
    try:
        properties_from_db = get_deals_data(db_session_mysql, property_ids, house_id)
    finally:
        MysqlSession.remove()

    categorized_deals = defaultdict(list)
    for prop_id, cadastre_area in cadastre_data.items():
        prop_data = properties_from_db.get(prop_id)
        if not prop_data:
            continue

        if not prop_data.get('deal_id'):
            continue

        contract_area = float(prop_data.get('contract_area', 0))
        area_diff = cadastre_area - contract_area

        # ДОБАВЛЕНО ПОЛУЧЕНИЕ СУММЫ
        deal_sum = float(prop_data.get('deal_sum', 0))

        deal_info = {
            'deal_id': prop_data.get('deal_id'),
            'deal_sum': deal_sum,  # <-- Сохраняем сумму
            'property_id': prop_id,
            'area_diff': round(area_diff, 2),
            'contract_area': contract_area,
            'client_id': prop_data.get('client_id'),
            'client_name': prop_data.get('client_name'),
            'floor': prop_data.get('floor'),
            'section': prop_data.get('section', 'N/A'),
            'sell_status_name': prop_data.get('sell_status_name'),
            'deal_status_name': prop_data.get('deal_status_name')
        }

        has_debt = prop_data.get('has_debt', False)
        # ИЗМЕНЕНИЕ ЛОГИКИ: Увеличение > 2 (было > 0.1)
        area_change = 'increase' if area_diff > 2 else 'decrease' if area_diff < -2 else 'no_change'

        key_map = {
            (False, 'no_change'): '1_no_issues', (True, 'no_change'): '2_debt_only',
            (False, 'increase'): '5_increase_only', (True, 'increase'): '3_debt_and_increase',
            (False, 'decrease'): '6_decrease_only', (True, 'decrease'): '4_debt_and_decrease',
        }
        key = key_map.get((has_debt, area_change))
        if key:
            categorized_deals[key].append(deal_info)

    try:
        all_deals_map = {
            deal['deal_id']: {'group_key': group_key, **deal}
            for group_key, deals in categorized_deals.items() for deal in deals if deal.get('deal_id')
        }

        if all_deals_map:
            all_deal_ids = list(all_deals_map.keys())

            existing_statuses = DealStatus.query.filter(DealStatus.deal_id.in_(all_deal_ids)).all()
            existing_status_map = {s.deal_id: s for s in existing_statuses}

            for deal_id, deal_info in all_deals_map.items():

                # --- РАСЧЕТ СУММЫ ДОПЛАТЫ ---
                payment_amount = 0
                if deal_info['area_diff'] > 2 and deal_info['contract_area'] > 0:
                    # Формула: (Стоимость по договору / площадь квартиры) * площадь расхождения
                    price_per_meter = deal_info['deal_sum'] / deal_info['contract_area']
                    payment_amount = price_per_meter * deal_info['area_diff']
                # --- КОНЕЦ РАСЧЕТА ---

                status = existing_status_map.get(deal_id)
                if status:
                    status.group_key = deal_info['group_key']
                    status.status = 'processing'

                    # Обновляем сумму доплаты
                    status.area_increase_payment_amount = payment_amount

                    # ... (сброс всех полей)
                    status.documents_delivered_at = None
                    status.client_arrived_at = None
                    status.unilateral_act_downloaded_at = None
                    status.unilateral_act_uploaded_path = None
                    status.acceptance_act_downloaded_at = None
                    status.is_act_signed = None
                    status.has_defect_list = None
                    status.signed_act_uploaded_path = None
                    status.defect_list_uploaded_path = None
                    # Сброс полей Группы 2
                    status.debt_payment_deadline = None
                    status.penalty_check_deadline = None
                    status.current_penalty_amount = None
                    status.penalty_notification_generated = False
                    # Сброс полей Группы 5
                    status.area_increase_agreement_deadline = None
                    status.area_increase_signed_at = None
                    status.area_increase_scan_path = None
                    status.area_increase_payment_deadline = None
                    status.area_increase_penalty_amount = None
                    status.area_increase_penalty_deadline = None
                    status.area_increase_penalty_doc_generated = False

                else:
                    new_status = DealStatus(
                        deal_id=deal_id,
                        group_key=deal_info['group_key'],
                        status='processing',
                        # Сохраняем рассчитанную сумму
                        area_increase_payment_amount=payment_amount
                    )
                    db.session.add(new_status)

            db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"Ошибка при обновлении/создании статусов: {e}")

    return categorized_deals
