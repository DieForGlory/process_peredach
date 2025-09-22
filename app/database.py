# app/database.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from app.config import Config

# Создаем "движок" для подключения к базе данных MySQL
mysql_engine = create_engine(Config.MYSQL_DATABASE_URI)

# Создаем фабрику сессий, которая будет создавать новые сессии для работы с БД
mysql_session_factory = sessionmaker(bind=mysql_engine)

# Создаем "scoped" сессию. Это гарантирует, что в каждом веб-запросе используется своя уникальная сессия.
# Это важно для потокобезопасности в веб-приложениях.
MysqlSession = scoped_session(mysql_session_factory)