from app.core.settings import get_llm_backend, config
from app.core.llm_backends.openai_backend import call_openai_llm
from app.core.llm_backends.ollama_backend import call_ollama_llm

async def call_llm(prompt: str, context: dict, metadata: dict = None) -> str:
    backend = get_llm_backend()

    # Ordre de priorité : policy.yaml > contexte utilisateur > config par défaut
    llm_model = (
        (metadata or {}).get("llm_model")
        or context.get("llm_model")
        or config.OLLAMA_MODEL
        or "mistral"
    )

    context["llm_model"] = llm_model  # injecte dans le contexte pour usage backend

    if backend == "openai":
        return await call_openai_llm(prompt, context)

    elif backend == "ollama":
        return await call_ollama_llm(prompt, context)

    else:
        raise ValueError(f"❌ Unsupported LLM backend: {backend}")
