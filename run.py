import os
from pathlib import Path
import uvicorn
import dotenv
# from hypercorn.config import Config
# from hypercorn.asyncio import serve
from app.main import app 


def run_uvicorn():
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port =8006,
        reload= False,
    )


# Exécution du serveur selon la configuration
if __name__ == "__main__":
    run_uvicorn()

