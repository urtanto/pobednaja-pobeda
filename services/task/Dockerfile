FROM python:3.12-slim
WORKDIR /app

RUN pip install --upgrade pip

COPY services/requirements.txt .

RUN pip install -r requirements.txt

COPY services/task/requirements.txt .

RUN pip install -r requirements.txt

# Копируем исходники
COPY services/task /app/services/task
CMD ["python", "services/task/main.py"]