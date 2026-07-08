#!/bin/sh
set -e

echo "=== RestoPOS Backend ishga tushmoqda ==="

echo "Database kutilmoqda..."
until python - <<'EOF'
import os, sys
from urllib.parse import urlparse
try:
    import psycopg2
    url = urlparse(os.environ.get('DATABASE_URL', ''))
    conn = psycopg2.connect(
        host=url.hostname, port=url.port or 5432,
        user=url.username, password=url.password,
        dbname=url.path.lstrip('/')
    )
    conn.close()
    print("Database tayyor")
    sys.exit(0)
except Exception as e:
    sys.exit(1)
EOF
do
    echo "  Database hali tayyor emas, 2s kutilmoqda..."
    sleep 2
done

echo "Migratsiyalar amalga oshirilmoqda..."
alembic upgrade head

echo "Server ishga tushirilmoqda (workers=2)..."
exec uvicorn main:app --host 0.0.0.0 --port 8000 --workers 2
