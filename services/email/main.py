import json
import os
import asyncio

from aio_pika import ExchangeType, connect_robust

async def main():
    rabbit_host = os.getenv("RABBITMQ_HOST", "localhost")
    rabbit_user = os.getenv("RABBITMQ_USER", "guest")
    rabbit_pass = os.getenv("RABBITMQ_PASS", "guest")
    rabbit_port = int(os.getenv("RABBITMQ_PORT", 5672))

    connection = await connect_robust(
        host=rabbit_host,
        port=rabbit_port,
        login=rabbit_user,
        password=rabbit_pass
    )

    async with connection:
        channel = await connection.channel()

        queue = await channel.declare_queue(
            name="email",
            durable=True
        )

        exchange = await channel.declare_exchange(
            name="event",
            type=ExchangeType.DIRECT,
            durable=True
        )

        routing_key = "user.registered"
        await queue.bind(exchange, routing_key=routing_key)

        async with queue.iterator() as queue_iter:
            async for message in queue_iter:
                async with message.process():
                    print(f"Send mail to {json.loads(message.body.decode())['data']['email']}")

if __name__ == "__main__":
    asyncio.run(main())