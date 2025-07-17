# Пьяная реализация ласт задания

писалась под ягодамастером

---

# Сумасшедшая структура говна

- [`services`](services) - папка с сервисами.
    - [`auth`](services/auth) - серивис авторизации.
        - [`alembic`](services/auth/alembic) - алембик.
        - [`alembic.ini`](services/auth/alembic.ini) - все еще алембик.
        - [`database`](services/auth/database) - база данных (модельки вся хуйня).
        - [`requirements.txt`](services/auth/requirements.txt) - зависимости сервиса авторизации.
    - [`task`](services/task) - серивис задач.
        - [`alembic`](services/task/alembic) - алембик.
        - [`alembic.ini`](services/task/alembic.ini) - все еще алембик.
        - [`database`](services/task/database) - база данных (модельки вся хуйня).
        - [`requirements.txt`](services/task/requirements.txt) - зависимости сервиса задач.
    - [`email`](services/email) - серивис мейлов.
    - [`requirements.txt`](services/requirements.txt) - общие зависимости сервисов.
- [`docker-compose.yml`](docker-compose.yml) - файл для сборки сервисов.

---

# Как запустить

1. DEV запуск:

```bash
  docker compose up
```

2. Запуск:

```bash
  docker compose --profile production up --build
```

---

# Ебанутые tips and tricks

Новая миграция для сервиса:

```bash
  alembic -c services/<сервис>/alembic.ini revision --autogenerate -m 'name'
```

Закомитить изменения:

```bash
  alembic -c services/<сервис>/alembic.ini upgrade head
```