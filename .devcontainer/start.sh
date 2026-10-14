#!/usr/bin/env bash
cd "$(dirname "$0")/.."
if [ ! -f .devcontainer/.db_ready ]; then
  python -c "import psycopg; c=psycopg.connect(host='localhost',user='postgres',password='postgres',dbname='vuz_staff'); c.execute('select 1 from сотрудник limit 1'); c.close()" 2>/dev/null \
    || python init_db.py
  touch .devcontainer/.db_ready
fi
echo "Приложение запускается. Откройте вкладку PORTS и ссылку на порт 8000."
exec python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
