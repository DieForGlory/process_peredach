# /app/cadastre_process/services/processing_service.py

from collections import defaultdict
from app.database import MysqlSession
from app import db
from ..models import DealStatus
from .data_service import get_deals_data


def process_cadastre_data(cadastre_data: dict, house_id: int):
    property_ids = list(cadastre_data.keys())
    if not property_ids:
        return {}

    db_session_mysql = MysqlSession()
    try:
        deals_from_db = get_deals_data(db_session_mysql, property_ids, house_id)
    finally:
        MysqlSession.remove()

    categorized_deals = defaultdict(list)
    for prop_id, cadastre_area in cadastre_data.items():
        deal = deals_from_db.get(prop_id)
        if not deal:
            continue

        contract_area = float(deal['contract_area'])
        area_diff = cadastre_area - contract_area

        deal_info = {
            'deal_id': deal['deal_id'],
            'property_id': prop_id,
            'area_diff': round(area_diff, 2),
            'client_id': deal['client_id'],
            'client_name': deal['client_name']
        }

        has_debt = deal['has_debt']
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
            for group_key, deals in categorized_deals.items() for deal in deals
        }
        all_deal_ids = list(all_deals_map.keys())

        existing_statuses = DealStatus.query.filter(DealStatus.deal_id.in_(all_deal_ids)).all()
        existing_status_map = {s.deal_id: s for s in existing_statuses}

        for deal_id, deal_info in all_deals_map.items():
            status = existing_status_map.get(deal_id)
            if status:
                status.group_key = deal_info['group_key']
                status.status = 'processing'
                status.documents_delivered_at = None
                status.client_arrived_at = None
                status.unilateral_act_downloaded_at = None
                status.unilateral_act_uploaded_path = None
                status.acceptance_act_downloaded_at = None
                status.is_act_signed = None
                status.has_defect_list = None
                status.signed_act_uploaded_path = None
                status.defect_list_uploaded_path = None
            else:
                new_status = DealStatus(
                    deal_id=deal_id,
                    group_key=deal_info['group_key'],
                    status='processing'
                )
                db.session.add(new_status)

        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"Ошибка при обновлении/создании статусов: {e}")

    return categorized_deals