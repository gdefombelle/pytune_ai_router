# ===============================
# Étape 1 : Build avec UV
# ===============================
FROM --platform=linux/amd64 python:3.12-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

RUN pip install uv

WORKDIR /app

# Copie du workspace root (pyproject + lock)
COPY pyproject.toml uv.lock ./

# Copie du repo complet (packages + services)
COPY src ./src

# Aller dans CE service
WORKDIR /app/src/services/pytune_ai_router

# Installation des deps du workspace + service
RUN uv sync --no-dev


# ===============================
# Étape 2 : Image finale
# ===============================
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# ❗️IMPORTANT : on se place dans le dossier du service
# pour que "app.main" soit résolu correctement
WORKDIR /app/src/services/pytune_ai_router

# Copier tout le workspace + la venv
COPY --from=builder /app /app

EXPOSE 8006

# Lancement via la venv globale du workspace
CMD ["/app/.venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8006"]