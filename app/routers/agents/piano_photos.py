# --- pytune_piano/routers/piano_photos.py ---
from typing import List
from fastapi import Depends, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from pytune_auth_common.models.schema import UserOut
from pytune_auth_common.services.auth_checks import get_current_user
from app.models.policy_model import AgentResponse
from app.services.piano_identify_from_images_service import identify_piano_from_images  # à adapter selon ton projet
from pytune_data.minio_client import PIANO_SESSION_BUCKET, minio_client, TEMP_BUCKET_NAME
from pytune_helpers.images import compress_image, compress_image_and_extract_metadata
from io import BytesIO
from uuid import uuid4
from fastapi import APIRouter, UploadFile, File, HTTPException
from pytune_data.minio_client import minio_client, TEMP_BUCKET_NAME
from io import BytesIO
from pytune_helpers.images import compress_image
from app.core.prompt_builder import render_prompt_template
from app.models.piano_guess_model import PianoGuessInput
from fastapi import UploadFile, File, HTTPException
from app.services.piano_guess_model import guess_model_from_images as guess_model_service
from app.services.piano_report import generate_piano_summary_pdf
from app.utils.upload_images import upload_images_to_miniofiles
from pytune_data.piano_identification_session import create_identification_session, update_identification_session
from app.services.image_labelling import label_images_from_session

router = APIRouter(tags=["Photos"])

@router.post("/pianos/report", response_class=FileResponse)
async def generate_report_pdf(data: PianoGuessInput, files: List[UploadFile] = File(...)):
    urls = await upload_images_to_miniofiles(files)
    report_data = await guess_model_service(data, urls)

    # 📄 Génère le PDF
    pdf_bytes = generate_piano_summary_pdf(report_data, urls)

    # Optionnel: stockage temporaire sur disque
    path = "/tmp/piano_report.pdf"
    with open(path, "wb") as f:
        f.write(pdf_bytes)

    return FileResponse(path, filename="piano_report.pdf", media_type="application/pdf")


@router.post("/pianos/guess_model")
async def guess_model_from_images(data: PianoGuessInput, files: List[UploadFile] = File(...)):
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    # 📤 Upload files to MinIO
    urls = []
    for file in files:
        try:
            raw = await file.read()
            compressed = compress_image(raw)
            fname = f"guess_model_{uuid4().hex}_{file.filename.replace(' ', '_')}"
            minio_client.client.put_object(
                PIANO_SESSION_BUCKET, fname, compressed,
                length=compressed.getbuffer().nbytes,
                content_type="image/jpeg"
            )
            url = f"https://minio.pytune.com/{PIANO_SESSION_BUCKET}/{fname}"
            urls.append(url)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Upload failed: {e}")

    # 🧠 Call model hypothesis generator
    try:
        result = await guess_model_service(data.dict(), urls)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Model hypothesis failed: {e}")

    # 🧹 Clean-up
    for url in urls:
        key = url.split("/")[-1]
        try:
            minio_client.client.remove_object(TEMP_BUCKET_NAME, key)
        except Exception as e:
            print(f"[WARN] Failed to delete {key}: {e}")

    return {
        "model_hypothesis": result,
        "photos": [f.filename for f in files]
    }


@router.post("/photos/identify/{manufacturer_id}", response_model=AgentResponse, )
async def identify_from_photos(manufacturer_id: int, files: list[UploadFile] = File(...),
    user: UserOut = Depends(get_current_user)):

    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    # 📥 Upload images to MinIO (temp)
    photo_metadata = []
    urls = []
    for file in files:
        try:
            raw = await file.read()
            compressed, metadata = compress_image_and_extract_metadata(raw)
            fname = f"identify_{uuid4().hex}_{file.filename.replace(' ', '_')}"
            minio_client.client.put_object(
                PIANO_SESSION_BUCKET, fname, compressed,
                length=compressed.getbuffer().nbytes,
                content_type="image/jpeg"
            )
            url = f"https://minio.pytune.com/{PIANO_SESSION_BUCKET}/{fname}"
            urls.append(url)

             # Ajoute à la liste metadata associée
            metadata["filename"] = file.filename
            metadata["minio_url"] = url
            photo_metadata.append(metadata)
                
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Upload failed: {e}")

    # 🧠 Identification du piano
    try:
        result = await identify_piano_from_images(manufacturer_id, urls, image_metadata=photo_metadata)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Identification failed: {e}")

    # ✅ ICI —> Création de la session
    try:
        session = await create_identification_session(
            user_id=user.id,
            image_urls=urls,
            photo_metadata=photo_metadata,
            model_hypothesis=None,  # on le mettra après
            photo_labels=None,
            context_snapshot={
                "manufacturer_id": manufacturer_id,
                "age_method": result.get("age_method"),
                "source": "photos.identify",
                "inferred_scene": result.get("extra", {}).get("scene_description"),
                "sheet_music": result.get("extra", {}).get("sheet_music"),
                "estimated_value_eur": result.get("extra", {}).get("estimated_value_eur"),
                "value_confidence": result.get("extra", {}).get("value_confidence"),
            }
        )
        photo_labels = await label_images_from_session(session.id) 
        await update_identification_session(session.id, photo_labels=photo_labels)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Session creation failed: {e}")


    # ⭐ Tentative de deviner le modèle (guess_model_from_images)
    try:
        sheet_music_title = (result.get("extra", {}).get("sheet_music") or {}).get("title")
        model_data = {
            "brand": result.get("brand"),
            "distributor": result.get("distributor"),
            "serial_number": result.get("serial_number"),
            "year_estimated": result.get("age"),
            "category": result.get("category"),
            "type": result.get("type"),
            "size_cm": result.get("size_cm"),
            "nb_notes": result.get("nb_notes"),
            "sheet_music": sheet_music_title,
            "scene_description": result.get("extra", {}).get("scene_description"),
            "photos": result.get("extra", {}).get("photos", []),  # ou []
        }
        model_hypothesis = await guess_model_service(
            data=model_data,
            image_urls=urls
        )
        await update_identification_session(session.id, model_hypothesis=model_hypothesis)
    except Exception as e:
        print(f"[WARN] Model hypothesis failed: {e}")
        model_hypothesis = {}

    # 🧾 Construction réponse agent
    msg_parts = []
    fp = {
        "brand": result.get("brand"),
        "category": result.get("category"),
        "type": result.get("type"),
        "size_cm": result.get("size_cm"),
        "serial_number": result.get("serial_number"),
        "year_estimated": result.get("age"),
        "nb_notes": result.get("nb_notes") or 88,
    }

    if fp["brand"]: msg_parts.append(f"- Brand: **{fp['brand']}**")
    if fp["category"]: msg_parts.append(f"- Category: {fp['category'].capitalize()}")
    if fp["type"]: msg_parts.append(f"- Type: {fp['type']}")
    if fp["size_cm"]: msg_parts.append(f"- Size: {fp['size_cm']} cm")
    if fp["serial_number"]: msg_parts.append(f"- Serial number: {fp['serial_number']}")
    if fp["year_estimated"]: msg_parts.append(f"- Estimated year: {fp['year_estimated']}")

    message = "🎹 Photo analysis result:\n" + "\n".join(msg_parts)
    if result.get("age_method"):
        message += f"\n\n🧠 {result['age_method']}"

    return AgentResponse(
        message=message,
        context_update={
            "first_piano": fp,
            "extra": {
                "sheet_music": result.get("extra", {}).get("sheet_music"),
                "scene_description": result.get("extra", {}).get("scene_description"),
                "estimated_value_eur": result.get("extra", {}).get("estimated_value_eur"),
                "value_confidence": result.get("extra", {}).get("value_confidence"),
                "model_hypothesis": model_hypothesis or None  
            },
            "metadata": {
                "extracted_from_image": True,
                "session_id": str(session.id)
            }
        }
    )

@router.post("/photos/upload/{piano_id}")
async def upload_piano_photos(piano_id: int, files: list[UploadFile] = File(...)):
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded.")

    uploaded_urls = []
    for file in files:
        try:
            original_bytes = await file.read()
            compressed = compress_image(original_bytes)
            fname = f"piano_{piano_id}_{uuid4().hex}_{file.filename.replace(' ', '_')}"

            minio_client.client.put_object(
                TEMP_BUCKET_NAME,
                fname,
                compressed,
                length=compressed.getbuffer().nbytes,
                content_type="image/jpeg"
            )

            url = f"https://minio.pytune.com/{TEMP_BUCKET_NAME}/{fname}"
            uploaded_urls.append(url)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

    return {"status": "ok", "urls": uploaded_urls}
