import asyncio
import os
import ssl

import asyncclick as click
from aiomqtt import MqttError

from misc import logger
from mqtt_client import Client
from scheduler_service import Scheduler


async def run(ssl_context, scheduler):
    loop = asyncio.get_running_loop()
    async with Client(
            os.environ['MQTT_HOSTNAME'],
            identifier='scheduler',
            port=8883,
            keepalive=60,
            tls_context=ssl_context,
            max_concurrent_outgoing_calls=2000,
    ) as client:
        # The scheduler instance (and its last-known-good plan) survives
        # reconnects; only the client is renewed per connection.
        scheduler.client = client
        scheduler_task = loop.create_task(scheduler.start())
        client.pending_calls_threshold = 500
        await client.subscribe('api/schedule/update', qos=1)
        try:
            async for message in client.messages:
                if message.topic.matches('api/schedule/update'):
                    await scheduler.load()
        finally:
            scheduler_task.cancel()


@click.command()
@click.option('--ca_certificate', default='/opt/tls/ca_certificate.pem')
@click.option('--client_certificate', default='/opt/tls/client_certificate.pem')
@click.option('--client_key', default='/opt/tls/client_key.pem')
async def main(ca_certificate, client_certificate, client_key):
    ssl_context = ssl.create_default_context(cafile=ca_certificate)
    ssl_context.load_cert_chain(
        client_certificate, client_key)
    scheduler = Scheduler()
    # Reconnect with backoff instead of exiting on broker disconnect.
    while True:
        try:
            await run(ssl_context, scheduler)
        except MqttError as e:
            logger.error('MQTT connection lost (%s); reconnecting in 5s', e)
            await asyncio.sleep(5)


if __name__ == '__main__':
    main()
