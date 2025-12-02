from app import db
from datetime import datetime


class DealStatus(db.Model):
    __tablename__ = 'deal_statuses'

    deal_id = db.Column(db.Integer, primary_key=True)
    group_key = db.Column(db.String(50), nullable=True)
    status = db.Column(db.String(50), default='processing', nullable=False)

    # --- Существующие этапы (Группа 1) ---
    documents_delivered_at = db.Column(db.DateTime, nullable=True)
    client_arrived_at = db.Column(db.DateTime, nullable=True)
    unilateral_act_downloaded_at = db.Column(db.DateTime, nullable=True)
    unilateral_act_uploaded_path = db.Column(db.String(255), nullable=True)
    acceptance_act_downloaded_at = db.Column(db.DateTime, nullable=True)
    is_act_signed = db.Column(db.Boolean, nullable=True)
    has_defect_list = db.Column(db.Boolean, nullable=True)
    signed_act_uploaded_path = db.Column(db.String(255), nullable=True)
    defect_list_uploaded_path = db.Column(db.String(255), nullable=True)
    notification_number = db.Column(db.Integer, nullable=True)  # Строгий номер уведомления
    notification_date = db.Column(db.Date, nullable=True)
    # --- Поля для Группы 2 (Долг) ---
    debt_payment_deadline = db.Column(db.DateTime, nullable=True)
    penalty_check_deadline = db.Column(db.DateTime, nullable=True)
    current_penalty_amount = db.Column(db.Float, nullable=True)
    penalty_notification_generated = db.Column(db.Boolean, default=False, nullable=True)

    # --- НОВЫЕ ПОЛЯ ДЛЯ ГРУПП 3 и 5 (Увеличение площади) ---

    # 10-дневный дедлайн на подписание ДС (Доп. соглашения)
    area_increase_agreement_deadline = db.Column(db.DateTime, nullable=True)

    # Дата фактического подписания ДС
    area_increase_signed_at = db.Column(db.DateTime, nullable=True)

    # Путь к скану ДС
    area_increase_scan_path = db.Column(db.String(255), nullable=True)

    # Рассчитанная сумма доплаты за метры
    area_increase_payment_amount = db.Column(db.Float, nullable=True)

    # 30-дневный дедлайн на оплату доплаты
    area_increase_payment_deadline = db.Column(db.DateTime, nullable=True)

    # Рассчитанная сумма штрафа (10% + доплата)
    area_increase_penalty_amount = db.Column(db.Float, nullable=True)

    # 15-дневный дедлайн на оплату штрафа
    area_increase_penalty_deadline = db.Column(db.DateTime, nullable=True)

    # Флаг для кнопки скачивания уведомления о штрафе
    area_increase_penalty_doc_generated = db.Column(db.Boolean, default=False, nullable=True)