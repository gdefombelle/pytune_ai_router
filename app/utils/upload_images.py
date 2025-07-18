from fastapi import UploadFile, HTTPException
from typing import List
from uuid import uuid4
from io import BytesIO
from PIL import Image
import mimetypes

from pytune_data import minio_client, BUCKET_NAME, COLLECTION_NAME
from pytune_helpers.images import compress_image


async def upload_images_to_miniofiles(
    files: List[UploadFile],
    bucket: str = BUCKET_NAME,
    compress: bool = True,
    prefix: str = "image"
) -> List[str]:
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")
    
    urls = []

    for file in files:
        try:
            raw = await file.read()
            buffer = compress_image(raw) if compress else BytesIO(raw)
            fname = f"{prefix}_{uuid4().hex}_{file.filename.replace(' ', '_')}"

            content_type = file.content_type or mimetypes.guess_type(fname)[0] or "application/octet-stream"

            minio_client.put_object(
                bucket,
                fname,
                buffer,
                length=buffer.getbuffer().nbytes,
                content_type=content_type
            )

            url = f"https://minio.pytune.com/{bucket}/{fname}"
            urls.append(url)

        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Upload failed for {file.filename}: {e}")
    
    return urls
