from typing import Dict, Any, List, Optional
import datetime
import logging
import numpy as np
import cv2
from document_types import DocumentType, DOCUMENT_FIELDS, get_required_fields
from document_strategy import DocumentStrategy
from document_detector import DocumentDetector
from ocr_processor import OCRProcessor
from typing import Tuple

logger = logging.getLogger(__name__)

class IdProcessorV2:
    """
    Classe principale qui orchestre OCR + extraction + validation
    """

    def __init__(self, lang: str = "fr"):
        self.default_lang = lang
        self.ocr_processors = {lang: OCRProcessor(lang=lang)}
        self.ocr_processor = self.ocr_processors[lang]
        self.detector = DocumentDetector()
        # MRZ OCR chargé à la demande pour éviter un coût de démarrage élevé.
        self.mrz_ocr = None
        logger.info("✅ IdProcessorV2 initialisé")

    def _get_ocr_processor(self, ocr_lang: Optional[str] = None) -> OCRProcessor:
        """Retourne un OCRProcessor pour la langue demandée (cache par langue)."""
        lang = (ocr_lang or self.default_lang or "fr").strip().lower()
        if lang not in self.ocr_processors:
            logger.info(f"🔤 Initialisation OCR langue: {lang}")
            self.ocr_processors[lang] = OCRProcessor(lang=lang)
        return self.ocr_processors[lang]

    def _get_mrz_ocr(self):
        """Initialise PaddleOCR MRZ uniquement au premier besoin."""
        if self.mrz_ocr is None:
            from paddleocr import PaddleOCR
            self.mrz_ocr = PaddleOCR(use_angle_cls=True, lang='en', det=True, rec=True)
            logger.info("✅ MRZ OCR initialisé (lazy load)")
        return self.mrz_ocr

    def get_supported_types(self) -> List[DocumentType]:
        """Retourne la liste des types de documents supportés"""
        return [dt for dt in DocumentType if dt != DocumentType.UNKNOWN]
    
    def process(self, image_bytes: bytes, code_document: Optional[str] = None, ocr_lang: Optional[str] = None) -> Dict[str, Any]:
        """Alias pour process_image_bytes (compatibilité avec main_v2.py)"""
        return self.process_image_bytes(image_bytes, code_document, ocr_lang)
    
    def process_multiple(self, images_bytes_list: List[bytes], code_document: Optional[str] = None, ocr_lang: Optional[str] = None) -> Dict[str, Any]:
        """
        Pipeline recto-verso: traite 2 images et fusionne les blocs OCR
        
        Args:
            images_bytes_list: Liste de 1-2 images (recto, verso optionnel)
            code_document: Code optionnel du type de document
        """
        start_time = datetime.datetime.now()
        try:
            # Vérifier qu'on a au moins 1 image
            if not images_bytes_list or len(images_bytes_list) == 0:
                return {"success": False, "error": "Aucune image fournie", "timestamp": datetime.datetime.utcnow().isoformat()}
            
            # Si une seule image, utiliser process_image_bytes direct
            if len(images_bytes_list) == 1:
                logger.info("📋 Process multiple: une seule image trouvée, utilisation du mode simple")
                return self.process_image_bytes(images_bytes_list[0], code_document, ocr_lang)
            
            # Mode recto-verso: traiter 2 images et fusionner
            logger.info(f"📋 Process multiple: {len(images_bytes_list)} image(s) à traiter")
            
            # OCR sur chaque image
            ocr_processor = self._get_ocr_processor(ocr_lang)
            all_blocks = []
            all_ocr_lines = []
            total_confidence = 0
            block_count = 0
            
            for idx, image_bytes in enumerate(images_bytes_list[:2]):  # Max 2 images
                logger.info(f"  📸 Traitement image {idx + 1}/{len(images_bytes_list[:2])}")
                
                # Prétraitement + OCR
                img = ocr_processor.preprocess(image_bytes)
                ocr_data = ocr_processor.run_ocr(img)
                
                # Offset le block ID pour éviter les doublons
                block_offset = idx * 10000
                for block in ocr_data["blocks"]:
                    block["id"] = block["id"] + block_offset  # Unique ID pour chaque image
                    block["page"] = idx  # Ajouter le numéro de page (0=recto, 1=verso)
                    all_blocks.append(block)
                
                all_ocr_lines.extend(ocr_data["lines"])
                total_confidence += ocr_data["avg_conf"]
                block_count += len(ocr_data["blocks"])
            
            # Fusionner les OCR data
            merged_ocr = {
                "blocks": all_blocks,
                "lines": all_ocr_lines,
                "full_text": " ".join(all_ocr_lines),
                "avg_conf": round(total_confidence / len(images_bytes_list[:2]), 3),
                "total_blocks": block_count
            }
            
            # Identifier type de document (avec code optionnel)
            doc_type, confidence = self._identify_document_type(merged_ocr["full_text"], code_document)
            
            # Extraction principale sur blocs fusionnés
            extracted = DocumentStrategy.extract(doc_type, merged_ocr["blocks"])
            
            # Si c'est un passeport, essayer la détection MRZ spécifique
            if doc_type in (DocumentType.PASSPORT, DocumentType.PASSPORT_BIOMETRIC):
                # Essayer MRZ sur la deuxième image seulement (verso du passeport)
                if len(images_bytes_list) >= 2:
                    mrz_text = self.extract_mrz_text(images_bytes_list[1])
                    if mrz_text and len(mrz_text) > 20:
                        parsed_mrz = self.parse_mrz(mrz_text)
                        for key, value in parsed_mrz.items():
                            if key not in extracted:
                                extracted[key] = value
                            elif value.get('confidence', 0) > extracted[key].get('confidence', 0):
                                extracted[key] = value
            
            # 🔥 Nettoyage: Supprimer les champs legacy avec confiance 0
            legacy_fields = ['passport_number', 'name', 'dob', 'expiration_date']
            for field in legacy_fields:
                if field in extracted and extracted[field].get('confidence', 1) == 0:
                    del extracted[field]
            
            # Validation
            validation = self._validate_extraction(extracted, doc_type)
            
            processing_time = (datetime.datetime.now() - start_time).total_seconds()
            
            # Construire la réponse finale
            result = {
                "success": True,
                "timestamp": datetime.datetime.utcnow().isoformat(),
                "processing_time_seconds": round(processing_time, 3),
                "mode": "recto-verso" if len(images_bytes_list) >= 2 else "simple",
                "images_processed": len(images_bytes_list),
                "document_type": doc_type.value,
                "document_type_confidence": round(confidence, 2),
                "extracted_data": extracted,
                "validation": validation,
                "blocks": merged_ocr["blocks"]
            }
            
            return result
            
        except Exception as e:
            logger.error(f"Erreur process_multiple: {e}", exc_info=True)
            return {"success": False, "error": str(e), "timestamp": datetime.datetime.utcnow().isoformat()}
    
    def process_ocr_only(self, image_bytes: bytes, ocr_lang: Optional[str] = None) -> Dict[str, Any]:
        """OCR uniquement sans extraction"""
        start_time = datetime.datetime.now()
        try:
            ocr_processor = self._get_ocr_processor(ocr_lang)
            img = ocr_processor.preprocess(image_bytes)
            ocr_data = ocr_processor.run_ocr(img)
            processing_time = (datetime.datetime.now() - start_time).total_seconds()
            return {
                "success": True,
                "timestamp": datetime.datetime.utcnow().isoformat(),
                "processing_time_seconds": round(processing_time, 3),
                "image_size": ocr_data["image_size"],
                "text_found": len(ocr_data["blocks"]) > 0,
                "total_blocks": len(ocr_data["blocks"]),
                "full_text": ocr_data["full_text"],
                "blocks": ocr_data["blocks"],
                "statistics": {
                    "average_confidence": round(ocr_data["avg_conf"], 3)
                }
            }
        except Exception as e:
            logger.error(f"Erreur process_ocr_only: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.datetime.utcnow().isoformat()
            }

    def process_image_bytes(self, image_bytes: bytes, code_document: Optional[str] = None, ocr_lang: Optional[str] = None) -> Dict[str, Any]:
        """
        Pipeline complet: OCR, extraction, validation
        """
        start_time = datetime.datetime.now()
        try:
            # Prétraitement + OCR
            ocr_processor = self._get_ocr_processor(ocr_lang)
            img = ocr_processor.preprocess(image_bytes)
            ocr_data = ocr_processor.run_ocr(img)

            # Identifier type de document (avec code optionnel)
            doc_type, confidence = self._identify_document_type(ocr_data["full_text"], code_document)

            # Extraction principale
            extracted = DocumentStrategy.extract(doc_type, ocr_data["blocks"])

            # Si c'est un passeport, essayer la détection MRZ spécifique
            if doc_type in (DocumentType.PASSPORT, DocumentType.PASSPORT_BIOMETRIC):
                mrz_text = self.extract_mrz_text(image_bytes)
                if mrz_text and len(mrz_text) > 20:  # MRZ valide
                    parsed_mrz = self.parse_mrz(mrz_text)
                    # Fusionner intelligemment (ne pas écraser les champs existants)
                    for key, value in parsed_mrz.items():
                        if key not in extracted:
                            extracted[key] = value
                        elif value.get('confidence', 0) > extracted[key].get('confidence', 0):
                            extracted[key] = value

            # 🔥 NETTOYAGE : Supprimer les champs legacy avec confiance 0
            legacy_fields = ['passport_number', 'name', 'dob', 'expiration_date']
            for field in legacy_fields:
                if field in extracted and extracted[field].get('confidence', 1) == 0:
                    del extracted[field]

            # Validation
            validation = self._validate_extraction(extracted, doc_type)

            processing_time = (datetime.datetime.now() - start_time).total_seconds()
            
            # Construire la réponse finale sans les champs legacy
            result = {
                "success": True,
                "timestamp": datetime.datetime.utcnow().isoformat(),
                "processing_time_seconds": round(processing_time, 3),
                "document_type": doc_type.value,
                "document_type_confidence": round(confidence, 2),
                "extracted_data": extracted,
                "validation": validation,
                "blocks": ocr_data["blocks"]
            }
            
            return result

        except Exception as e:
            logger.error(f"Erreur process_image_bytes: {e}", exc_info=True)
            return {"success": False, "error": str(e), "timestamp": datetime.datetime.utcnow().isoformat()}

    def extract_mrz_text(self, image_bytes: bytes) -> str:
        """Extraire le texte MRZ en utilisant PaddleOCR"""
        try:
            mrz_ocr = self._get_mrz_ocr()
            # Convertir en image OpenCV
            nparr = np.frombuffer(image_bytes, np.uint8)
            image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            height, width, _ = image.shape
            # Découpe zone inférieure MRZ
            mrz_zone = image[int(height*0.6):, :]

            result = mrz_ocr.ocr(mrz_zone)
            lines = []
            for line in result:
                line_text = ''.join([word_info[1][0] for word_info in line])
                lines.append(line_text)
            mrz_text = '\n'.join(lines)
            return mrz_text
        except Exception as e:
            logger.error(f"Erreur extraction MRZ: {e}")
            return ""

    def parse_mrz(self, mrz_text: str) -> Dict[str, Any]:
        """
        Parse une MRZ TD3 (passeport) et retourne les champs extraits.
        """
        if not mrz_text or len(mrz_text) < 20:
            return {}

        try:
            from mrz_parser import MRZParser

            # Nettoyage et normalisation des lignes OCR MRZ.
            raw_lines = [ln.strip().replace(' ', '') for ln in mrz_text.splitlines() if ln.strip()]
            if not raw_lines:
                return {}

            candidates = []
            for ln in raw_lines:
                line = ln.upper()
                if '<' not in line:
                    continue
                # Garde uniquement le charset MRZ standard pour limiter le bruit OCR.
                line = ''.join(ch for ch in line if ch.isalnum() or ch == '<')
                if len(line) >= 30:
                    candidates.append(line)

            if len(candidates) < 2:
                return {}

            # TD3: prendre deux lignes consécutives les plus longues proches de 44 chars.
            candidates = sorted(candidates, key=len, reverse=True)
            line1 = candidates[0][:44]
            line2 = candidates[1][:44]

            parsed = MRZParser.parse_td3(line1, line2)
            if isinstance(parsed, dict):
                return parsed

            return {}
        except Exception as e:
            logger.error(f"Erreur parse_mrz: {e}")
            return {}

    # ---------------------------
    # Identification type document (avec code optionnel)
    # ---------------------------
    def _identify_document_type(self, text: str, code: Optional[str] = None) -> Tuple[DocumentType, float]:
        from document_types import DOCUMENT_CODE_MAP
        if code:
            doc_type = DOCUMENT_CODE_MAP.get(code)
            if doc_type:
                logger.info(f"📋 Type détecté par code '{code}': {doc_type.value}")
                return doc_type, 1.0
            else:
                logger.warning(f"⚠️ Code document inconnu: '{code}', détection auto")

        synthetic_blocks = [{"text": text, "confidence": 1.0}]
        detected_type = self.detector.detect(synthetic_blocks)
        if detected_type == DocumentType.UNKNOWN:
            return DocumentType.UNKNOWN, 0.0

        confidence = self.detector.get_detection_confidence(synthetic_blocks, detected_type)
        logger.info(
            "📋 Type détecté automatiquement: %s (confiance: %.2f)",
            detected_type.value,
            confidence,
        )
        return detected_type, confidence

    # ---------------------------
    # Validation générique
    # ---------------------------
    def _validate_extraction(self, extracted: Dict[str, Any], doc_type: DocumentType) -> Dict[str, Any]:
        required_fields = get_required_fields(doc_type)
        found = []
        missing = []

        for field in required_fields:
            data = extracted.get(field)
            value = data.get("value", "") if isinstance(data, dict) else ""
            if isinstance(value, str) and value.strip():
                found.append(field)
            else:
                missing.append(field)

        score = len(found)/len(required_fields) if required_fields else 0
        return {
            "champs_requis_trouves": found,
            "champs_requis_manquants": missing,
            "score": round(score,2),
            "est_valide": score >= 0.7
        }