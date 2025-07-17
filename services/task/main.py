import asyncio
import json
import os
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Optional

import jwt
import sqlalchemy.exc
import uvicorn
from aio_pika import ExchangeType, IncomingMessage, Message, connect_robust
from aio_pika.abc import AbstractExchange, AbstractRobustConnection
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr, UUID4
from sqlalchemy import Result, select, update
from sqlalchemy.orm import selectinload
from starlette.requests import Request
from starlette.status import HTTP_200_OK, HTTP_201_CREATED, HTTP_204_NO_CONTENT, HTTP_400_BAD_REQUEST, \
    HTTP_404_NOT_FOUND

from services.task.database.connector import Database
from services.task.database.models import Executors, TaskModel, Watcher
from services.task.schemas import BaseErrorResponse, CreateTaskRequest, FilterTaskRequest, MultiTaskResponse, TaskDB, \
    TaskResponse, UpdateTaskRequest

SECRET_KEY: str = os.getenv("SECRET_KEY", "change_this_in_prod")
ALGORITHM: str = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login")

rabbit_host = os.getenv("RABBITMQ_HOST", "localhost")
rabbit_user = os.getenv("RABBITMQ_USER", "guest")
rabbit_pass = os.getenv("RABBITMQ_PASS", "guest")
rabbit_port = int(os.getenv("RABBITMQ_PORT", 5672))


def get_connection(request: Request) -> AbstractRobustConnection:
    return request.app.state.amqp_connection


async def get_exchange(name: str, connection: AbstractRobustConnection) -> AbstractExchange:
    channel = await connection.channel()
    exchange = await channel.get_exchange(
        name=name,
        ensure=True,
    )
    return exchange


async def auth_exchange(connection: AbstractRobustConnection = Depends(get_connection)) -> AbstractExchange:
    return await get_exchange(name="event", connection=connection)


async def rpc_call(routing_key: str, data: dict):
    corr_id = str(uuid.uuid4())

    # exchange = await get_exchange("event", connection)
    channel = await app.state.amqp_connection.channel()

    loop = asyncio.get_event_loop()
    future = loop.create_future()

    async def on_response(msg: IncomingMessage) -> None:
        if msg.correlation_id == corr_id:
            future.set_result(json.loads(msg.body.decode()))

    reply_q = await channel.get_queue("amq.rabbitmq.reply-to", ensure=False)
    await reply_q.consume(
        on_response,
        no_ack=True,
    )

    exchange = await channel.declare_exchange(
        name="rpc",
        type=ExchangeType.DIRECT,
        durable=True
    )

    await exchange.publish(
        Message(
            body=json.dumps(data).encode(),
            reply_to="amq.rabbitmq.reply-to",
            correlation_id=corr_id,
        ),
        routing_key=routing_key,
    )

    result = await future
    return result


async def rpc_task_watchers(msg: IncomingMessage):
    async with msg.process():
        body = json.loads(msg.body.decode())
        user_id: str = body["user_id"]

        async with await Database().get_session() as session:
            async with session.begin():
                watchers = (
                    await session.execute(
                        select(Watcher).where(Watcher.user_id == user_id)
                    )
                ).scalars().all()

                watchers = [str(watcher.task_id) for watcher in watchers]

                channel = await app.state.amqp_connection.channel()

                await channel.default_exchange.publish(
                    Message(
                        body=json.dumps(
                            {
                                "type": "error",
                                "data": watchers
                            }
                        ).encode(),
                        correlation_id=msg.correlation_id
                    ),
                    routing_key=msg.reply_to,
                )


async def rpc_task_executors(msg: IncomingMessage):
    async with msg.process():
        body = json.loads(msg.body.decode())
        user_id: str = body["user_id"]

        async with await Database().get_session() as session:
            async with session.begin():
                executors = (
                    await session.execute(
                        select(Executors).where(Executors.user_id == user_id)
                    )
                ).scalars().all()

                executors = [str(executor.task_id) for executor in executors]

                channel = await app.state.amqp_connection.channel()

                await channel.default_exchange.publish(
                    Message(
                        body=json.dumps(
                            {
                                "type": "error",
                                "data": executors
                            }
                        ).encode(),
                        correlation_id=msg.correlation_id
                    ),
                    routing_key=msg.reply_to,
                )


async def start_rpc():
    channel = await app.state.amqp_connection.channel()

    exchange = await channel.declare_exchange(
        name="rpc",
        type=ExchangeType.DIRECT,
        durable=True
    )

    queue_watchers = await channel.declare_queue("tasks.watchers", durable=False)
    queue_executors = await channel.declare_queue("tasks.executors", durable=False)
    await queue_watchers.bind(exchange, routing_key="tasks.watchers")
    await queue_executors.bind(exchange, routing_key="tasks.executors")
    await queue_watchers.consume(rpc_task_watchers)
    await queue_executors.consume(rpc_task_executors)

    await asyncio.Future()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await Database().init()

    connection = await connect_robust(
        host=rabbit_host,
        port=rabbit_port,
        login=rabbit_user,
        password=rabbit_pass
    )
    app.state.amqp_connection = connection

    channel = await connection.channel()

    await channel.declare_exchange(
        name="event",
        type=ExchangeType.DIRECT,
        durable=True
    )

    asyncio.create_task(start_rpc())

    yield

    await connection.close()


app = FastAPI(title="Unified API", lifespan=lifespan)


class UserCreate(BaseModel):
    email: EmailStr
    password: str


class UserPublic(BaseModel):
    id: uuid.UUID
    email: EmailStr


class AuthUserResponse(BaseModel):
    status: int = HTTP_200_OK
    error: bool = False
    access_token: str
    token_type: str = 'bearer'


def _verify_password(password: str, hashed: str) -> bool:
    return pwd_context.verify(password, hashed)


def _create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(UTC) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


async def _get_user(email: str) -> Optional[dict]:
    user = await rpc_call("user.get", {"email": email})
    return user


async def _authenticate_user(email: str, password: str) -> Optional[dict]:
    user = await _get_user(email)
    if user["type"] == "error":
        return None
    if not _verify_password(password, user["data"]["password"]):
        return None
    return user["data"]


async def _get_current_user(token: str = Depends(oauth2_scheme)) -> UserPublic:
    cred_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise cred_exc
    except jwt.PyJWTError:
        raise cred_exc
    user = await _get_user(email)
    if user is None:
        raise cred_exc
    return UserPublic(id=user["id"], email=user["email"])


@app.post("/login", response_model=AuthUserResponse)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = await _authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password")
    access_token = _create_access_token(data={"sub": user["email"]})
    return AuthUserResponse(access_token=access_token)


@app.post(
    path='/',
    status_code=HTTP_201_CREATED,
    responses={
        HTTP_201_CREATED: {
            'model': TaskResponse,
            'description': 'Task created successfully.',
        },
        HTTP_400_BAD_REQUEST: {
            'model': BaseErrorResponse,
            'description': 'Invalid input data.',
        },
    },
)
async def create_task(
        task: CreateTaskRequest,
        _: str = Depends(oauth2_scheme)
) -> TaskResponse:
    """Create task."""
    try:
        async with await Database().get_session() as session:
            async with session.begin():
                print(task)
                if task.assignee_id:
                    res = await rpc_call("user.get", {"user_id": str(task.assignee_id)})
                    if res["type"] == "error":
                        raise Exception()

                if task.author_id:
                    res = await rpc_call("user.get", {"user_id": str(task.author_id)})
                    if res["type"] == "error":
                        raise Exception()

                created_task: TaskModel = TaskModel(**task.model_dump())
                session.add(created_task)
                await session.commit()
                created_task: TaskDB = created_task.to_schema()
    except Exception:
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail='Wrong data provided.')
    return TaskResponse(payload=created_task)


@app.get(
    path='/',
    status_code=HTTP_200_OK,
    responses={
        HTTP_200_OK: {
            'model': MultiTaskResponse,
            'description': 'Tasks got successfully.',
        },
    },
)
async def get_tasks(
        task_filter: FilterTaskRequest = Depends(FilterTaskRequest),
        _: str = Depends(oauth2_scheme)
) -> MultiTaskResponse:
    """Get tasks with filtering."""
    # tasks: list[TaskDB] = await service.get_all(task_filter)
    async with await Database().get_session() as session:
        async with session.begin():
            query = select(TaskModel)

            if task_filter.title:
                query = query.where(TaskModel.title.ilike(f'%{task_filter.title}%'))

            if task_filter.status:
                query = query.where(TaskModel.status == task_filter.status)

            if task_filter.author_id:
                query = query.where(TaskModel.author_id == task_filter.author_id)

            query = query.options(
                selectinload(TaskModel.watcher_associations),
                selectinload(TaskModel.executor_associations),
            )

            result = await session.execute(query)
            result: list[TaskModel] = list(result.scalars().all())
            tasks = [task.to_schema() for task in result]
    return MultiTaskResponse(payload=tasks)


@app.get(
    path='/{task_id}',
    status_code=HTTP_200_OK,
    responses={
        HTTP_200_OK: {
            'model': TaskResponse,
            'description': 'Task got successfully.',
        },
        HTTP_404_NOT_FOUND: {
            'model': BaseErrorResponse,
            'description': 'Task not found.',
        },
    },
)
async def get_task(
        task_id: UUID4,
        _: str = Depends(oauth2_scheme)
) -> TaskResponse:
    """Delete user."""
    async with await Database().get_session() as session:
        async with session.begin():
            task: TaskModel = (
                await session.execute(
                    select(TaskModel).where(TaskModel.id == task_id).options(
                        selectinload(TaskModel.watcher_associations),
                        selectinload(TaskModel.executor_associations),
                    )
                )
            ).scalar_one_or_none()
            if not task:
                raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail='Task not found.')
            task: TaskDB = task.to_schema()
    return TaskResponse(payload=task)


@app.patch(
    path='/{task_id}',
    status_code=HTTP_200_OK,
    responses={
        HTTP_200_OK: {
            'model': TaskResponse,
            'description': 'Task updated successfully.',
        },
        HTTP_404_NOT_FOUND: {
            'model': BaseErrorResponse,
            'description': 'Task not found.',
        },
        HTTP_400_BAD_REQUEST: {
            'model': BaseErrorResponse,
            'description': 'Invalid input data.',
        },
    },
)
async def update_task(
        task_id: UUID4,
        update_data: UpdateTaskRequest,
        _: str = Depends(oauth2_scheme)
) -> TaskResponse:
    """Update task."""
    async with await Database().get_session() as session:
        async with session.begin():
            query = update(TaskModel).where(TaskModel.id == task_id)

            if 'title' in update_data.model_fields_set:
                query = query.values(title=update_data.title)

            if 'description' in update_data.model_fields_set:
                query = query.values(description=update_data.description)

            if 'status' in update_data.model_fields_set:
                query = query.values(status=update_data.status)

            if 'author_id' in update_data.model_fields_set:
                query = query.values(author_id=update_data.author_id)

            if 'assignee_id' in update_data.model_fields_set:
                query = query.values(assignee_id=update_data.assignee_id)

            query = query.returning(TaskModel)
            query = query.options(
                selectinload(TaskModel.watcher_associations),
                selectinload(TaskModel.executor_associations),
            )

            try:
                result: Result = await session.execute(query)
                task: TaskModel = result.scalar_one()
            except sqlalchemy.exc.NoResultFound:
                raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail='Task not found.')
            except sqlalchemy.exc.IntegrityError:
                raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail='Wrong data provided.')
    return TaskResponse(payload=task.to_schema())


@app.delete(
    path='/{task_id}',
    status_code=HTTP_204_NO_CONTENT,
    responses={
        HTTP_204_NO_CONTENT: {
            'description': 'Task deleted successfully.',
        },
    },
)
async def delete_task(
        task_id: UUID4,
        _: str = Depends(oauth2_scheme)
) -> None:
    """Delete task."""
    async with await Database().get_session() as session:
        async with session.begin():
            task: TaskModel = (
                await session.execute(
                    select(TaskModel).where(TaskModel.id == task_id)
                )
            ).scalar_one_or_none()
            if not task:
                raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail='Task not found.')
            await session.delete(task)
            await session.commit()


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", 8000)), reload=True)
