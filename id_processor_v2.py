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

    def _detect_and_split_multipage(self, image_bytes: bytes) -> List[bytes]:
        """
        Détecte si une image contient 2 pages et les scinde si nécessaire.
        
        Heuristique:
        - Si l'image a un ratio hauteur/largeur > 1.8, elle contient probablement 2 pages
        - Scinde l'image horizontalement au milieu si détection de 2 pages
        
        Retourne:
            Lista de 1 ou 2 images (bytes)
        """
        try:
            # Décoder l'image
            nparr = np.frombuffer(image_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            if img is None:
                logger.warning("Unable to decode image for multipage detection")
                return [image_bytes]
            
            height, width = img.shape[:2]
            aspect_ratio = height / width if width > 0 else 0
            
            logger.debug(f"Image dimensions: {width}x{height}, aspect ratio: {aspect_ratio:.2f}")
            
            # Détection multi-pages : ratio hauteur/largeur > 1.7
            if aspect_ratio > 1.7:
                logger.info(f"📄 Image multi-pages détectée (aspect ratio: {aspect_ratio:.2f})")
                
                # Scinder l'image en deux : haut et bas (recto et verso)
                mid_height = height // 2
                top_page = img[:mid_height, :]
                bottom_page = img[mid_height:, :]
                
                # Encoder les deux pages en bytes
                _, top_bytes = cv2.imencode('.jpg', top_page)
                _, bottom_bytes = cv2.imencode('.jpg', bottom_page)
                
                logger.info(f"  ✂️ Image scindée en 2 pages: {width}x{mid_height} et {width}x{height-mid_height}")
                return [top_bytes.tobytes(), bottom_bytes.tobytes()]
            else:
                logger.debug("Image simple (une seule page)")
                return [image_bytes]
                
        except Exception as e:
            logger.warning(f"Error detecting multipage: {e}, returning original image")
            return [image_bytes]

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
        Avec support multi-pages et fallback MRZ agressif
        """
        start_time = datetime.datetime.now()
        try:
            # Étape 1: Détection et scission multi-pages
            image_list = self._detect_and_split_multipage(image_bytes)
            
            # Étape 2: Si l'image a été scindée, utiliser process_multiple
            if len(image_list) > 1:
                logger.info("🔄 Image multi-pages détectée, basculement vers process_multiple")
                return self.process_multiple(image_list, code_document, ocr_lang)
            
            # Étape 3: Prétraitement + OCR image unique
            ocr_processor = self._get_ocr_processor(ocr_lang)
            img = ocr_processor.preprocess(image_bytes)
            ocr_data = ocr_processor.run_ocr(img)

            # Étape 4: Identification du type de document
            doc_type, confidence = self._identify_document_type(ocr_data["full_text"], code_document)

            # Étape 5: Extraction principale
            extracted = DocumentStrategy.extract(doc_type, ocr_data["blocks"])

            # Étape 6: Validation initiale
            validation = self._validate_extraction(extracted, doc_type)
            validation_score = validation.get('score', 0)
            
            logger.debug(f"Initial validation score: {validation_score}")

            # Étape 7: FALLBACK MRZ AGRESSIF
            # Si score validation < 0.3 (très faible) ET c'est un passeport, tenter MRZ fortement
            if validation_score < 0.3 and doc_type in (DocumentType.PASSPORT, DocumentType.PASSPORT_BIOMETRIC):
                logger.warning(f"⚠️ Score validation très faible ({validation_score}), tentative extraction MRZ aggressive")
                
                mrz_text = self.extract_mrz_text(image_bytes)
                if mrz_text and len(mrz_text) > 20:
                    parsed_mrz = self.parse_mrz(mrz_text)
                    
                    if parsed_mrz:
                        logger.info(f"✅ MRZ extraction réussie: {len(parsed_mrz)} champs trouvés")
                        
                        # Fusionner AGRESSIVEMENT: remplacer les champs vides/faibles
                        for key, value in parsed_mrz.items():
                            if key not in extracted or not extracted[key].get('value'):
                                # Champ manquant: ajouter depuis MRZ
                                extracted[key] = value
                                logger.debug(f"  ✅ Champ {key} rempli depuis MRZ")
                            elif value.get('confidence', 0) >= 0.95:
                                # MRZ a haute confiance: peut remplacer
                                old_conf = extracted[key].get('confidence', 0)
                                if old_conf < 0.80 or (old_conf >= 0 and old_conf != 0 and value['confidence'] > old_conf):
                                    extracted[key] = value
                                    logger.debug(f"  🔄 Champ {key} remplacé (MRZ confiance: {value['confidence']:.2f} vs {old_conf:.2f})")
                        
                        # Revalider après fusion MRZ
                        validation = self._validate_extraction(extracted, doc_type)
                        logger.info(f"✅ Score validation après MRZ fallback: {validation.get('score', 0)}")

            # Étape 8: Nettoyage des champs legacy
            legacy_fields = ['passport_number', 'name', 'dob', 'expiration_date']
            for field in legacy_fields:
                if field in extracted and extracted[field].get('confidence', 1) == 0:
                    del extracted[field]

            processing_time = (datetime.datetime.now() - start_time).total_seconds()
            
            # Étape 9: Construire la réponse finale
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
        """
        Extraire le texte MRZ en utilisant PaddleOCR
        Stratégie:
        1. Chercher la zone MRZ (généralement en bas de l'image)
        2. Appliquer OCR avec lang=english pour meilleure reconnaissance des caractères
        3. Retourner le texte brut trouvé
        """
        try:
            mrz_ocr = self._get_mrz_ocr()
            # Convertir en image OpenCV
            nparr = np.frombuffer(image_bytes, np.uint8)
            image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            if image is None:
                logger.warning("Cannot decode image for MRZ extraction")
                return ""
            
            height, width, _ = image.shape
            
            # Stratégie 1: Chercher MRZ dans les 40% inférieurs (zone typique des passeports)
            mrz_zone_start = int(height * 0.60)
            mrz_zone = image[mrz_zone_start:, :]
            
            logger.debug(f"MRZ zone: {width}x{height-mrz_zone_start} (height {mrz_zone_start} to {height})")
            
            # OCR sur la zone MRZ
            result = mrz_ocr.ocr(mrz_zone)
            lines = []
            
            if result and result[0]:
                for line in result[0]:
                    line_text = ''.join([word_info[1][0] for word_info in line])
                    if line_text.strip():
                        lines.append(line_text.strip())
            
            mrz_text = '\n'.join(lines)
            
            if mrz_text:
                logger.info(f"✅ MRZ text found ({len(lines)} lines): \n{mrz_text[:100]}...")
            else:
                logger.warning("No MRZ text found in lower zone, trying full image OCR")
                # Fallback: essayer sur toute l'image si rien en bas
                result = mrz_ocr.ocr(image)
                if result and result[0]:
                    for line in result[0]:
                        line_text = ''.join([word_info[1][0] for word_info in line])
                        if '<' in line_text and len(line_text) >= 30:
                            lines.append(line_text.strip())
                mrz_text = '\n'.join(lines)
            
            return mrz_text
            
        except Exception as e:
            logger.error(f"Erreur extraction MRZ: {e}")
            return ""

    def parse_mrz(self, mrz_text: str) -> Dict[str, Any]:
        """
        Parse une MRZ TD3 (passeport) et retourne les champs extraits.
        Amélioration: meilleure extraction et nettoyage du texte MRZ
        """
        if not mrz_text or len(mrz_text) < 20:
            logger.warning("MRZ text too short for parsing")
            return {}

        try:
            from mrz_parser import MRZParser

            # Nettoyage et normalisation des lignes OCR MRZ
            raw_lines = [ln.strip().replace(' ', '') for ln in mrz_text.splitlines() if ln.strip()]
            
            if not raw_lines:
                logger.warning("No lines found in MRZ text")
                return {}

            logger.debug(f"MRZ raw lines ({len(raw_lines)}): {raw_lines}")

            # Filtrer et nettoyer les candidats MRZ
            candidates = []
            for ln in raw_lines:
                line = ln.upper()
                
                # Une ligne MRZ valide contient '<' et fait au moins 30 chars
                if '<' not in line and len(line) < 30:
                    continue
                
                # Garder uniquement le charset MRZ standard (A-Z, 0-9, <)
                cleaned = ''.join(ch for ch in line if ch.isalnum() or ch == '<')
                
                if len(cleaned) >= 30:
                    candidates.append(cleaned)
                    logger.debug(f"  Candidat MRZ: {cleaned[:50]}...")

            if len(candidates) < 2:
                logger.warning(f"Pas assez de candidats MRZ: {len(candidates)} trouvés")
                return {}

            # TD3: prendre les deux lignes les plus longues et proches de 44 chars
            candidates = sorted(candidates, key=len, reverse=True)
            
            # Essayer différentes combinaisons de paires
            for i in range(len(candidates)):
                for j in range(i + 1, len(candidates)):
                    line1 = candidates[i][:44]
                    line2 = candidates[j][:44]
                    
                    logger.debug(f"Tentative parse TD3 avec lignes {i},{j}:")
                    logger.debug(f"  L1: {line1}")
                    logger.debug(f"  L2: {line2}")
                    
                    parsed = MRZParser.parse_td3(line1, line2)
                    
                    if parsed and len(parsed) > 0:
                        logger.info(f"✅ Parsing TD3 réussi avec lignes {i},{j}")
                        return parsed
            
            logger.warning("Impossible de parser les lignes MRZ")
            return {}
            
        except Exception as e:
            logger.error(f"Erreur parse_mrz: {e}", exc_info=True)
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