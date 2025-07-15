FROM python:3.12-slim
WORKDIR /app

RUN pip install --upgrade pip

COPY services/requirements.txt .

RUN pip install -r requirements.txt

COPY services/auth/requirements.txt .

RUN pip install -r requirements.txt

# Копируем исходники
COPY services/auth /app/services/auth
CMD ["python", "services/auth/main.py"]