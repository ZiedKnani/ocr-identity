"""
main_v2.py - FastAPI avec IdProcessorV2 refactorisé
"""

from fastapi import FastAPI, File, UploadFile, HTTPException, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
import logging
import time
from typing import List, Optional, Tuple, Union
import datetime
import base64
import json
import binascii
import os
import re
import ntpath
import importlib
from io import BytesIO
from starlette.responses import Response
from PIL import Image, UnidentifiedImageError

from id_processor_v2 import IdProcessorV2
from document_types import DocumentType, DOCUMENT_CODE_MAP, DOCUMENT_FIELDS, get_document_features

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

try:
    smbclient = importlib.import_module("smbclient")
except Exception:
    smbclient = None

# Initialiser FastAPI
app = FastAPI(
    title="OCR Identity Extractor V2",
    description="Service OCR refactorisé avec Strategy Pattern",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _sanitize_log_payload(data):
    """Masque les champs sensibles pour les logs sans tronquer la réponse."""
    if isinstance(data, dict):
        sanitized = {}
        for key, value in data.items():
            key_lower = str(key).lower()
            if "base64" in key_lower and isinstance(value, str):
                sanitized[key] = f"<base64 len={len(value)}>"
            else:
                sanitized[key] = _sanitize_log_payload(value)
        return sanitized

    if isinstance(data, list):
        return [_sanitize_log_payload(item) for item in data]

    if isinstance(data, str):
        return data

    return data


def _debug_print_response(tag: str, payload: dict):
    """Affiche explicitement la réponse envoyée (mode debug manuel)."""
    try:
        safe_payload = _sanitize_log_payload(payload)
        text = json.dumps(safe_payload, ensure_ascii=False)
        print(f"[DEBUG_RESPONSE] {tag}: {text}")
        logger.info(f"[DEBUG_RESPONSE] {tag}: {text}")
    except Exception as e:
        print(f"[DEBUG_RESPONSE] {tag}: <serialization_error {e}>")
        logger.warning(f"[DEBUG_RESPONSE] {tag}: <serialization_error {e}>")


@app.middleware("http")
async def log_http_requests(request: Request, call_next):
    start_time = time.time()
    request_body = None

    if request.method in {"POST", "PUT", "PATCH"}:
        raw_body = await request.body()
        if raw_body:
            request._body = raw_body
            try:
                request_body = _sanitize_log_payload(json.loads(raw_body.decode("utf-8")))
            except Exception:
                request_body = f"<non-json body len={len(raw_body)}>"

    response = await call_next(request)

    response_body = b""
    async for chunk in response.body_iterator:
        response_body += chunk

    elapsed_ms = round((time.time() - start_time) * 1000, 2)
    log_prefix = f"HTTP {request.method} {request.url.path} -> {response.status_code} ({elapsed_ms} ms)"

    if request_body is not None:
        logger.info(f"{log_prefix} | request={request_body}")

    if response_body:
        try:
            response_json = _sanitize_log_payload(json.loads(response_body.decode("utf-8")))
            logger.info(f"{log_prefix} | response={response_json}")
        except Exception:
            logger.info(f"{log_prefix} | response=<non-json body len={len(response_body)}>")
    else:
        logger.info(f"{log_prefix} | response=<empty>")

    return Response(
        content=response_body,
        status_code=response.status_code,
        headers=dict(response.headers),
        media_type=response.media_type,
    )

# Initialiser IdProcessorV2
try:
    id_processor = IdProcessorV2(lang='fr')
    logger.info("✅ IdProcessorV2 initialisé avec succès")
except Exception as e:
    logger.error(f"❌ Erreur d'initialisation: {e}")
    raise RuntimeError(f"Échec de l'initialisation: {str(e)}")


# =========================
# MODELS
# =========================

class Base64ImageRequest(BaseModel):
    """Modèle pour requête avec image en base64"""
    model_config = ConfigDict(populate_by_name=True)

    image_base64: Optional[str] = Field(default=None, alias="imageBase64")  # Legacy (image unique)
    recto_base64: Optional[str] = Field(default=None, alias="rectoBase64")
    verso_base64: Optional[str] = Field(default=None, alias="versoBase64")
    code_document: Optional[str] = Field(default="01", alias="codeDocument")
    cod_typ_pid: Optional[str] = Field(default=None, alias="codTypPid")  # Alternative à code_document (pour Oracle)
    client_id: Optional[int] = Field(default=None, alias="clientId")  # ID client depuis base Oracle
    document_type: Optional[str] = Field(default=None, alias="documentType")  # Libellé du type de document
    ocr_lang: Optional[str] = Field(default="fr", alias="ocrLang")
    filename: Optional[str] = "document.jpg"

    @field_validator(
        "image_base64",
        "recto_base64",
        "verso_base64",
        "code_document",
        "cod_typ_pid",
        "document_type",
        "ocr_lang",
        "filename",
        mode="before"
    )
    @classmethod
    def normalize_optional_str(cls, value):
        if value is None:
            return None
        if isinstance(value, str):
            cleaned = value.strip()
            return cleaned or None
        return value

    @field_validator("client_id", mode="before")
    @classmethod
    def normalize_client_id(cls, value):
        if value is None:
            return None
        if isinstance(value, str):
            cleaned = value.strip()
            if cleaned == "":
                return None
        return value


class PathImageRequest(BaseModel):
    """Modèle pour extraction via chemin disque (DocIBANK/partage)."""
    model_config = ConfigDict(populate_by_name=True)

    document_path: str = Field(..., alias="documentPath")
    code_document: Optional[str] = Field(default="01", alias="codeDocument")
    cod_typ_pid: Optional[str] = Field(default=None, alias="codTypPid")
    auto_pair: bool = Field(default=True, alias="autoPair")
    client_id: Optional[int] = Field(default=None, alias="clientId")
    ocr_lang: Optional[str] = Field(default="fr", alias="ocrLang")

    @field_validator("document_path", mode="before")
    @classmethod
    def normalize_document_path(cls, value):
        if value is None:
            raise ValueError("document_path est requis")
        if isinstance(value, str):
            cleaned = value.strip().strip('"')
            if not cleaned:
                raise ValueError("document_path ne peut pas être vide")
            return cleaned
        return value

    @field_validator("code_document", "cod_typ_pid", "ocr_lang", mode="before")
    @classmethod
    def normalize_optional_str(cls, value):
        if value is None:
            return None
        if isinstance(value, str):
            cleaned = value.strip()
            return cleaned or None
        return value

    @field_validator("client_id", mode="before")
    @classmethod
    def normalize_client_id(cls, value):
        if value is None:
            return None
        if isinstance(value, str):
            cleaned = value.strip()
            if cleaned == "":
                return None
        return value


# =========================
# ENDPOINTS
# =========================

@app.get("/")
async def root():
    """Page d'accueil"""
    return {
        "service": "OCR Identity Extractor V2",
        "version": "2.0.0",
        "status": "running",
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "improvements": [
            "Strategy Pattern pour chaque type de document",
            "Preprocessing adaptatif (passeports, CIN Mali, CIN Sénégal)",
            "Détection MRZ pour passeports biométriques",
            "Validation pondérée par importance des champs",
            "Support NINA Mali (12 chiffres)",
            "Support CIN Sénégal (13 chiffres)",
            "Meilleure gestion des reflets et fonds colorés"
        ],
        "endpoints": {
            "GET /": "Cette page",
            "GET /health": "Santé du service",
            "GET /supported-types": "Types de documents supportés",
            "POST /extract-identity": "Extraction intelligente (multipart/form-data avec fichier image)",
            "POST /extract-identity-path": "Extraction intelligente (JSON avec chemin fichier local/réseau)",
            "POST /extract-identity-base64": "Extraction intelligente (JSON avec image_base64 encodée)",
            "POST /extract-identity-sync": "Extraction intelligente (multipart → normalisation → pipeline base64 = résultats identiques)",
            "POST /ocr-only-base64": "OCR texte uniquement (JSON base64)",
            "POST /ocr-only-sync": "OCR texte uniquement (multipart → base64 interne)",
            "POST /ocr-only": "OCR de base",
            "POST /extract-batch": "Traitement batch"
        }
    }


@app.get("/health")
async def health_check():
    """Vérification de santé"""
    try:
        supported_types = [dt for dt in DocumentType if dt != DocumentType.UNKNOWN]
        
        return {
            "status": "healthy",
            "service": "ocr-identity-extractor-v2",
            "timestamp": datetime.datetime.utcnow().isoformat(),
            "processor_initialized": True,
            "supported_types_count": len(supported_types),
            "details": {
                "ocr_engine": "PaddleOCR",
                "language": "fr",
                "version": "2.0.0",
                "architecture": "Strategy Pattern"
            }
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return JSONResponse(
            status_code=500,
            content={
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.datetime.utcnow().isoformat()
            }
        )


@app.get("/supported-types")
async def get_supported_types():
    """Liste des types de documents supportés"""
    try:
        # Ne pas dépendre d'un mapping legacy potentiel côté processor.
        supported = [dt.name for dt in DocumentType if dt != DocumentType.UNKNOWN]
        
        # Détails par type
        type_details = []
        for dt in DocumentType:
            if dt != DocumentType.UNKNOWN:
                type_details.append({
                    "code": dt.name,
                    "description": dt.value,
                    "features": _get_type_features(dt)
                })
        
        return {
            "success": True,
            "count": len(supported),
            "supported_types": supported,
            "details": type_details,
            "timestamp": datetime.datetime.utcnow().isoformat()
        }
    
    except Exception as e:
        logger.error(f"Erreur get_supported_types: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/extract-identity")
async def extract_identity(
    recto_file: Union[UploadFile, str, None] = File(default=None),
    verso_file: Union[UploadFile, str, None] = File(default=None),
    code_document: Optional[str] = Form(default="01"),
    ocr_lang: Optional[str] = Form(default="fr")
):
    """
    Extraction intelligente avec support recto-verso
    
    Args:
        recto_file: Image du recto (ou image unique en mode simple)
        verso_file: Image du verso (optionnel)
        code_document: Code optionnel du type de document
            - 01: CIN
            - 02: Passeport
            - 04: Carte séjour
            - 05: Permis de conduire
            - 21: CIN biométrique
            - 22: Passeport biométrique
    
    MODES:
    - Mode simple: Fournir seulement 'recto_file'
    - Mode recto-verso: Fournir 'recto_file' + 'verso_file'
    """
    start_time = time.time()
    
    try:
        # Normaliser recto_file: si envoyé vide via multipart, le traiter comme absent
        if isinstance(recto_file, str):
            if recto_file.strip() == '':
                recto_file = None
            else:
                raise HTTPException(
                    status_code=400,
                    detail="'recto_file' doit être un fichier image"
                )

        # Normaliser verso_file: si vide ou filename vide, le traiter comme None
        if isinstance(verso_file, str):
            if verso_file.strip() == '':
                verso_file = None
            else:
                raise HTTPException(
                    status_code=400,
                    detail="'verso_file' doit être un fichier image"
                )
        elif verso_file and (not verso_file.filename or verso_file.filename.strip() == ''):
            verso_file = None
        
        # Validation: au moins recto_file requise
        if not recto_file:
            raise HTTPException(
                status_code=400,
                detail="'recto_file' est requise"
            )
        
        code_document = _normalize_document_code(code_document)

        # Validation du code document: mettre "01" (CIN) par défaut si invalide ou absent
        from document_types import DOCUMENT_CODE_MAP
        if not code_document or code_document not in DOCUMENT_CODE_MAP:
            original_code = code_document
            code_document = "01"  # CIN par défaut
            if original_code:
                logger.warning(f"⚠️ Code document invalide '{original_code}', utilisation du code par défaut: 01 (CIN)")
            else:
                logger.info(f"📋 Aucun code document fourni, utilisation du code par défaut: 01 (CIN)")
        
        logger.info(f"📋 Code document utilisé: {code_document}")
        
        # Vérification type fichier
        allowed_types = ['image/jpeg', 'image/png', 'image/webp', 'image/bmp', 'image/tiff', 'image/jpg']
        
        # Préparer les images à traiter
        images_to_process = []
        original_total_size = 0
        filenames = []
        
        # Traiter recto_file
        if recto_file.content_type.lower() not in allowed_types:
            raise HTTPException(status_code=400, detail=f"Type fichier recto non supporté: {recto_file.content_type}")
        recto_bytes = await recto_file.read()
        if not recto_bytes:
            raise HTTPException(status_code=400, detail="Fichier recto vide")
        original_total_size += len(recto_bytes)
        images_to_process.append(recto_bytes)
        filenames.append(recto_file.filename or "recto.jpg")
        
        # Traiter verso_file optionnel
        if verso_file:
            if verso_file.content_type.lower() not in allowed_types:
                raise HTTPException(status_code=400, detail=f"Type fichier verso non supporté: {verso_file.content_type}")
            verso_bytes = await verso_file.read()
            if not verso_bytes:
                raise HTTPException(status_code=400, detail="Fichier verso vide")
            original_total_size += len(verso_bytes)
            images_to_process.append(verso_bytes)
            filenames.append(verso_file.filename or "verso.jpg")
            logger.info(f"🔍 Extraction - Mode recto-verso: {filenames[0]} + {filenames[1]}")
        else:
            logger.info(f"🔍 Extraction - Mode simple: {filenames[0]}")
        
        # Traitement avec support recto-verso
        result, ocr_lang_selected, ocr_lang_tried = _process_multiple_with_optional_auto(
            images_to_process,
            code_document,
            ocr_lang,
        )
        
        if not result.get("success", False):
            raise HTTPException(
                status_code=500,
                detail=result.get("error", "Erreur de traitement")
            )
        
        # Formater les données extraites avec schéma stable
        extracted_data = result.get("extracted_data", {})
        formatted_extracted = _format_extracted_data(
            extracted_data,
            code_document,
            result.get("document_type", "Document inconnu")
        )
        
        # Validation
        validation = result.get("validation", {})
        
        # Construire la réponse
        response = {
            "success": True,
            "filename": filenames[0] if len(filenames) == 1 else ", ".join(filenames),
            "file_size_bytes": sum(len(image) for image in images_to_process),
            "input_file_size_bytes": original_total_size,
            "content_type": recto_file.content_type,
            "processing_time": round(time.time() - start_time, 2),
            "document": {
                "type": result.get("document_type", "UNKNOWN"),
                "description": result.get("document_type_value", "Document inconnu"),
                "detection_confidence": result.get("document_type_confidence", 0)
            },
            "extracted_data": formatted_extracted,
            "validation": validation,
            "metadata": {
                **result.get("metadata", {}),
                "ocr_lang_requested": _normalize_ocr_lang(ocr_lang) or "fr",
                "ocr_lang_selected": ocr_lang_selected,
                "ocr_lang_tried": ocr_lang_tried,
            },
            "message": _generate_message(validation, result.get("document_type_value", ""))
        }
        
        logger.info(
            f"✅ Extraction OK - Type: {result.get('document_type')} - "
            f"Score: {validation.get('global_score', 0):.2f}"
        )

        _debug_print_response("extract-identity", response)
        
        return response
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur extraction: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erreur: {str(e)}")


@app.post("/extract-identity-base64")
async def extract_identity_base64(request: Base64ImageRequest):
    """
    Extraction intelligente à partir d'image(s) encodée(s) en base64
    
    Body JSON:
    {
        "image_base64": "base64_encoded_image_string",  // legacy (mode simple)
        "recto_base64": "base64_recto",  // recommandé
        "verso_base64": "base64_verso",  // optionnel
        "code_document": "02",  // optionnel
        "cod_typ_pid": "02",  // alternative à code_document (pour Oracle)
        "client_id": 12345,  // optionnel
        "document_type": "Passport",  // optionnel (libellé)
        "filename": "document.jpg"  // optionnel
    }
    """
    start_time = time.time()
    
    try:
        # Utiliser cod_typ_pid si code_document n'est pas fourni (compatibilité Oracle)
        code_document = _normalize_document_code(request.code_document or request.cod_typ_pid)
        
        logger.info(f"🔍 Extraction base64 - Image base64 JSON: {request.filename}")
        
        # Sélection des entrées base64 (compatibilité: image_base64 == recto_base64)
        recto_b64 = request.recto_base64 or request.image_base64
        verso_b64 = request.verso_base64

        if not recto_b64:
            raise HTTPException(
                status_code=400,
                detail="Fournir 'recto_base64' (ou 'image_base64' en mode legacy)"
            )

        raw_recto = _decode_b64_payload(recto_b64, "recto")
        images_to_process = [raw_recto]
        original_total_size = len(raw_recto)

        if verso_b64:
            raw_verso = _decode_b64_payload(verso_b64, "verso")
            original_total_size += len(raw_verso)
            images_to_process.append(raw_verso)
        
        # Validation du code document: mettre "01" (CIN) par défaut si invalide ou absent
        from document_types import DOCUMENT_CODE_MAP
        if not code_document or code_document not in DOCUMENT_CODE_MAP:
            original_code = code_document
            code_document = "01"  # CIN par défaut
            if original_code:
                logger.warning(f"⚠️ Code document invalide '{original_code}', utilisation du code par défaut: 01 (CIN)")
            else:
                logger.info(f"📋 Aucun code document fourni, utilisation du code par défaut: 01 (CIN)")
        
        # Log du code document et client_id si fournis
        if request.client_id:
            logger.info(f"👤 Client ID: {request.client_id}")
        logger.info(f"📋 Code document utilisé: {code_document}")
        if request.document_type:
            logger.info(f"📄 Type document (libellé): {request.document_type}")
        
        # Traitement (simple ou recto-verso)
        result, ocr_lang_selected, ocr_lang_tried = _process_multiple_with_optional_auto(
            images_to_process,
            code_document,
            request.ocr_lang,
        )
        
        if not result.get("success", False):
            raise HTTPException(
                status_code=500,
                detail=result.get("error", "Erreur de traitement")
            )
        
        # Formater les données extraites avec schéma stable
        extracted_data = result.get("extracted_data", {})
        formatted_extracted = _format_extracted_data(
            extracted_data,
            code_document,
            result.get("document_type", "Document inconnu")
        )
        
        # Validation
        validation = result.get("validation", {})
        
        # Construire la réponse
        response = {
            "success": True,
            "filename": request.filename,
            "file_size_bytes": sum(len(img) for img in images_to_process),
            "input_file_size_bytes": original_total_size,
            "processing_time": round(time.time() - start_time, 2),
            "document": {
                "type": result.get("document_type", "UNKNOWN"),
                "description": result.get("document_type_value", "Document inconnu"),
                "detection_confidence": result.get("document_type_confidence", 0),
                "code_provided": code_document  # Code document fourni (si existe)
            },
            "mode": "recto-verso" if len(images_to_process) > 1 else "simple",
            "images_processed": len(images_to_process),
            "extracted_data": formatted_extracted,
            "validation": validation,
            "metadata": {
                **result.get("metadata", {}),
                "ocr_lang_requested": _normalize_ocr_lang(request.ocr_lang) or "fr",
                "ocr_lang_selected": ocr_lang_selected,
                "ocr_lang_tried": ocr_lang_tried,
            },
            "message": _generate_message(validation, result.get("document_type_value", ""))
        }
        
        # Ajouter client_id si fourni (pour traçabilité Oracle)
        if request.client_id:
            response["client_id"] = request.client_id
        
        logger.info(
            f"✅ Extraction base64 OK - Type: {result.get('document_type')} - "
            f"Score: {validation.get('global_score', 0):.2f}"
        )

        _debug_print_response("extract-identity-base64", response)
        
        return response
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur extraction base64: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erreur: {str(e)}")


@app.post("/extract-identity-path")
async def extract_identity_path(request: PathImageRequest):
    """
    Extraction intelligente à partir d'un chemin fichier.

    Exemple de chemin DocIBANK:
    \DocIBANK\PER\PER-1045\DOC\IMG\PER11000D0000001045P1.jpg

    Convention de nommage supportée:
    - PER<cod_typ_pid>D<id_personne>P<sequence>.jpg
    - sequence 1 => recto, sequence 2 => verso
    """
    start_time = time.time()

    try:
        resolved_path = _resolve_input_document_path(request.document_path)
        parsed_meta = _parse_docibank_filename(resolved_path)

        raw_main = _read_binary_file(resolved_path)

        if not raw_main:
            raise HTTPException(status_code=400, detail="Fichier principal vide")

        images_to_process = []
        filenames = []
        original_total_size = 0

        sequence = parsed_meta.get("sequence")
        paired_path = _find_paired_path(resolved_path, sequence) if request.auto_pair else None

        # Si l'entrée est un verso (P2) et le recto (P1) existe, on traite P1 puis P2.
        if paired_path and sequence == 2:
            raw_recto = _read_binary_file(paired_path)
            if raw_recto:
                images_to_process.append(raw_recto)
                filenames.append(_display_filename(paired_path))
                original_total_size += len(raw_recto)

        main_label = "verso" if sequence == 2 else "recto"
        images_to_process.append(raw_main)
        filenames.append(_display_filename(resolved_path))
        original_total_size += len(raw_main)

        # Si l'entrée est un recto (P1), ajouter le verso (P2) quand disponible.
        if paired_path and sequence == 1:
            raw_verso = _read_binary_file(paired_path)
            if raw_verso:
                images_to_process.append(raw_verso)
                filenames.append(_display_filename(paired_path))
                original_total_size += len(raw_verso)

        # Priorité: code explicite > cod_typ_pid explicite > cod_typ_pid parsé du nom de fichier.
        code_document = _normalize_document_code(request.code_document)
        if not code_document:
            code_document = _map_cod_typ_pid_to_code_document(request.cod_typ_pid)
        if not code_document:
            code_document = _map_cod_typ_pid_to_code_document(parsed_meta.get("cod_typ_pid"))

        if not code_document or code_document not in DOCUMENT_CODE_MAP:
            code_document = "01"

        result, ocr_lang_selected, ocr_lang_tried = _process_multiple_with_optional_auto(
            images_to_process,
            code_document,
            request.ocr_lang,
        )

        if not result.get("success", False):
            raise HTTPException(
                status_code=500,
                detail=result.get("error", "Erreur de traitement")
            )

        extracted_data = result.get("extracted_data", {})
        formatted_extracted = _format_extracted_data(
            extracted_data,
            code_document,
            result.get("document_type", "Document inconnu")
        )

        validation = result.get("validation", {})

        response = {
            "success": True,
            "filename": filenames[0] if len(filenames) == 1 else ", ".join(filenames),
            "source_path": request.document_path,
            "resolved_path": resolved_path,
            "paired_path": paired_path,
            "file_size_bytes": sum(len(img) for img in images_to_process),
            "input_file_size_bytes": original_total_size,
            "processing_time": round(time.time() - start_time, 2),
            "document": {
                "type": result.get("document_type", "UNKNOWN"),
                "description": result.get("document_type_value", "Document inconnu"),
                "detection_confidence": result.get("document_type_confidence", 0),
                "code_provided": code_document
            },
            "mode": "recto-verso" if len(images_to_process) > 1 else "simple",
            "images_processed": len(images_to_process),
            "extracted_data": formatted_extracted,
            "validation": validation,
            "metadata": {
                **result.get("metadata", {}),
                "path_input": request.document_path,
                "resolved_path": resolved_path,
                "docibank": parsed_meta,
                "auto_pair": request.auto_pair,
                "ocr_lang_requested": _normalize_ocr_lang(request.ocr_lang) or "fr",
                "ocr_lang_selected": ocr_lang_selected,
                "ocr_lang_tried": ocr_lang_tried,
            },
            "message": _generate_message(validation, result.get("document_type_value", ""))
        }

        if request.client_id:
            response["client_id"] = request.client_id

        _debug_print_response("extract-identity-path", response)
        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur extract-identity-path: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erreur: {str(e)}")


@app.post("/extract-identity-sync")
async def extract_identity_sync(
    recto_file: UploadFile = File(...),
    verso_file: Union[UploadFile, str, None] = File(default=None),
    code_document: Optional[str] = Form(default="01"),
    ocr_lang: Optional[str] = Form(default="fr")
):
    """
    Endpoint de synchronisation: reçoit upload multipart,
    convertit en base64 puis appelle le endpoint base64 en interne.
    Cela force exactement le même chemin de traitement que /extract-identity-base64.
    """
    start_time = time.time()

    try:
        if not recto_file:
            raise HTTPException(status_code=400, detail="'recto_file' est requise")

        allowed_types = ['image/jpeg', 'image/png', 'image/webp', 'image/bmp', 'image/tiff', 'image/jpg']
        
        # Normaliser verso_file: si vide ou str "", le traiter comme None
        if isinstance(verso_file, str):
            if verso_file.strip() == '':
                verso_file = None
        elif verso_file and (not verso_file.filename or verso_file.filename.strip() == ''):
            verso_file = None
        
        if recto_file.content_type.lower() not in allowed_types:
            raise HTTPException(status_code=400, detail=f"Type fichier recto non supporté: {recto_file.content_type}")
        
        recto_bytes = await recto_file.read()
        if not recto_bytes:
            raise HTTPException(status_code=400, detail="Fichier recto vide")

        verso_bytes = None
        if verso_file:
            if verso_file.content_type.lower() not in allowed_types:
                raise HTTPException(status_code=400, detail=f"Type fichier verso non supporté: {verso_file.content_type}")
            verso_bytes = await verso_file.read()
            if not verso_bytes:
                raise HTTPException(status_code=400, detail="Fichier verso vide")

        # Encodage base64 réel depuis les bytes source pour forcer le chemin base64.
        recto_b64 = base64.b64encode(recto_bytes).decode("ascii")
        verso_b64 = base64.b64encode(verso_bytes).decode("ascii") if verso_bytes else None

        sync_request = Base64ImageRequest(
            recto_base64=recto_b64,
            verso_base64=verso_b64,
            code_document=code_document,
            ocr_lang=ocr_lang,
            filename=recto_file.filename or "document.jpg"
        )

        response = await extract_identity_base64(sync_request)
        if isinstance(response, dict):
            response["content_type"] = recto_file.content_type
            response["_pipeline"] = "sync_via_base64"
            response["sync_processing_time"] = round(time.time() - start_time, 2)

        if isinstance(response, dict):
            _debug_print_response("extract-identity-sync", response)

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur extraction sync: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erreur: {str(e)}")


@app.post("/ocr-only")
async def ocr_only(file: UploadFile = File(...)):
    """OCR de base sans extraction"""
    start_time = time.time()
    
    try:
        allowed_types = ['image/jpeg', 'image/png', 'image/webp', 'image/bmp', 'image/tiff', 'image/jpg']
        content_type = file.content_type.lower()
        
        if content_type not in allowed_types:
            raise HTTPException(
                status_code=400,
                detail=f"Type non supporté: {content_type}"
            )
        
        logger.info(f"📄 OCR only - Fichier: {file.filename}")
        
        image_bytes = await file.read()
        
        if not image_bytes:
            raise HTTPException(status_code=400, detail="Fichier vide")
        
        result = id_processor.process_ocr_only(image_bytes)
        
        if not result.get("success", False):
            raise HTTPException(status_code=500, detail=result.get("error", "Erreur OCR"))
        
        result["filename"] = file.filename
        result["file_size_bytes"] = len(image_bytes)
        result["content_type"] = content_type
        result["total_processing_time"] = round(time.time() - start_time, 2)
        
        logger.info(f"✅ OCR terminé - {result.get('total_blocks', 0)} blocs")

        _debug_print_response("ocr-only", result)
        
        return result
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur OCR: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/ocr-only-base64")
async def ocr_only_base64(request: Base64ImageRequest):
    """OCR texte uniquement à partir d'une image base64 (recto/image unique)."""
    start_time = time.time()

    try:
        recto_b64 = request.recto_base64 or request.image_base64
        if not recto_b64:
            raise HTTPException(
                status_code=400,
                detail="Fournir 'recto_base64' (ou 'image_base64' en mode legacy)"
            )

        raw_recto = _decode_b64_payload(recto_b64, "recto")
        normalized = _normalize_image_bytes(raw_recto, "recto")

        result = id_processor.process_ocr_only(normalized, request.ocr_lang)
        if not result.get("success", False):
            raise HTTPException(status_code=500, detail=result.get("error", "Erreur OCR"))

        result["filename"] = request.filename or "document.jpg"
        result["file_size_bytes"] = len(normalized)
        result["input_file_size_bytes"] = len(raw_recto)
        result["processing_time"] = round(time.time() - start_time, 2)
        result["_pipeline"] = "ocr_only_base64"

        _debug_print_response("ocr-only-base64", result)

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur OCR base64: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erreur: {str(e)}")


@app.post("/ocr-only-sync")
async def ocr_only_sync(file: UploadFile = File(...)):
    """OCR texte uniquement: upload multipart, conversion base64 interne, puis pipeline base64."""
    start_time = time.time()

    try:
        if not file:
            raise HTTPException(status_code=400, detail="'file' est requise")

        allowed_types = ['image/jpeg', 'image/png', 'image/webp', 'image/bmp', 'image/tiff', 'image/jpg']
        content_type = file.content_type.lower()
        if content_type not in allowed_types:
            raise HTTPException(status_code=400, detail=f"Type non supporté: {content_type}")

        image_bytes = await file.read()
        if not image_bytes:
            raise HTTPException(status_code=400, detail="Fichier vide")

        image_b64 = base64.b64encode(image_bytes).decode("ascii")
        sync_request = Base64ImageRequest(
            recto_base64=image_b64,
            filename=file.filename or "document.jpg"
        )

        response = await ocr_only_base64(sync_request)
        if isinstance(response, dict):
            response["content_type"] = content_type
            response["sync_processing_time"] = round(time.time() - start_time, 2)
            response["_pipeline"] = "ocr_only_sync_via_base64"

        if isinstance(response, dict):
            _debug_print_response("ocr-only-sync", response)

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur OCR sync: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erreur: {str(e)}")


@app.post("/ocr-only-pair")
async def ocr_only_pair(
    recto_file: Union[UploadFile, str, None] = File(default=None),
    verso_file: Union[UploadFile, str, None] = File(default=None),
    ocr_lang: Optional[str] = Form(default="fr")
):
    """OCR texte uniquement pour recto + verso optionnel (retourne juste les dates OCR détectées)"""
    start_time = time.time()
    
    try:
        # Normaliser recto_file
        if isinstance(recto_file, str):
            if recto_file.strip() == '':
                recto_file = None
            else:
                raise HTTPException(status_code=400, detail="'recto_file' doit être un fichier image")
        
        # Normaliser verso_file
        if isinstance(verso_file, str):
            if verso_file.strip() == '':
                verso_file = None
            else:
                raise HTTPException(status_code=400, detail="'verso_file' doit être un fichier image")
        elif verso_file and (not verso_file.filename or verso_file.filename.strip() == ''):
            verso_file = None
        
        # Validation: au moins recto_file requise
        if not recto_file:
            raise HTTPException(status_code=400, detail="'recto_file' est requise")
        
        allowed_types = ['image/jpeg', 'image/png', 'image/webp', 'image/bmp', 'image/tiff', 'image/jpg']
        
        # Préparer les images
        images_to_process = []
        filenames_list = []
        
        # Recto
        if recto_file.content_type.lower() not in allowed_types:
            raise HTTPException(status_code=400, detail=f"Type fichier recto non supporté: {recto_file.content_type}")
        recto_bytes = await recto_file.read()
        if not recto_bytes:
            raise HTTPException(status_code=400, detail="Fichier recto vide")
        images_to_process.append(recto_bytes)
        filenames_list.append(recto_file.filename or "recto.jpg")
        
        # Verso (optionnel)
        verso_bytes = None
        if verso_file:
            if verso_file.content_type.lower() not in allowed_types:
                raise HTTPException(status_code=400, detail=f"Type fichier verso non supporté: {verso_file.content_type}")
            verso_bytes = await verso_file.read()
            if verso_bytes:
                images_to_process.append(verso_bytes)
                filenames_list.append(verso_file.filename or "verso.jpg")
        
        logger.info(f"🔍 OCR pair - Images: {filenames_list}")
        
        # Process recto
        recto_result = id_processor.process_ocr_only(recto_bytes, ocr_lang)
        if not recto_result.get("success", False):
            raise HTTPException(status_code=500, detail=recto_result.get("error", "Erreur OCR recto"))
        
        # Process verso si existe
        verso_result = None
        if verso_bytes:
            verso_result = id_processor.process_ocr_only(verso_bytes, ocr_lang)
            if not verso_result.get("success", False):
                logger.warning(f"⚠️ Erreur OCR verso: {verso_result.get('error', 'Unknown error')}")
        
        # Extraire juste les dates détectées
        recto_dates = recto_result.get("dates", [])
        verso_dates = verso_result.get("dates", []) if verso_result else []
        all_dates = recto_dates + verso_dates
        
        result = {
            "success": True,
            "total_processing_time": round(time.time() - start_time, 2),
            "filenames": filenames_list,
            "recto": {
                "filename": filenames_list[0],
                "dates_found": recto_dates,
                "text_blocks": recto_result.get("text_blocks", []),
                "total_blocks": recto_result.get("total_blocks", 0)
            },
            "verso": {
                "filename": filenames_list[1] if len(filenames_list) > 1 else None,
                "dates_found": verso_dates,
                "text_blocks": verso_result.get("text_blocks", []) if verso_result else [],
                "total_blocks": verso_result.get("total_blocks", 0) if verso_result else 0
            } if verso_result else None,
            "all_dates_found": all_dates,
            "total_blocks": recto_result.get("total_blocks", 0) + (verso_result.get("total_blocks", 0) if verso_result else 0)
        }
        
        logger.info(f"✅ OCR pair terminé - Dates trouvées: {all_dates}")
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur OCR pair: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erreur: {str(e)}")


@app.post("/extract-batch")
async def extract_batch(files: List[UploadFile] = File(...)):
    """Traitement batch"""
    batch_start = time.time()
    results = []
    
    for file in files:
        file_start = time.time()
        
        try:
            allowed_types = ['image/jpeg', 'image/png', 'image/webp', 'image/bmp', 'image/tiff', 'image/jpg']
            content_type = file.content_type.lower()
            
            if content_type not in allowed_types:
                results.append({
                    "filename": file.filename,
                    "success": False,
                    "error": f"Type non supporté: {content_type}",
                    "processing_time": 0
                })
                continue
            
            image_bytes = await file.read()
            
            if not image_bytes:
                results.append({
                    "filename": file.filename,
                    "success": False,
                    "error": "Fichier vide",
                    "processing_time": 0
                })
                continue
            
            # Traitement
            proc_result = id_processor.process(image_bytes)
            
            result_item = {
                "filename": file.filename,
                "success": proc_result.get("success", False),
                "document_type": proc_result.get("document_type", "UNKNOWN"),
                "extracted_fields_count": len(proc_result.get("extracted_data", {})),
                "validation_score": proc_result.get("validation", {}).get("global_score", 0),
                "processing_time": round(time.time() - file_start, 2)
            }
            
            if not proc_result.get("success", True):
                result_item["error"] = proc_result.get("error", "Erreur inconnue")
            
            results.append(result_item)
        
        except Exception as e:
            logger.error(f"Erreur batch pour {file.filename}: {e}")
            results.append({
                "filename": file.filename,
                "success": False,
                "error": str(e),
                "processing_time": round(time.time() - file_start, 2)
            })
    
    # Statistiques
    successful = sum(1 for r in results if r.get("success", False))
    
    return {
        "batch_results": results,
        "summary": {
            "total_files": len(files),
            "successful": successful,
            "failed": len(files) - successful,
            "success_rate": round(successful / len(files) * 100, 2) if files else 0,
            "total_processing_time": round(time.time() - batch_start, 2)
        },
        "timestamp": datetime.datetime.utcnow().isoformat()
    }


# =========================
# FONCTIONS UTILITAIRES
# =========================

def _get_type_features(doc_type: DocumentType) -> List[str]:
    """Retourne les features par type"""
    return get_document_features(doc_type)


def _generate_message(validation: dict, doc_description: str) -> str:
    """Génère un message approprié"""
    is_valid = bool(validation.get("is_valid", validation.get("est_valide", False)))
    if is_valid:
        return f"Document {doc_description} traité avec succès"
    else:
        missing = validation.get("fields_missing_required", validation.get("champs_requis_manquants", []))
        if missing:
            return f"Document traité partiellement - Champs manquants: {', '.join(missing)}"
        else:
            return "Document traité avec une confiance limitée"


def _normalize_document_code(code_value: Optional[Union[str, int]]) -> Optional[str]:
    """Normalise les codes document (ex: 2 -> '02', ' 02 ' -> '02')."""
    if code_value is None:
        return None

    normalized = str(code_value).strip()
    if not normalized:
        return None

    if normalized.isdigit() and len(normalized) == 1:
        normalized = normalized.zfill(2)

    return normalized


def _normalize_ocr_lang(lang_value: Optional[str]) -> Optional[str]:
    """Normalise la langue OCR (ex: ' FR ' -> 'fr')."""
    if lang_value is None:
        return None
    if not isinstance(lang_value, str):
        return None
    normalized = lang_value.strip().lower()
    return normalized or None


def _result_quality_score(result: dict) -> float:
    """Score qualité agrégé pour comparer deux sorties OCR."""
    if not isinstance(result, dict) or not result.get("success", False):
        return -1.0

    validation = result.get("validation", {}) or {}
    score = validation.get("global_score", validation.get("score", 0)) or 0

    extracted = result.get("extracted_data", {}) or {}
    non_empty = 0
    for value in extracted.values():
        if isinstance(value, dict):
            if str(value.get("value", "")).strip():
                non_empty += 1
        elif str(value).strip():
            non_empty += 1

    # Priorise la validation, puis le nombre de champs utiles.
    return float(score) + min(non_empty / 20.0, 0.3)


def _process_multiple_with_optional_auto(
    images_to_process: List[bytes],
    code_document: Optional[str],
    ocr_lang: Optional[str],
) -> Tuple[dict, str, List[str]]:
    """Exécute l'extraction en mode langue fixe ou auto (fr -> ar)."""
    normalized_lang = _normalize_ocr_lang(ocr_lang)
    if normalized_lang not in (None, "", "auto"):
        result = id_processor.process_multiple(images_to_process, code_document, normalized_lang)
        return result, normalized_lang, [normalized_lang]

    primary_lang = "fr"
    secondary_lang = "ar"

    primary_result = id_processor.process_multiple(images_to_process, code_document, primary_lang)
    primary_score = _result_quality_score(primary_result)

    # Si le résultat FR est déjà solide, éviter le coût de l'arabe.
    if primary_score >= 0.85:
        return primary_result, primary_lang, [primary_lang]

    secondary_result = id_processor.process_multiple(images_to_process, code_document, secondary_lang)
    secondary_score = _result_quality_score(secondary_result)

    if secondary_score > primary_score:
        return secondary_result, secondary_lang, [primary_lang, secondary_lang]

    return primary_result, primary_lang, [primary_lang, secondary_lang]


def _map_cod_typ_pid_to_code_document(cod_typ_pid: Optional[Union[str, int]]) -> Optional[str]:
    """Mappe un cod_typ_pid métier (ex: 11000) vers un code_document API (ex: 01)."""
    normalized = _normalize_document_code(cod_typ_pid)
    if not normalized:
        return None

    if normalized in DOCUMENT_CODE_MAP:
        return normalized

    raw = str(cod_typ_pid).strip()
    explicit_map = {
        "11000": "01",  # CIN
        "12000": "02",  # Passeport
        "14000": "04",  # Carte séjour
        "15000": "05",  # Permis
        "21000": "21",  # CIN biométrique
        "22000": "22",  # Passeport biométrique
    }
    if raw in explicit_map:
        return explicit_map[raw]

    # Heuristique: 11000 -> 01, 12000 -> 02, etc.
    if raw.isdigit() and len(raw) == 5 and raw.endswith("000"):
        candidate_num = int(raw[:2]) - 10
        if 1 <= candidate_num <= 99:
            candidate = f"{candidate_num:02d}"
            if candidate in DOCUMENT_CODE_MAP:
                return candidate

    return None


def _resolve_input_document_path(path_value: str) -> str:
    """Résout un chemin entrant en testant chemin brut, absolu et racines configurées."""
    raw = (path_value or "").strip().strip('"')
    if not raw:
        raise HTTPException(status_code=400, detail="document_path vide")

    is_unc_input = _is_unc_path(raw)
    normalized = raw.replace("/", "\\") if is_unc_input else raw.replace("/", os.sep).replace("\\", os.sep)
    candidates = []

    # Candidat direct tel quel
    candidates.append(normalized)

    # Candidat absolu depuis le cwd
    if not is_unc_input:
        candidates.append(os.path.abspath(normalized))

    # Cas conteneur Linux: mapper un UNC (\\serveur\partage\...) vers une racine montée.
    # Exemple: DOC_PATH_ROOT=/mnt/docibank + \\x\c$\DocIBANK\... -> /mnt/docibank/...
    if is_unc_input:
        unc_parts = [part for part in re.split(r"[\\/]+", raw) if part]
        if len(unc_parts) >= 2:
            unc_relative_parts = unc_parts[2:]

            mapped_roots = []
            for env_var in ["UNC_PATH_ROOT", "DOC_PATH_ROOT", "DOCUMENT_PATH_ROOT", "DOCIBANK_ROOT"]:
                root = os.getenv(env_var)
                if root:
                    mapped_roots.append(root)

            for root in mapped_roots:
                root_abs = os.path.abspath(root)
                if unc_relative_parts:
                    candidates.append(os.path.join(root_abs, *unc_relative_parts))
                    first_segment = unc_relative_parts[0].upper()
                    root_name = os.path.basename(root_abs).upper()
                    if first_segment == root_name and len(unc_relative_parts) > 1:
                        candidates.append(os.path.join(root_abs, *unc_relative_parts[1:]))
                else:
                    candidates.append(root_abs)

    # Candidats via racines configurables (utile pour les chemins \DocIBANK\...)
    trimmed = normalized.lstrip("\\/")
    configured_roots = []
    for env_var in ["DOC_PATH_ROOT", "DOCUMENT_PATH_ROOT", "DOCIBANK_ROOT"]:
        root = os.getenv(env_var)
        if root:
            configured_roots.append(root)

    for root in configured_roots:
        root_abs = os.path.abspath(root)
        root_name = os.path.basename(root_abs).upper()
        trimmed_for_root = trimmed

        # Si le chemin fourni commence déjà par DocIBANK, éviter root\DocIBANK\...
        if trimmed_for_root.upper().startswith(root_name + os.sep):
            trimmed_for_root = trimmed_for_root[len(root_name) + 1:]
        elif trimmed_for_root.upper() == root_name:
            trimmed_for_root = ""

        candidates.append(os.path.join(root_abs, trimmed_for_root))

    for candidate in candidates:
        if candidate and _path_exists(candidate):
            return _normalize_resolved_path(candidate)

    deployment_hint = (
        "Chemin UNC détecté. En conteneur Linux, montez le partage SMB sur l'hôte puis exposez le montage au conteneur "
        "(ex: DOC_PATH_ROOT=/mnt/docibank)."
        if is_unc_input else None
    )

    raise HTTPException(
        status_code=404,
        detail={
            "message": "Fichier introuvable",
            "document_path": path_value,
            "checked_paths": candidates,
            "hint": deployment_hint,
        }
    )


def _is_unc_path(path_value: Optional[str]) -> bool:
    if not path_value:
        return False
    return str(path_value).startswith("\\\\") or str(path_value).startswith("//")


def _normalize_resolved_path(path_value: str) -> str:
    if _is_unc_path(path_value):
        return path_value.replace("/", "\\")
    return os.path.abspath(path_value)


def _network_path_parts(path_value: str) -> Optional[tuple]:
    if not _is_unc_path(path_value):
        return None
    cleaned = path_value.replace("/", "\\").lstrip("\\")
    parts = [p for p in cleaned.split("\\") if p]
    if len(parts) < 2:
        return None
    return parts[0], parts[1]


def _init_smb_session_for_path(path_value: str):
    if not _is_unc_path(path_value):
        return
    if smbclient is None:
        raise HTTPException(
            status_code=500,
            detail="Accès UNC demandé mais dépendance SMB indisponible (installer smbprotocol)."
        )

    parts = _network_path_parts(path_value)
    if not parts:
        return

    server, _share = parts
    username = os.getenv("SMB_USERNAME")
    password = os.getenv("SMB_PASSWORD")
    domain = os.getenv("SMB_DOMAIN")

    if username and password:
        try:
            smbclient.register_session(server, username=username, password=password, domain=domain)
        except TypeError:
            smbclient.register_session(server, username=username, password=password)
    else:
        # Tentative en session anonyme / credentials système si disponibles.
        smbclient.register_session(server)


def _path_exists(path_value: str) -> bool:
    if _is_unc_path(path_value):
        try:
            _init_smb_session_for_path(path_value)
            return bool(smbclient.path.exists(path_value))
        except Exception:
            return False
    return os.path.isfile(path_value)


def _read_binary_file(path_value: str) -> bytes:
    if _is_unc_path(path_value):
        try:
            _init_smb_session_for_path(path_value)
            with smbclient.open_file(path_value, mode="rb") as f:
                return f.read()
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Impossible de lire le chemin réseau: {str(e)}")

    with open(path_value, "rb") as f:
        return f.read()


def _display_filename(path_value: str) -> str:
    return ntpath.basename(path_value) if _is_unc_path(path_value) else os.path.basename(path_value)


def _parse_docibank_filename(file_path: str) -> dict:
    """Parse le pattern PER<cod_typ_pid>D<id_personne>P<sequence> dans le nom de fichier."""
    filename = ntpath.basename(file_path) if _is_unc_path(file_path) else os.path.basename(file_path)
    stem, ext = os.path.splitext(filename)
    normalized_stem = stem.upper()

    metadata = {
        "filename": filename,
        "extension": ext.lower(),
    }

    match = re.match(r"^PER(?P<cod>\d{5})D0*(?P<person>\d+)P(?P<seq>\d+)$", normalized_stem)
    if not match:
        return metadata

    cod_typ_pid = match.group("cod")
    person_id = match.group("person")
    sequence = int(match.group("seq"))

    metadata.update({
        "cod_typ_pid": cod_typ_pid,
        "person_id": person_id,
        "sequence": sequence,
        "side": "recto" if sequence == 1 else ("verso" if sequence == 2 else "unknown"),
        "code_document_inferred": _map_cod_typ_pid_to_code_document(cod_typ_pid)
    })

    return metadata


def _find_paired_path(file_path: str, sequence: Optional[int]) -> Optional[str]:
    """Trouve le pair P1/P2 à partir du nom de fichier si présent et accessible."""
    if sequence not in (1, 2):
        return None

    if _is_unc_path(file_path):
        base, ext = ntpath.splitext(file_path)
    else:
        base, ext = os.path.splitext(file_path)
    target = 2 if sequence == 1 else 1
    paired_base = re.sub(r"P\d+$", f"P{target}", base, flags=re.IGNORECASE)
    if paired_base == base:
        return None

    paired_path = paired_base + ext
    if _path_exists(paired_path):
        return _normalize_resolved_path(paired_path)

    return None


def _resolve_document_type(code_document: Optional[str], detected_doc_type_label: str) -> DocumentType:
    """Détermine le DocumentType à partir du code fourni ou du type détecté."""
    if code_document and code_document in DOCUMENT_CODE_MAP:
        return DOCUMENT_CODE_MAP[code_document]

    for doc_type in DocumentType:
        if doc_type.value == detected_doc_type_label:
            return doc_type

    return DocumentType.UNKNOWN


def _format_extracted_data(
    extracted_data: dict,
    code_document: Optional[str],
    detected_doc_type_label: str
) -> dict:
    """Formate et complète extracted_data pour avoir un schéma stable entre endpoints."""
    resolved_doc_type = _resolve_document_type(code_document, detected_doc_type_label)
    expected_fields = DOCUMENT_FIELDS.get(resolved_doc_type, [])

    # Garder d'abord les champs attendus, puis ajouter les champs supplémentaires détectés.
    ordered_fields = list(expected_fields)
    for field_name in extracted_data.keys():
        if field_name not in ordered_fields:
            ordered_fields.append(field_name)

    formatted = {}

    def _prune_location(location: dict) -> dict:
        """Conserve uniquement l'indicateur booléen attendu/non-attendu."""
        if not isinstance(location, dict):
            return {}

        return {"in_expected_zone": bool(location.get("in_expected_zone", False))}

    for field in ordered_fields:
        data = extracted_data.get(field)
        if isinstance(data, dict):
            formatted[field] = {
                "value": data.get("value", ""),
                "confidence": data.get("confidence", 0),
                "method": data.get("method", "unknown")
            }
            if "location" in data:
                formatted[field]["location"] = _prune_location(data.get("location"))
        elif data is not None:
            formatted[field] = {
                "value": data,
                "confidence": 0,
                "method": "legacy"
            }
        else:
            formatted[field] = {
                "value": "",
                "confidence": 0,
                "method": "missing"
            }

    return formatted


def _normalize_image_bytes(image_bytes: bytes, label: str) -> bytes:
    """Normalise les images vers un format JPEG stable pour homogénéiser l'OCR."""
    try:
        img = Image.open(BytesIO(image_bytes))
        img.load()

        # Uniformiser le mode couleur pour stabiliser le preprocessing OCR.
        if img.mode != "RGB":
            img = img.convert("RGB")

        out = BytesIO()
        img.save(out, format="JPEG", quality=90, optimize=True)
        normalized = out.getvalue()

        if not normalized:
            raise HTTPException(status_code=400, detail=f"Image {label} invalide après normalisation")

        return normalized
    except UnidentifiedImageError:
        raise HTTPException(status_code=400, detail=f"Image {label} non reconnue")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erreur traitement image {label}: {str(e)}")


def _decode_b64_payload(base64_value: str, label: str) -> bytes:
    """Décode strictement une payload base64 en bytes image bruts."""
    try:
        base64_str = base64_value
        if ',' in base64_str:
            base64_str = base64_str.split(',', 1)[1]

        # Supprime espaces/sauts de ligne éventuels dans la payload base64.
        base64_str = ''.join(base64_str.split())
        image_data = base64.b64decode(base64_str, validate=True)
    except (binascii.Error, ValueError) as e:
        raise HTTPException(
            status_code=400,
            detail=f"Erreur décodage base64 ({label}): {str(e)}"
        )

    if not image_data:
        raise HTTPException(status_code=400, detail=f"Image {label} vide après décodage")

    return image_data


# =========================
# GESTIONNAIRES D'ERREURS
# =========================

@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": exc.detail,
            "status_code": exc.status_code,
            "timestamp": datetime.datetime.utcnow().isoformat()
        }
    )


@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    logger.error(f"Exception non gérée: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": "Erreur interne",
            "detail": str(exc),
            "timestamp": datetime.datetime.utcnow().isoformat()
        }
    )


# =========================
# POINT D'ENTRÉE
# =========================

if __name__ == "__main__":
    import uvicorn
    
    host = "0.0.0.0"
    port = 8000
    
    logger.info(f"🚀 Démarrage OCR Service V2 sur {host}:{port}")
    logger.info(f"📚 Documentation: http://{host}:{port}/docs")
    
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info",
        reload=False
    )
