"""Параметры подключения к серверу БД.

Значения можно переопределить переменными окружения VUZ_DB_HOST, VUZ_DB_PORT,
VUZ_DB_NAME, VUZ_DB_USER, VUZ_DB_PASSWORD.
"""
import os

DB = {
    "host": os.getenv("VUZ_DB_HOST", "localhost"),
    "port": int(os.getenv("VUZ_DB_PORT", "5432")),
    "dbname": os.getenv("VUZ_DB_NAME", "vuz_staff"),
    "user": os.getenv("VUZ_DB_USER", "postgres"),
    "password": os.getenv("VUZ_DB_PASSWORD", "postgres"),
}

APP_TITLE = "Сотрудники вуза"
UNIVERSITY = "Иркутский национальный исследовательский технический университет"
