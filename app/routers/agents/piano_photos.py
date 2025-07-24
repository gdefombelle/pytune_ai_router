# --- pytune_piano/routers/piano_photos.py ---
from typing import List
from fastapi import Depends, UploadFile, File, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pytune_auth_common.models.schema import UserOut
from pytune_auth_common.services.auth_checks import get_current_user
from app.models.policy_model import AgentResponse
from app.services.piano_identify_from_images_service import identify_piano_from_images  # à adapter selon ton projet
from pytune_data.crud import get_user_by_id
from pytune_data.minio_client import PIANO_SESSION_IMAGES_BUCKET, minio_client, TEMP_BUCKET_NAME
from pytune_data.models import PianoIdentificationSession, User, UserPianoModel
from pytune_data.schemas import UserPianoModelCreate
from pytune_helpers.images import compress_image, compress_image_and_extract_metadata, download_images_locally, safe_json
from io import BytesIO
from uuid import UUID, uuid4
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
from pytune_data.piano_identification_session import create_identification_session, get_identification_session, update_identification_session
from app.services.image_labelling import label_images_from_session
from app.utils.context_helpers import build_context_snapshot, build_model_data
from app.services.email_sender import send_piano_summary_email
from pytune_helpers.pdf import upload_pdf_and_get_url
from simple_logger import get_logger, logger, SimpleLogger


logger: SimpleLogger = get_logger() 

router = APIRouter(tags=["Photos"])

# ✅ Nouveau endpoint FastAPI pour envoyer le rapport par email

import os

@router.post("/api/send_piano_report/{session_id}")
async def send_piano_report(
    session_id: UUID,
    user: UserOut = Depends(get_current_user)
):
    session = await get_identification_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if not session.image_urls:
        raise HTTPException(status_code=400, detail="No images found for this session")

    report_data = {
        "brand": session.model_hypothesis.get("brand") or session.photo_labels[0].get("brand") if session.photo_labels else None,
        "year_estimated": session.model_hypothesis.get("year_estimated"),
        "model_hypothesis": session.model_hypothesis,
        "serial_number": session.model_hypothesis.get("serial_number"),
        "category": session.model_hypothesis.get("category"),
        "type": session.model_hypothesis.get("type"),
        "size_cm": session.model_hypothesis.get("size_cm"),
        "nb_notes": session.model_hypothesis.get("nb_notes"),
    }

    try:
        # ⬇️ Téléchargement
        local_image_paths = []
        local_image_paths = await download_images_locally(session.image_urls)

        # 📄 Génération PDF
        pdf_buffer = await generate_piano_summary_pdf(report_data, local_image_paths, session.photo_labels)
        # 🔼 Upload + URL
        pdf_url = await upload_pdf_and_get_url(pdf_buffer)
        await update_identification_session(session_id=session.id, report_url = pdf_url)
    finally:
        # 🧹 Nettoyage fichiers temporaires
        for path in local_image_paths:
            try:
                os.remove(path)
            except Exception:
                pass  # silencieux mais tu peux logguer si besoin

    try:
        await send_piano_summary_email(user=user, pdf_url=pdf_url, piano_info=report_data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Email sending failed: {e}")

    return JSONResponse({"success": True})


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
                PIANO_SESSION_IMAGES_BUCKET, fname, compressed,
                length=compressed.getbuffer().nbytes,
                content_type="image/jpeg"
            )
            url = f"https://minio.pytune.com/{PIANO_SESSION_IMAGES_BUCKET}/{fname}"
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

@router.post("/photos/identify/{manufacturer_id}", response_model=AgentResponse)
async def identify_from_photos(
    manufacturer_id: int,
    files: list[UploadFile] = File(...),
    user: UserOut = Depends(get_current_user)
):
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    # 📥 Upload to MinIO + collect metadata
    photo_metadata = []
    urls = []

    for file in files:
        try:
            raw = await file.read()
            compressed, safe_metadata = compress_image_and_extract_metadata(raw)

            fname = f"identify_{uuid4().hex}_{file.filename.replace(' ', '_')}"
            minio_client.client.put_object(
                PIANO_SESSION_IMAGES_BUCKET, fname, compressed,
                length=compressed.getbuffer().nbytes,
                content_type="image/jpeg"
            )

            url = f"https://minio.pytune.com/{PIANO_SESSION_IMAGES_BUCKET}/{fname}"
            urls.append(url)

            safe_metadata["filename"] = file.filename
            safe_metadata["minio_url"] = url
            photo_metadata.append(safe_metadata)

        except Exception as e:
            logger.warning(f"Upload failed for {file.filename}: {e}")
            raise HTTPException(status_code=500, detail=f"Upload failed: {e}")

    # 🛡️ Clean entire list before DB insert
    photo_metadata = safe_json(photo_metadata)

    # 🧠 Identification par vision
    try:
        result = await identify_piano_from_images(
            manufacturer_id, urls, image_metadata=photo_metadata
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Identification failed: {e}")

    # 🗂️ Création de session
    try:
        context_snapshot = build_context_snapshot(result, manufacturer_id)
        session = await create_identification_session(
            user_id=user.id,
            image_urls=urls,
            photo_metadata=photo_metadata,
            model_hypothesis=None,
            photo_labels=None,
            context_snapshot=context_snapshot,
        )

        raw_metadata, cleaned_labels = await label_images_from_session(session.id)
        await update_identification_session(session.id, photo_labels=cleaned_labels, metadata=raw_metadata)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Session creation failed: {e}")

    # 🎯 Devine le modèle
    try:
        model_data = build_model_data(result)
        model_hypothesis = await guess_model_service(
            data=model_data,
            image_urls=urls
        )
        await update_identification_session(session.id, model_hypothesis=model_hypothesis)
    except Exception as e:
        logger.warning(f"Model hypothesis failed: {e}")
        model_hypothesis = {}

    # 🧾 Réponse agent
    fp = {
        "manufacturer_id": result.get("manufacturer_id"),
        "brand": result.get("brand"),
        "category": result.get("category"),
        "type": result.get("type"),
        "size_cm": result.get("size_cm"),
        "serial_number": result.get("serial_number"),
        "year_estimated": result.get("age"),
        "nb_notes": result.get("nb_notes") or 88,
    }

    msg_parts = [
        f"- Brand: **{fp['brand']}**" if fp["brand"] else None,
        f"- Category: {fp['category'].capitalize()}" if fp["category"] else None,
        f"- Type: {fp['type']}" if fp["type"] else None,
        f"- Size: {fp['size_cm']} cm" if fp["size_cm"] else None,
        f"- Serial number: {fp['serial_number']}" if fp["serial_number"] else None,
        f"- Estimated year: {fp['year_estimated']}" if fp["year_estimated"] else None,
    ]
    msg_parts = [m for m in msg_parts if m]
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

@router.post("/piano/save", summary="Confirm and save user's piano model")
async def save_user_piano_model(
    payload: UserPianoModelCreate,
    current_user: UserOut = Depends(get_current_user)
):
    try:
        user = await get_user_by_id(current_user.id)
        session = None
        if payload.piano_identification_session_id:
            session = await PianoIdentificationSession.get_or_none(id=payload.piano_identification_session_id)
            if not session:
                raise HTTPException(status_code=404, detail="Identification session not found")

        user_piano = await UserPianoModel.create(
            user=user,
            pianomodel_id=payload.pianomodel_id,
            manufacturer_id=payload.manufacturer_id,
            name=payload.name,
            location=payload.location,
            serial_number=payload.serial_number,
            manufacture_year=payload.manufacture_year,
            purchase_year=payload.purchase_year,
            notes=payload.notes,
            model_name=payload.model_name,
            kind=payload.kind,
            type_label=payload.type_label,
            size_cm=payload.size_cm,
            keys=payload.keys,
            extra_data=payload.extra_data or {},
            piano_identification_session_id=payload.piano_identification_session_id
        )

        return {"success": True, "piano_id": user_piano.id}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save piano: {str(e)}")

