from fastapi import APIRouter
from pydantic import BaseModel
from pathlib import Path
import hashlib

from app.services.tts_service import generate_tts

router = APIRouter(prefix="/tts", tags=["tts"])

TTS_DIR = Path("/var/pytune/tts")
TTS_DIR.mkdir(parents=True, exist_ok=True)

class TTSRequest(BaseModel):
    text: str
    lang: str = "en"
    voice: str = "alloy"

@router.post("/speak")
async def speak(req: TTSRequest):
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

    return {
        "audio_url": f"/tts/audio/{filename}",
        "cached": output_path.exists()
    }