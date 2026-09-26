web: gunicorn -b 0.0.0.0:${PORT:-8787} -w 2 -k gthread --threads 8 --timeout 120 app:app
