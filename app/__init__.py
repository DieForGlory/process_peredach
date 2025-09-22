# /app/__init__.py
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from .config import Config

db = SQLAlchemy()


def create_app():
    """Application factory function."""
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)

    if app.config.get("RESET_DB_ON_START"):
        with app.app_context():
            # ИСПРАВЛЕНИЕ: Импортируем правильную модель DealStatus
            from .cadastre_process.models import DealStatus

            print("Resetting local database...")
            db.drop_all()
            db.create_all()
            print("Local database has been successfully reset.")

    from .cadastre_process import cadastre_bp
    app.register_blueprint(cadastre_bp)

    return app