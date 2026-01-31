import redis.asyncio as redis
from typing import Optional
import os


class RedisConfig:
    def __init__(
        self,
        host: str = os.getenv("REDIS_HOST", "localhost"),
        port: int = int(os.getenv("REDIS_PORT", "6379")),
        db: int = int(os.getenv("REDIS_DB", "0")),
        password: Optional[str] = os.getenv("REDIS_PASSWORD"),
        ssl: bool = os.getenv("REDIS_SSL", "false").lower() == "true"
    ):
        self.host = host
        self.port = port
        self.db = db
        self.password = password
        self.ssl = ssl


def create_redis_client(config: RedisConfig) -> redis.Redis:
    """
    Create and return a Redis client instance
    """
    return redis.Redis(
        host=config.host,
        port=config.port,
        db=config.db,
        password=config.password,
        ssl=config.ssl,
        decode_responses=True
    )


# Global Redis client instance
redis_config = RedisConfig()
redis_client = create_redis_client(redis_config)


async def get_redis_client() -> redis.Redis:
    """
    Get the global Redis client instance
    """
    return redis_client


# Connection test function
async def test_connection():
    """
    Test Redis connection
    """
    try:
        client = await get_redis_client()
        await client.ping()
        print("Connected to Redis successfully!")
        return True
    except Exception as e:
        print(f"Failed to connect to Redis: {e}")
        return False