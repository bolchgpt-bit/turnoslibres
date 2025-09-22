#!/bin/bash
set -e

echo "Starting TurnosLibres application..."

# Wait for database
echo "Waiting for database..."
while ! pg_isready -h $DB_HOST -p $DB_PORT -U $DB_USER; do
    echo "Database is unavailable - sleeping"
    sleep 1
done
echo "Database is up!"

# Run migrations
echo "Running database migrations..."
flask db upgrade

# Check if database is empty and seed if needed
echo "Checking if database needs seeding..."
python -c "
from app import create_app, db
from app.models import Category
app = create_app()
with app.app_context():
    if Category.query.count() == 0:
        print('Database is empty, running seed...')
        exec(open('scripts/seed_data.py').read())
    else:
        print('Database already has data, skipping seed.')
"

echo "Starting application..."
exec "$@"
