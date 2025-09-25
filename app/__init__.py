# /app/__init__.py
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_session import Session  # <-- ДОБАВЬТЕ ЭТОТ ИМПОРТ
from .config import Config

db = SQLAlchemy()
sess = Session()  # <-- СОЗДАЙТЕ ЭКЗЕМПЛЯР

def create_app():
    """Application factory function."""
    app = Flask(__name__)
    app.config.from_object(Config)

    # --- ИНИЦИАЛИЗИРУЙТЕ СЕССИЮ ---
    sess.init_app(app) # <-- ДОБАВЬТЕ ЭТУ СТРОКУ

    db.init_app(app)

    if app.config.get("RESET_DB_ON_START"):
        with app.app_context():
            from .cadastre_process.models import DealStatus

            print("Resetting local database...")
            db.drop_all()
            db.create_all()
            print("Local database has been successfully reset.")

    from .cadastre_process import cadastre_bp
    app.register_blueprint(cadastre_bp)

    return app