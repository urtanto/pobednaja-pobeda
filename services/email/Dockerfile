FROM python:3.12-slim
WORKDIR /app

RUN pip install --upgrade pip

COPY services/requirements.txt .

RUN pip install -r requirements.txt

# Копируем исходники
COPY services/email /app/services/email
CMD ["python", "services/email/main.py"]