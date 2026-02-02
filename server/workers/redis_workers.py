import redis.asyncio as redis
import asyncio
import uuid
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional, List, Tuple
from ..models.routing_state_machine import Message, MessageState, transition, send_via_channel, human_delay


class RedisClient:
    def __init__(self, host="localhost", port=6379, db=0, password=None, ssl=False):
        self.client = redis.Redis(
            host=host,
            port=port,
            db=db,
            password=password,
            ssl=ssl,
            decode_responses=True,
            socket_keepalive=True,
            socket_keepalive_options={},
            health_check_interval=30
        )

    async def get_client(self):
        return self.client

    async def test_connection(self) -> bool:
        """Test Redis connection"""
        try:
            client = await self.get_client()
            await client.ping()
            return True
        except Exception as e:
            logging.error(f"Redis connection test failed: {e}")
            return False


# Global Redis client instance
redis_client = RedisClient()


async def acquire_lock(redis_conn, key: str, ttl: int = 30) -> bool:
    """
    Acquire a distributed lock using Redis
    """
    try:
        return await redis_conn.set(key, "1", ex=ttl, nx=True)
    except Exception as e:
        logging.error(f"Failed to acquire lock {key}: {e}")
        return False


async def release_lock(redis_conn, key: str):
    """
    Release a distributed lock
    """
    try:
        await redis_conn.delete(key)
    except Exception as e:
        logging.error(f"Failed to release lock {key}: {e}")


async def enqueue_message(to: str, text: str, channel: str, fallback_channels: List[str] = None, priority: int = 1) -> str:
    """
    Enqueue a message in Redis with initial state
    """
    if fallback_channels is None:
        fallback_channels = []

    msg_id = str(uuid.uuid4())

    # Store message data in Redis hash
    message_data = {
        "id": msg_id,
        "to": to,
        "text": text,
        "channel": channel,
        "state": MessageState.QUEUED.value,
        "attempts": 0,
        "fallback_channels": ",".join(fallback_channels),
        "created_at": datetime.now().isoformat(),
        "priority": priority,
        "expires_at": (datetime.now() + timedelta(hours=24)).isoformat()  # Expires in 24 hours
    }

    client = await redis_client.get_client()
    pipe = client.pipeline()

    # Store message data
    pipe.hset(f"msg:{msg_id}", mapping=message_data)

    # Add to send queue with priority consideration
    if priority > 1:
        # Higher priority messages go to the front of the queue
        pipe.lpush("queue:send", msg_id)
    else:
        # Normal priority messages go to the back
        pipe.rpush("queue:send", msg_id)

    # Execute pipeline
    await pipe.execute()

    logging.info(f"Message {msg_id} enqueued for {to} via {channel}")
    return msg_id


async def get_message(msg_id: str) -> Optional[Message]:
    """
    Retrieve a message from Redis and convert to Message object
    """
    try:
        client = await redis_client.get_client()
        data = await client.hgetall(f"msg:{msg_id}")

        if not data or 'id' not in data:
            logging.warning(f"Message {msg_id} not found in Redis")
            return None

        # Check if message has expired
        if 'expires_at' in data:
            from datetime import datetime
            expires_at = datetime.fromisoformat(data['expires_at'])
            if datetime.now() > expires_at:
                logging.info(f"Message {msg_id} has expired, removing from queue")
                await client.delete(f"msg:{msg_id}")
                return None

        msg = Message(
            id=data['id'],
            to=data['to'],
            text=data['text'],
            channel=data.get('channel')
        )

        # Set state
        if 'state' in data:
            try:
                msg.state = MessageState(data['state'])
            except ValueError:
                logging.warning(f"Invalid state {data['state']} for message {msg_id}, using default")
                msg.state = MessageState.QUEUED

        # Set attempts
        if 'attempts' in data:
            try:
                msg.attempts = int(data['attempts'])
            except ValueError:
                msg.attempts = 0

        # Set fallback channels
        if 'fallback_channels' in data and data['fallback_channels']:
            msg.fallback_channels = data['fallback_channels'].split(',')

        # Set error if present
        if 'last_error' in data:
            msg.last_error = data['last_error']

        # Set priority
        if 'priority' in data:
            try:
                msg.priority = int(data['priority'])
            except ValueError:
                msg.priority = 1

        # Set expiration time
        if 'expires_at' in data:
            try:
                from datetime import datetime
                msg.expires_at = datetime.fromisoformat(data['expires_at']).timestamp()
            except ValueError:
                pass

        return msg
    except Exception as e:
        logging.error(f"Error retrieving message {msg_id} from Redis: {e}")
        return None


async def update_message(msg: Message):
    """
    Update message state in Redis
    """
    try:
        client = await redis_client.get_client()

        await client.hset(f"msg:{msg.id}", mapping={
            "state": msg.state.value,
            "attempts": msg.attempts,
            "channel": msg.channel or "",
            "last_error": msg.last_error or "",
            "sent_at": msg.sent_at or "",
            "confirmed_at": msg.confirmed_at or "",
            "retry_after": msg.retry_after or ""
        })
    except Exception as e:
        logging.error(f"Error updating message {msg.id} in Redis: {e}")


async def send_worker():
    """
    Async worker to process messages from the send queue
    """
    logging.info("Send worker started")

    while True:
        try:
            client = await redis_client.get_client()

            # Block for up to 5 seconds waiting for a message
            result = await client.brpop("queue:send", timeout=5)

            if not result:
                # Timeout occurred, continue loop
                continue

            _, msg_id = result  # brpop returns (key, value)

            # Acquire lock to prevent duplicate processing
            lock_key = f"lock:msg:{msg_id}"
            acquired = await acquire_lock(client, lock_key, ttl=60)

            if not acquired:
                logging.warning(f"Could not acquire lock for message {msg_id}, skipping")
                continue

            try:
                # Get message from Redis
                msg = await get_message(msg_id)

                if not msg:
                    logging.warning(f"Message {msg_id} not found in Redis after lock acquisition")
                    continue

                # Check if message should be retried based on retry_after timestamp
                if msg.retry_after and msg.retry_after > time.time():
                    # Put message back in queue for later processing
                    await client.lpush("queue:send", msg_id)
                    continue

                # Update state to sending
                if transition(msg, "send"):
                    await update_message(msg)

                # Add human-like delay
                human_delay()

                # Attempt to send via channel
                try:
                    send_via_channel(msg)
                    if transition(msg, "success"):
                        await update_message(msg)
                        logging.info(f"Message {msg.id} sent successfully via {msg.channel}")
                except Exception as e:
                    msg.last_error = str(e)
                    msg.attempts += 1
                    logging.error(f"Failed to send message {msg.id} via {msg.channel}: {str(e)}. Attempt {msg.attempts}/{msg.max_attempts}")

                    if msg.attempts < msg.max_attempts:
                        if transition(msg, "retry"):
                            # Re-queue for retry after delay
                            msg.retry_after = time.time() + (30 * msg.attempts)  # Exponential backoff
                            await update_message(msg)
                            await client.lpush("queue:send", msg_id)
                    else:
                        if transition(msg, "fallback"):
                            await update_message(msg)

                            # Move to fallback queue if fallback channels available
                            if msg.fallback_channels:
                                await fallback_worker(msg)
                            else:
                                # No fallback options, mark as failed
                                msg.state = MessageState.FAILED
                                await update_message(msg)
                                logging.warning(f"Message {msg.id} failed after all attempts and fallbacks")

                # Update message state in Redis
                await update_message(msg)

                # If successful, move to confirmation queue
                if msg.state == MessageState.SENT:
                    await client.lpush("queue:confirm", msg_id)
                    logging.info(f"Message {msg.id} moved to confirmation queue")

            except Exception as e:
                logging.error(f"Error processing message {msg_id} in send_worker: {e}")
            finally:
                # Always release the lock
                await release_lock(client, lock_key)

        except asyncio.CancelledError:
            logging.info("Send worker cancelled")
            break
        except KeyboardInterrupt:
            logging.info("Send worker shutting down...")
            break
        except Exception as e:
            logging.error(f"Unexpected error in send worker: {e}")
            await asyncio.sleep(5)  # Longer pause on unexpected errors


async def fallback_worker(msg: Message):
    """
    Handle fallback logic when primary channel fails
    """
    try:
        client = await redis_client.get_client()

        if not msg.fallback_channels:
            msg.state = MessageState.FAILED
            await update_message(msg)
            logging.info(f"Message {msg.id} failed - no fallback channels available")
            return

        # Switch to next fallback channel
        msg.channel = msg.fallback_channels.pop(0)
        msg.attempts = 0

        if transition(msg, "reroute"):
            # Update in Redis
            await update_message(msg)

            # Add back to send queue
            await client.lpush("queue:send", msg.id)
            logging.info(f"Message {msg.id} falling back to channel: {msg.channel}")
    except Exception as e:
        logging.error(f"Error in fallback_worker for message {msg.id}: {e}")


async def confirm_worker():
    """
    Worker to check for delivery confirmations
    """
    logging.info("Confirmation worker started")

    while True:
        try:
            client = await redis_client.get_client()

            # Get messages from confirmation queue
            result = await client.brpop("queue:confirm", timeout=5)

            if not result:
                continue

            _, msg_id = result

            # Acquire lock
            lock_key = f"lock:msg:{msg_id}"
            acquired = await acquire_lock(client, lock_key, ttl=30)

            if not acquired:
                continue

            try:
                msg = await get_message(msg_id)

                if not msg:
                    continue

                # In a real system, this would check external services for receipts
                # For now, we'll simulate confirmation after a delay
                await asyncio.sleep(2)  # Simulate time to receive confirmation

                # Check if confirmation was received
                # (In real implementation, this would check external systems)
                from ..models.routing_state_machine import receipt_seen
                if receipt_seen(msg):
                    if transition(msg, "confirm"):
                        await update_message(msg)
                        logging.info(f"Message {msg_id} confirmed delivered")
                else:
                    # Confirmation timeout - optimistically mark as confirmed
                    if transition(msg, "timeout"):
                        await update_message(msg)
                        logging.info(f"Message {msg_id} marked confirmed (timeout)")

            except Exception as e:
                logging.error(f"Error processing confirmation for message {msg_id}: {e}")
            finally:
                await release_lock(client, lock_key)

        except asyncio.CancelledError:
            logging.info("Confirm worker cancelled")
            break
        except KeyboardInterrupt:
            logging.info("Confirm worker shutting down...")
            break
        except Exception as e:
            logging.error(f"Unexpected error in confirm worker: {e}")
            await asyncio.sleep(5)  # Longer pause on unexpected errors


async def cleanup_expired_messages():
    """
    Periodically clean up expired messages from Redis
    """
    logging.info("Starting expired message cleanup task")

    while True:
        try:
            client = await redis_client.get_client()

            # Get all message keys
            message_keys = await client.keys("msg:*")

            for key in message_keys:
                data = await client.hgetall(key)
                if 'expires_at' in data:
                    from datetime import datetime
                    try:
                        expires_at = datetime.fromisoformat(data['expires_at'])
                        if datetime.now() > expires_at:
                            # Message has expired, remove it
                            await client.delete(key)
                            msg_id = data.get('id', 'unknown')
                            logging.info(f"Removed expired message {msg_id}")
                    except ValueError:
                        # Invalid date format, skip
                        continue

            # Wait 1 hour before next cleanup
            await asyncio.sleep(3600)

        except Exception as e:
            logging.error(f"Error in cleanup_expired_messages: {e}")
            await asyncio.sleep(300)  # Wait 5 minutes before retrying


async def queue_manager():
    """
    Main function to run all workers
    """
    logging.info("Starting queue manager...")

    # Run all workers concurrently
    await asyncio.gather(
        send_worker(),
        confirm_worker(),
        cleanup_expired_messages()
    )


# Example usage
if __name__ == "__main__":
    # Example of how to use the system
    async def example():
        # Enqueue a message
        msg_id = await enqueue_message(
            to="+1234567890",
            text="Hello from the LLM messaging service!",
            channel="sms",
            fallback_channels=["email", "rcs"]
        )

        print(f"Enqueued message with ID: {msg_id}")

        # Start the workers
        await queue_manager()

    # asyncio.run(example())