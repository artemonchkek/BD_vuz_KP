"""Создание БД vuz_staff и выполнение SQL-скриптов (таблицы, логика, тестовые данные).

Запуск:  python init_db.py            — создать БД (если нет) и заполнить заново
         python init_db.py --no-seed  — без тестовых данных
Параметры подключения — в app/config.py или переменных окружения VUZ_DB_*.
"""
import sys
from pathlib import Path

import psycopg
from psycopg import sql

from app.config import DB

ROOT = Path(__file__).resolve().parent / "sql"


def main():
    params = {k: v for k, v in DB.items() if k != "dbname"}
    try:
        with psycopg.connect(**params, dbname="postgres", autocommit=True) as c:
            if not c.execute("SELECT 1 FROM pg_database WHERE datname = %s", (DB["dbname"],)).fetchone():
                c.execute(sql.SQL("CREATE DATABASE {} ENCODING 'UTF8' TEMPLATE template0").format(sql.Identifier(DB["dbname"])))
                print(f"База данных {DB['dbname']} создана")
    except psycopg.OperationalError as e:
        sys.exit(f"Не удалось подключиться к PostgreSQL ({DB['host']}:{DB['port']}, пользователь {DB['user']}).\n"
                 f"Проверьте, что сервер запущен и пароль указан в app/config.py.\n{e}")
    files = ["01_schema.sql", "02_logic.sql"] + ([] if "--no-seed" in sys.argv else ["03_seed.sql"])
    with psycopg.connect(**DB, autocommit=True) as c:
        c.execute("SET client_min_messages = warning")
        for f in files:
            c.execute((ROOT / f).read_text(encoding="utf-8"))
            print(f"Выполнен {f}")
    print("Готово. Запустите приложение: python -m uvicorn app.main:app  и откройте http://127.0.0.1:8000")


if __name__ == "__main__":
    main()
