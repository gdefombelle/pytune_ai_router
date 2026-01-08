from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from pathlib import Path
import hashlib
import os

from pytune_auth_common.models.schema import UserOut

from app.services.tts_service import generate_tts

router = APIRouter(prefix="/tts", tags=["tts"])

TTS_DIR = Path(os.getenv("TTS_AUDIO_DIR", "/tmp/pytune/tts"))
TTS_DIR.mkdir(parents=True, exist_ok=True)

class TTSRequest(BaseModel):
    text: str
    lang: str = "en"
    voice: str = "alloy"

@router.post("/speak")
async def speak(req: TTSRequest, request: Request):
    key = hashlib.sha1(
        f"{req.text}|{req.lang}|{req.voice}".encode()
    ).hexdigest()

    filename = f"tts_{key}_{req.lang}_{req.voice}.mp3"
    output_path = TTS_DIR / filename

    if not output_path.exists():
        generate_tts(
            text=req.text,
            output_path=output_path,
            voice=req.voice,
        )

    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("host")

    base = f"{scheme}://{host}"

    return {
        "audio_url": f"{base}/tts/audio/{filename}",
        "cached": output_path.exists(),
    }