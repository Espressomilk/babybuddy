FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libopenjp2-7 \
    libpq5 \
    gettext \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p data media

# Compile translation files (.po → .mo)
RUN python manage.py compilemessages

EXPOSE 8000

CMD ["bash", "-c", "python manage.py migrate && gunicorn babybuddy.wsgi:application -c etc/gunicorn.py --timeout 30 --log-file -"]
