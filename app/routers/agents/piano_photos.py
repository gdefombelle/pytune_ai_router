# --- pytune_piano/routers/piano_photos.py ---
import asyncio
import json
from typing import Annotated, List, Optional
from fastapi import Depends, Form, UploadFile, File, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pydantic import ValidationError
from pytune_auth_common.models.schema import UserOut
from pytune_auth_common.services.auth_checks import get_current_user
from app.models.policy_model import AgentResponse
from app.services.piano_identify_from_images_service import identify_piano_from_images  # à adapter selon ton projet
from pytune_data.crud import get_user_by_id
from pytune_data.minio_client import PIANO_SESSION_IMAGES_BUCKET, minio_client, TEMP_BUCKET_NAME
from pytune_data.models import PianoIdentificationSession, PianoModel, User, UserPianoModel
from pytune_data.piano_model_data_service import resolve_kind_id, resolve_piano_type_id
from pytune_data.schemas import SaveUserPianoModelOut, UserPianoModelCreate
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
from app.services.piano_report import generate_clean_piano_summary_pdf
from app.utils.upload_images import upload_images_to_miniofiles
from pytune_data.piano_identification_session import create_identification_session, get_identification_session, update_identification_session
from app.services.image_labelling import label_images_from_session
from app.utils.context_helpers import build_context_snapshot, build_model_data
from app.services.email_sender import send_piano_summary_email
from pytune_helpers.pdf import upload_pdf_and_get_url
from app.services.music_enrichment import trigger_music_source_enrichment
from simple_logger import get_logger, logger, SimpleLogger
import os
from fastapi import Body
from pytune_llm.task_reporting.reporter import TaskReporter
logger: SimpleLogger = get_logger() 

router = APIRouter(tags=["Photos"])

# ✅ Nouveau endpoint FastAPI pour envoyer le rapport par email

@router.post("/api/send_piano_report/{session_id}")
async def send_piano_report(
    session_id: UUID,
    data: dict = Body(...),
    user: UserOut = Depends(get_current_user)
):
    reporter = TaskReporter(agent="piano_agent", total_steps=5, delay_after_step=0.05)

    await reporter.step("📦 Fetching session")
    session = await get_identification_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if not session.image_urls:
        raise HTTPException(status_code=400, detail="No images found for this session")

    user_piano_data = data.get("first_piano", {}) or {}
    request_source = data.get("request_source", "unknown")
    model_hyp = session.model_hypothesis or {}

    model_hypothesis_str = None
    if model_hyp.get("name"):
        model_hypothesis_str = f"{model_hyp['name']}"
        if model_hyp.get("variant"):
            model_hypothesis_str += f" {model_hyp['variant']}"
        if model_hyp.get("confidence") is not None:
            pct = round(float(model_hyp["confidence"]) * 100)
            model_hypothesis_str += f" (confidence: {pct}%)"

    report_data = {
        "brand": user_piano_data.get("brand") or model_hyp.get("brand"),
        "model": user_piano_data.get("model_name") or model_hypothesis_str,
        "size_cm": user_piano_data.get("size_cm") or model_hyp.get("size_cm"),
        "category": user_piano_data.get("kind") or model_hyp.get("category"),
        "type": user_piano_data.get("type_label") or model_hyp.get("type"),
        "serial_number": user_piano_data.get("serial_number") or model_hyp.get("serial_number"),
        "year_estimated": user_piano_data.get("manufacture_year") or model_hyp.get("year_estimated"),
        "nb_notes": user_piano_data.get("keys") or model_hyp.get("nb_notes"),
        "source": user_piano_data.get("extra_data", {}).get("user_input_source"),
        "model_hypothesis": model_hyp,
    }

    try:
        await reporter.step("🖼️ Downloading images")
        local_image_paths = await download_images_locally(session.image_urls)

        await reporter.step("📄 Generating PDF")
        pdf_buffer = await generate_clean_piano_summary_pdf(report_data, local_image_paths, session.photo_labels)

        await reporter.step("☁️ Uploading PDF")
        pdf_url = await upload_pdf_and_get_url(pdf_buffer)

        await update_identification_session(session_id=session.id, report_url=pdf_url)

    finally:
        for path in local_image_paths:
            try:
                os.remove(path)
            except Exception:
                pass

    try:
        await reporter.step("📧 Sending email")
        await send_piano_summary_email(user=user, pdf_url=pdf_url, piano_info=report_data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Email sending failed: {e}")

    await reporter.done("✅ Report sent")
    return JSONResponse({"success": True, "pdf_url" :pdf_url})

@router.post("/pianos/guess_model")
async def guess_model_from_images(
    data: PianoGuessInput, 
    files: List[UploadFile] = File(...)
):
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    reporter = TaskReporter(agent="piano_agent", total_steps=2, auto_progress=True)

    # 📤 Step 1: Upload files to MinIO
    await reporter.step("📤 Uploading images")
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

    # 🧠 Step 2: Generate model hypothesis
    await reporter.step("🧠 Generating model hypothesis")
    try:
        result = await guess_model_service(data.model_dump(), urls, reporter=reporter)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Model hypothesis failed: {e}")

    await reporter.done("✅ Done")

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

    reporter = TaskReporter("piano_agent", auto_progress=True, delay_after_step=0.5)

    # 🖼️ Upload
    await reporter.step("📤 Uploading photos to MinIO")
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

    photo_metadata = safe_json(photo_metadata)

    # 🎯 Identification principale
    await reporter.step("🔍 Identifying piano details")
    try:
        result = await identify_piano_from_images(
            manufacturer_id, 
            urls, 
            image_metadata=photo_metadata, 
            reporter=reporter)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Identification failed: {e}")

    # 🗂️ Session
    await reporter.step("🗂️ Creating session")
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

        # 🏷️ Labellisation images
        await reporter.step("🏷️ Labelling photos")
        raw_metadata, cleaned_labels = await label_images_from_session(session.id, reporter=reporter)
        await update_identification_session(session.id, photo_labels=cleaned_labels, metadata=raw_metadata)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Session creation failed: {e}")

    # 🔮 Hypothèse modèle
    await reporter.step("🔮 Guessing piano model")
    try:
        model_data = build_model_data(result)
        model_hypothesis = await guess_model_service(
            data=model_data,
            image_urls=urls,
            reporter=reporter  # 👈 passe-le pour avoir du suivi détaillé si implémenté
        )
        await update_identification_session(session.id, model_hypothesis=model_hypothesis)
    except Exception as e:
        logger.warning(f"Model hypothesis failed: {e}")
        model_hypothesis = {}

    await reporter.step("✅ Preparing final response")

    # 🎯 AgentResponse
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
    message = "🎹 Photo analysis result:\n" + "\n".join(filter(None, msg_parts))
    if result.get("age_method"):
        message += f"\n\n🧠 {result['age_method']}"

    await reporter.done()
        # 🚀 Tâche de fond : enrichir avec sources musicales (IMSLP, Spotify, etc.)
    asyncio.create_task(
        trigger_music_source_enrichment(
            piano_data=fp,
            sheet_music=result.get("extra", {}).get("sheet_music"),
            user_id=user.id,
            session_id=session.id
        )
    )
    return AgentResponse(
        message=message,
        context_update={
            "first_piano": fp,
            "extra": {
                # ---- déjà présent ----
                "sheet_music": result.get("extra", {}).get("sheet_music"),
                "scene_description": result.get("extra", {}).get("scene_description"),
                "estimated_value_eur": result.get("extra", {}).get("estimated_value_eur"),
                "value_confidence": result.get("extra", {}).get("value_confidence"),
                "model_hypothesis": model_hypothesis or None,

                # ---- 🔥 NOUVEAU : pour la galerie ----
                "image_urls": urls,             # liste d’URL (MinIO)
                "photo_previews": urls,         # alias au cas où
                "preview_urls": urls,           # alias au cas où
                "photo_metadata": photo_metadata,  # width/height/format/exif…
                "photo_labels": cleaned_labels,    # angle / notes / lighting / content / view_type…
            },
            "metadata": {
                "extracted_from_image": True,
                "session_id": str(session.id)
            }
        }
    )


@router.post("/pianos/{piano_id}/photos", response_model=AgentResponse)
async def upload_photos_for_piano_id(
    piano_id: int,
    files: List[UploadFile] = File(...),
    current_user: UserOut = Depends(get_current_user),
):
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    # 0) Ownership
    user_piano = await UserPianoModel.get_or_none(id=piano_id, user_id=current_user.id)
    if not user_piano:
        raise HTTPException(status_code=404, detail="Piano not found")

    reporter = TaskReporter("piano_agent", auto_progress=True, delay_after_step=0.5)

    # 1) Upload vers MinIO
    await reporter.step("📤 Uploading photos to MinIO")
    uploaded_urls: list[str] = []
    uploaded_meta_list: list[dict] = []

    for f in files:
        try:
            raw = await f.read()
            compressed, safe_meta = compress_image_and_extract_metadata(raw)

            fname = f"attach_{uuid4().hex}_{f.filename.replace(' ', '_')}"
            minio_client.client.put_object(
                PIANO_SESSION_IMAGES_BUCKET,
                fname,
                compressed,
                length=compressed.getbuffer().nbytes,
                content_type="image/jpeg",
            )

            url = f"https://minio.pytune.com/{PIANO_SESSION_IMAGES_BUCKET}/{fname}"
            uploaded_urls.append(url)

            safe_meta["filename"] = f.filename
            safe_meta["minio_url"] = url
            uploaded_meta_list.append(safe_meta)
        except Exception as e:
            logger.warning(f"Upload failed for {f.filename}: {e}")
            raise HTTPException(status_code=500, detail=f"Upload failed: {e}")

    # 2) Session : réutiliser si possible, sinon créer
    await reporter.step("🗂️ Attaching to session")
    session: Optional[PianoIdentificationSession] = None
    if user_piano.piano_identification_session_id:
        session = await PianoIdentificationSession.get_or_none(
            id=user_piano.piano_identification_session_id
        )

    if not session:
        ctx = {
            "first_piano": {
                "manufacturer_id": user_piano.manufacturer_id,
                "brand": getattr(user_piano, "brand", None),
                "category": user_piano.kind,
                "type": user_piano.type_label,
                "size_cm": user_piano.size_cm,
                "serial_number": user_piano.serial_number,
                "year_estimated": user_piano.manufacture_year,
                "nb_notes": user_piano.keys,
            },
            "manufacturer_id": user_piano.manufacturer_id,
            "extra": {},
        }
        session = await create_identification_session(
            user_id=current_user.id,
            image_urls=uploaded_urls,
            photo_metadata=safe_json(uploaded_meta_list),
            model_hypothesis=None,
            photo_labels=None,
            context_snapshot=ctx,
        )
        user_piano.piano_identification_session_id = session.id
        await user_piano.save()
    else:
        # Merge URLs/métadatas avec l’existant de la session
        try:
            existing_urls = []
            if isinstance(session.image_urls, list):
                existing_urls = session.image_urls
            elif isinstance(session.image_urls, str) and session.image_urls:
                existing_urls = json.loads(session.image_urls)
        except Exception:
            existing_urls = []

        try:
            existing_meta = []
            if isinstance(session.photo_metadata, list):
                existing_meta = session.photo_metadata
            elif isinstance(session.photo_metadata, str) and session.photo_metadata:
                existing_meta = json.loads(session.photo_metadata)
        except Exception:
            existing_meta = []

        merged_urls = list(dict.fromkeys([*existing_urls, *uploaded_urls]))
        merged_meta = [*existing_meta, *uploaded_meta_list]

        session.image_urls = safe_json(merged_urls)
        session.photo_metadata = safe_json(merged_meta)
        await session.save()

    # 3) Labellisation
    await reporter.step("🏷️ Labelling photos")
    raw_metadata, cleaned_labels = await label_images_from_session(session.id, reporter=reporter)
    await update_identification_session(session.id, photo_labels=cleaned_labels, metadata=raw_metadata)

    await reporter.done()

    # 4) Prépare les données pour l’UI (galerie)
    #    On relit ce qu’on a en base pour être sûr d’envoyer l’état cumulé.
    try:
        all_urls = []
        if isinstance(session.image_urls, list):
            all_urls = session.image_urls
        elif isinstance(session.image_urls, str) and session.image_urls:
            all_urls = json.loads(session.image_urls)
    except Exception:
        all_urls = uploaded_urls  # fallback minimal

    try:
        all_meta = []
        if isinstance(session.photo_metadata, list):
            all_meta = session.photo_metadata
        elif isinstance(session.photo_metadata, str) and session.photo_metadata:
            all_meta = json.loads(session.photo_metadata)
    except Exception:
        all_meta = uploaded_meta_list

    # 5) Réponse agent (on ne modifie pas first_piano ici)
    return AgentResponse(
        message="📸 Photos uploaded and linked to your piano.",
        context_update={
            "extra": {
                "image_urls": all_urls,
                # alias pour compat avec l’UI :
                "photo_previews": all_urls,
                "preview_urls": all_urls,
                "photo_metadata": all_meta,
                "photo_labels": cleaned_labels or [],
            },
            "metadata": {
                "session_id": str(session.id),
                "photos_attached": True,
            },
        },
        actions=[],
    )

# routes
@router.post("/piano/save", summary="Confirm and save user's piano model",
             response_model=SaveUserPianoModelOut)
async def save_user_piano_model(
    payload: UserPianoModelCreate,
    current_user: UserOut = Depends(get_current_user),
):
    from pytune_data.piano_model_data_service import resolve_model
    reporter = TaskReporter("piano_agent", total_steps=1)
    await reporter.step("💾 Saving your piano...")

    try:
        user = await get_user_by_id(current_user.id)

        # (facultatif) réutiliser la session si fournie; ne PAS lever 404 si absente
        session = None
        if payload.piano_identification_session_id:
            session = await PianoIdentificationSession.get_or_none(
                id=payload.piano_identification_session_id
            )
            # si non trouvée, on laisse session=None et on continue; on peut logger si besoin

        # Résoudre un modèle connu si possible
        # Résoudre un modèle connu si possible
        pianomodel_fk: Optional[int] = None

        if payload.pianomodel_id:
            pianomodel_fk = payload.pianomodel_id

        else:
            model_label: Optional[str] = payload.model_name

            # Fallback sur hypothesized_model si model_name est vide
            if not model_label and payload.extra_data:
                hypo = payload.extra_data.get("hypothesized_model")
                if hypo:
                    model_label = f"~{hypo}"  # ou juste hypo si tu ne veux pas du ~ dans le resolver

            if payload.manufacturer_id and model_label:
                pianomodel_fk = await resolve_model(
                    manufacturer_id=payload.manufacturer_id,
                    raw_label=model_label
                )

        if pianomodel_fk:
            logger.info(f"🎹 Model resolved: {pianomodel_fk} for label '{payload.model_name}'")
        else:
            logger.warning(f"⚠️ No model match for '{payload.model_name}' (manufacturer_id={payload.manufacturer_id})")

        kind_id: Optional[int] = None
        if payload.kind:
            kind_id = resolve_kind_id(payload.kind)

        piano_type_id: Optional[int] = None
        if kind_id and payload.type_label:
            piano_type_id = await resolve_piano_type_id(
                kind_id=kind_id,
                piano_type_label=payload.type_label,
                size_cm=payload.size_cm
            )

        if not session:
            # 🗂️ Session
            await reporter.step("🗂️ Creating session")
            session = await create_identification_session(
                user_id=current_user.id,
                image_urls=[],  # requis même si vide
                photo_labels=None,
                photo_metadata=None,
                context_snapshot=None,
                model_hypothesis=None,
                metadata=None,
                conversation_id=payload.conversation_id  # <-- nouveau champ à passer
            )


        # ✅ IMPORTANT : utiliser le bon nom de champ pour la FK modèle
        user_piano = await UserPianoModel.create(
            user=user,
            piano_model_id=pianomodel_fk,                         # mapping FK correct
            manufacturer_id=payload.manufacturer_id,
            name=payload.name,
            location=payload.location,
            serial_number=payload.serial_number,
            manufacture_year=payload.manufacture_year,
            purchase_year=payload.purchase_year,
            notes=payload.notes,
            model_name=model_label,
            kind=payload.kind,
            type_label=payload.type_label,
            size_cm=payload.size_cm,                              # ⚠️ size_cm (pas size)
            keys=payload.keys,
            extra_data=payload.extra_data or {},
            piano_identification_session_id=payload.piano_identification_session_id,
            kind_id= kind_id,
            piano_type_id=piano_type_id
        )

        await reporter.done("✅ Piano saved!")
        return SaveUserPianoModelOut(
            success=True,
            user_piano_id=user_piano.id,
            manufacturer_id=user_piano.manufacturer_id,
            pianomodel_id=pianomodel_fk,
            piano_identification_session_id=user_piano.piano_identification_session_id,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save piano: {e}")

