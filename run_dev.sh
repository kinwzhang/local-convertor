#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

export FLASK_DEBUG="${FLASK_DEBUG:-1}"
export SECRET_KEY="${SECRET_KEY:-dev-secret-key-change-in-production}"
export TIMEZONE="${TIMEZONE:-Asia/Hong_Kong}"
export PUBLIC_BASE_URL="${PUBLIC_BASE_URL:-http://localhost:5000}"

.venv/bin/python -c "from app import create_app; create_app()" >/dev/null 2>&1

.venv/bin/flask db upgrade

exec .venv/bin/python main.py
