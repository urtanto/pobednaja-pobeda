import asyncio
import json
import os
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any, AsyncGenerator, Optional

import jwt
import uvicorn
from aio_pika import ExchangeType, IncomingMessage, Message, RobustChannel, connect_robust
from aio_pika.abc import AbstractExchange, AbstractIncomingMessage, AbstractRobustConnection
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from starlette.requests import Request
from starlette.status import HTTP_200_OK

from services.auth.database.connector import Database
from services.auth.database.models import Users

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


async def rpc_user_get(msg: AbstractIncomingMessage):
    async with msg.process():
        body = json.loads(msg.body.decode())
        user_id = body.get("user_id", None)
        user_email = body.get("email", None)

        if not user_id and not user_email:
            res = {
                "type": "error",
                "data": {
                    "error": "User ID or email is required"
                }
            }
        else:
            async with await Database().get_session() as session:
                async with session.begin():
                    if user_id:
                        user: Users = (
                            await session.execute(
                                select(Users).where(Users.id == uuid.UUID(user_id))
                            )
                        ).scalar_one_or_none()
                    else:
                        user: Users = (
                            await session.execute(
                                select(Users).where(Users.email == user_email)
                            )
                        ).scalar_one_or_none()

                    if user:
                        res = {
                            "type": "success",
                            "data": {
                                "id": str(user.id),
                                "email": user.email,
                                "password": user.password
                            }
                        }
                    else:
                        res = {
                            "type": "error",
                            "data": {
                                "error": "User not found"
                            }
                        }

        channel = await app.state.amqp_connection.channel()

        await channel.default_exchange.publish(
            Message(
                body=json.dumps(res).encode(),
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

    queue = await channel.declare_queue("user.get", durable=False)
    await queue.bind(exchange, routing_key="user.get")
    await queue.consume(rpc_user_get)

    await asyncio.Future()


async def rpc_call(routing_key: str, data: dict):
    corr_id = str(uuid.uuid4())

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

class UserInfo(UserPublic):
    watchers: int = 0
    executors: int = 0


class AuthUserResponse(BaseModel):
    status: int = HTTP_200_OK
    error: bool = False
    access_token: str
    token_type: str = 'bearer'


def _hash_password(password: str) -> str:
    return pwd_context.hash(password)


def _verify_password(password: str, hashed: str) -> bool:
    return pwd_context.verify(password, hashed)


def _create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(UTC) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


async def _get_user(email: str) -> Optional[Users]:
    async with await Database().get_session() as session:
        async with session.begin():
            user: Users = (
                await session.execute(
                    select(Users).where(Users.email == email)
                )
            ).scalar_one_or_none()
            return user


async def _authenticate_user(email: str, password: str) -> Optional[Users]:
    user = await _get_user(email)
    if not user or not _verify_password(password, user.password):
        return None
    return user


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
    return UserPublic(id=user.id, email=user.email)


@app.post("/register", response_model=UserPublic, status_code=status.HTTP_201_CREATED)
async def register(user: UserCreate, exchange: AbstractExchange = Depends(auth_exchange)):
    if await _get_user(user.email):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User already exists")

    async with await Database().get_session() as session:
        async with session.begin():
            new_user = Users(
                email=user.email,
                password=_hash_password(user.password),
            )
            session.add(new_user)
            await session.flush()
            await exchange.publish(
                message=Message(
                    body=json.dumps(
                        {
                            "type": "user registered",
                            "data": {
                                "email": new_user.email,
                            }
                        }
                    ).encode(),
                    content_type="application/json",
                ),
                routing_key="user.registered",
            )

    return UserPublic(id=new_user.id, email=new_user.email)


@app.post("/login", response_model=AuthUserResponse)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = await _authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password")
    access_token = _create_access_token(data={"sub": user.email})
    return AuthUserResponse(access_token=access_token)


@app.get("/info", response_model=UserInfo)
async def read_users_me(current_user: UserPublic = Depends(_get_current_user)):
    watchers = await rpc_call("tasks.watchers", {"user_id": str(current_user.id)})
    executors = await rpc_call("tasks.executors", {"user_id": str(current_user.id)})
    return UserInfo(
        id=current_user.id,
        email=current_user.email,
        watchers=len(watchers["data"]),
        executors=len(executors["data"])
    )


@app.get("/healthz", tags=["healthz"])
async def healthz():
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", 8000)), reload=True)
