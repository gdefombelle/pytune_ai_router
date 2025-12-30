# tts_service.py
from openai import OpenAI
from pytune_configuration import config
from pathlib import Path

client = OpenAI(api_key=config.OPENAI_API_KEY)

def generate_tts(
    *,
    text: str,
    output_path: Path,
    voice: str = "alloy",
    model: str = "gpt-4o-mini-tts",
) -> None:
    """
    Génère un fichier audio OpenAI TTS à l'emplacement demandé.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with client.audio.speech.with_streaming_response.create(
        model=model,
        voice=voice,
        input=text,
    ) as response:
        response.stream_to_file(output_path)