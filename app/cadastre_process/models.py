# /app/cadastre_process/models.py
from app import db
from datetime import datetime


class DealStatus(db.Model):
    __tablename__ = 'deal_statuses'

    deal_id = db.Column(db.Integer, primary_key=True)
    group_key = db.Column(db.String(50), nullable=True)
    status = db.Column(db.String(50), default='processing', nullable=False)

    # Существующие этапы
    documents_delivered_at = db.Column(db.DateTime, nullable=True)
    client_arrived_at = db.Column(db.DateTime, nullable=True)
    unilateral_act_downloaded_at = db.Column(db.DateTime, nullable=True)
    unilateral_act_uploaded_path = db.Column(db.String(255), nullable=True)

    # --- НОВЫЕ ПОЛЯ ДЛЯ НОВОЙ ЛОГИКИ ---
    acceptance_act_downloaded_at = db.Column(db.DateTime, nullable=True)
    is_act_signed = db.Column(db.Boolean, nullable=True)
    has_defect_list = db.Column(db.Boolean, nullable=True)
    signed_act_uploaded_path = db.Column(db.String(255), nullable=True)
    defect_list_uploaded_path = db.Column(db.String(255), nullable=True)