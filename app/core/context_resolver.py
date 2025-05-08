from typing import Optional

from pytune_auth_common.models.schema import UserOut
from pytune_data.models import UserContext
from pytune_data.user_data_service import get_user_context
from simple_logger.logger import get_logger

logger = get_logger("ai_router")

async def resolve_user_context(user: UserOut, extra: Optional[dict] = None) -> dict:
    """
    Construit un dictionnaire de contexte utilisateur riche à partir :
    - de l'objet UserOut
    - de UserContext (chargé depuis la DB)
    - d’un dictionnaire extra fourni à la volée par le client
    """

    try:
        # 1. Départ : dictionnaire de base depuis UserOut
        full_context = {
            "user_id": user.id,
            "email": str(user.email),
            "user_type": str(user.user_type),
            "client_status": str(user.client_status),
            "oauth_provider": user.oauth_provider,
            "firstname": user.first_name,
            "lastname": user.last_name,
        }

        # 2. Ajout du contexte enrichi de la base
        user_context_obj: UserContext = await get_user_context(user.id)
        base_ctx = user_context_obj.model_dump()
        full_context.update(base_ctx)

        # 3. Injection intelligente des données extra
        if extra:
            for key, value in extra.items():
                if key == "user_input":
                    full_context["user_input"] = value
                elif "user_profile" in full_context and key in full_context["user_profile"]:
                    # Mise à jour dans user_profile si la clé y existe
                    full_context["user_profile"][key] = value
                else:
                    # Sinon on ajoute à la racine
                    full_context[key] = value

        return full_context

    except Exception as e:
        await logger.acritical(f"❌ Erreur dans resolve_user_context: {e}")
        raise
