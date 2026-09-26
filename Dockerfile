FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn
COPY . .
ENV PORT=8787
EXPOSE 8787
CMD ["gunicorn", "-b", "0.0.0.0:8787", "-w", "1", "-k", "gthread", "--threads", "16", "--timeout", "120", "app:app"]
