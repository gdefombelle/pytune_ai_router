from typing import Optional
from pytune_data.models import UserContext
from pytune_data.user_data_service import get_user_context
from simple_logger.logger import get_logger

logger = get_logger("ai_router")


async def resolve_user_context(user_id: int, extra: Optional[dict] = None) -> dict:
    """
    Résout dynamiquement le contexte utilisateur pour une policy AI,
    en combinant les infos de base (UserContext) et des ajouts dynamiques.
    """
    try:
        # 1. Charger le contexte utilisateur depuis la base (via service local)
        user_context_obj: UserContext = await get_user_context(user_id)
        base_context = user_context_obj.model_dump()

        # 2. Fusionner avec les données additionnelles dynamiques
        if extra:
            base_context.update(extra)

        return base_context

    except Exception as e:
        await logger.acritical(f"❌ Erreur dans resolve_user_context: {e}")
        raise
