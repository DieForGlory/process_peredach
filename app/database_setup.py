# /app/database_setup.py
from app import db
# Убедитесь, что все ваши модели импортированы здесь, чтобы SQLAlchemy о них знал
from .cadastre_process.models import CadastreNotification, DeliveredDocument

def init_database(app):
    """Удаляет все таблицы и создает их заново."""
    with app.app_context():
        print("Resetting local database...")
        # Удаляем все таблицы, которые описаны в наших моделях
        db.drop_all()
        # Создаем все таблицы заново по моделям
        db.create_all()
        print("Local database has been successfully reset.")