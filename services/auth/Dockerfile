FROM python:3.12-slim
WORKDIR /app

ENV PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN pip install --upgrade pip

COPY services/requirements.txt .

RUN pip install -r requirements.txt

COPY services/auth/requirements.txt .

RUN pip install -r requirements.txt

# Копируем исходники
COPY services/auth /app/services/auth
CMD ["python", "services/auth/main.py"]