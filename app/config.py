# app/config.py
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'a-very-secret-key'

    # --- ДОБАВЬТЕ ЭТИ СТРОКИ ---
    # Указываем, что сессии теперь хранятся на сервере в файловой системе
    SESSION_TYPE = 'filesystem'
    # Говорим сессии не подписывать cookie, так как мы храним там только ID
    SESSION_PERMANENT = False
    SESSION_USE_SIGNER = True
    # --- КОНЕЦ НОВЫХ СТРОК ---

    MYSQL_DATABASE_URI = (
        f"mysql+pymysql://"
        f"{os.environ.get('MYSQL_USER')}:{os.environ.get('MYSQL_PASSWORD')}"
        f"@{os.environ.get('MYSQL_HOST')}:{os.environ.get('MYSQL_PORT')}"
        f"/{os.environ.get('MYSQL_DB')}"
    )
    SQLALCHEMY_DATABASE_URI = 'sqlite:///notifications.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    RESET_DB_ON_START = True