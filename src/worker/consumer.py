"""Kafka consumer loop for executable hivemind.spawn commands."""

from __future__ import annotations

import asyncio
import logging
import os

from aiokafka import AIOKafkaConsumer

from bus.events import ArtifactType
from bus.producer import kafka_enabled
from bus.serde import bytes_to_envelope
from bus.topics import TOPIC_SPAWN
from worker.dispatch import dispatch_spawn_envelope

logger = logging.getLogger(__name__)

_SPAWN_COMMANDS = frozenset({ArtifactType.RUN_PARENT, ArtifactType.RUN_CHILD})


async def run_spawn_consumer(*, stop_event: asyncio.Event | None = None) -> None:
    """Consume RUN_PARENT/RUN_CHILD commands until stop_event is set."""

    if not kafka_enabled():
        logger.info("Spawn consumer idle: KAFKA_BOOTSTRAP unset (inline dispatch used)")
        if stop_event:
            await stop_event.wait()
        return

    consumer = AIOKafkaConsumer(
        TOPIC_SPAWN,
        bootstrap_servers=os.getenv("KAFKA_BOOTSTRAP", "").strip(),
        group_id="hivemind-workers",
        auto_offset_reset="latest",
        enable_auto_commit=True,
    )
    await consumer.start()
    logger.info("Spawn consumer started on %s", TOPIC_SPAWN)
    try:
        while True:
            if stop_event and stop_event.is_set():
                break
            records = await consumer.getmany(timeout_ms=500, max_records=50)
            for batch in records.values():
                for message in batch:
                    try:
                        envelope = bytes_to_envelope(message.value)
                    except Exception:
                        logger.exception("Failed to decode spawn message")
                        continue
                    if envelope.artifact_type not in _SPAWN_COMMANDS:
                        continue
                    try:
                        await dispatch_spawn_envelope(envelope)
                    except Exception:
                        logger.exception(
                            "Spawn dispatch failed for run %s command %s",
                            envelope.run_id,
                            envelope.artifact_type,
                        )
            if stop_event is None:
                await asyncio.sleep(0)
    finally:
        await consumer.stop()
        logger.info("Spawn consumer stopped")
