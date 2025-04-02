#!/bin/bash
cd /app
# Use PORT env var if available, default to 8000 otherwise
export PORT=${PORT:-8000}
# Start the app with Gunicorn
exec gunicorn --bind 0.0.0.0:$PORT app:app
