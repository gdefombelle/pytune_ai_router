import httpx
from pytune_data.models import UserContext
from simple_logger.logger import get_logger

logger = get_logger("ai_router")

USER_SERVICE_URL = "http://localhost:8002"  # 🔥 interne Docker

async def resolve_user_context(user_id: int) -> UserContext:
    url = f"{USER_SERVICE_URL}/user/profile/context/internal/{user_id}"
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url)

        if response.status_code == 200:
            return UserContext(**response.json())
        else:
            logger.aerror(f"Failed to fetch user context: {response.status_code} {response.text}")
            raise Exception(f"Failed to fetch user context: {response.status_code}")
    except Exception as e:
        logger.acritical(f"Exception while resolving user context: {e}")
        raise
