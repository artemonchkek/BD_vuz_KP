#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/.."
pip install --user -q -r requirements.txt
for i in $(seq 1 30); do
  python -c "import psycopg; psycopg.connect(host='localhost', user='postgres', password='postgres', dbname='postgres').close()" 2>/dev/null && break
  echo "Ожидание PostgreSQL..."; sleep 2
done
python init_db.py
