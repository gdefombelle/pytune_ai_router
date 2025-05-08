from app.core.settings import get_llm_backend, get_openai_key, get_ollama_url, get_supported_llm_models
from app.core.llm_backends.openai_backend import call_openai_llm
from app.core.llm_backends.ollama_backend import call_ollama_llm

async def call_llm(prompt: str, context: dict, metadata: dict = None) -> str:
    metadata = metadata or {}

    # 1. Récupérer backend et modèle
    backend = metadata.get("llm_backend") or get_llm_backend()
    llm_model = metadata.get("llm_model") or context.get("llm_model") or "mistral"

    # 2. Valider contre les modèles supportés
    supported_models = get_supported_llm_models()
    supported = supported_models.get(backend, set())

    if llm_model not in supported:
        raise ValueError(f"❌ LLM model '{llm_model}' is not supported for backend '{backend}'")

    # 3. Injecter dans le contexte (optionnel mais utile)
    context["llm_model"] = llm_model
    context["llm_backend"] = backend

    # 4. Appel du backend correspondant
    if backend == "openai":
        return await call_openai_llm(prompt, context)

    elif backend == "ollama":
        return await call_ollama_llm(prompt, context)

    else:
        raise ValueError(f"❌ Unsupported LLM backend: {backend}")
