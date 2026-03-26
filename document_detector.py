"""document_detector.py - Detection du type de document basee sur un registre."""

import logging
import re
from typing import Any, Dict, List

from document_types import (
    DETECTION_KEYWORDS,
    DOCUMENT_DEFINITIONS,
    DocumentType,
    get_detection_number_patterns,
)

logger = logging.getLogger(__name__)


class DocumentDetector:
    """Detecte le type de document a partir des blocs OCR."""

    def __init__(self):
        self.keywords = DETECTION_KEYWORDS

    def detect(self, blocks: List[Dict[str, Any]]) -> DocumentType:
        """Detecte le type de document avec un scoring configurable."""
        if not blocks:
            return DocumentType.UNKNOWN

        full_text = " ".join(str(b.get("text", "")).upper() for b in blocks)
        scores = {doc_type: 0.0 for doc_type in DOCUMENT_DEFINITIONS.keys()}

        if self._has_mrz(blocks):
            scores[DocumentType.PASSPORT_BIOMETRIC] += 4.0
            scores[DocumentType.PASSPORT] += 2.0

        for doc_type, keywords in self.keywords.items():
            for keyword in keywords:
                if keyword and keyword.upper() in full_text:
                    scores[doc_type] += 1.0

        number_scores = self._detect_by_number_format(blocks)
        for doc_type, score in number_scores.items():
            scores[doc_type] = scores.get(doc_type, 0.0) + score

        structure_scores = self._detect_by_structure(blocks)
        for doc_type, score in structure_scores.items():
            scores[doc_type] = scores.get(doc_type, 0.0) + score

        best_type, best_score = max(scores.items(), key=lambda x: x[1])
        if best_score <= 0:
            logger.warning("Type de document non reconnu")
            return DocumentType.UNKNOWN

        logger.info("Document detecte: %s (score %.2f)", best_type.value, best_score)
        return best_type

    def _has_mrz(self, blocks: List[Dict[str, Any]]) -> bool:
        """Verifie la presence d'une zone MRZ."""
        for block in blocks:
            text = str(block.get("text", "")).upper().strip()
            if text.startswith("P<") and len(text) >= 40:
                return True
            if len(text) >= 40 and " " not in text and re.match(r"^[A-Z0-9<]+$", text):
                return True
        return False

    def _detect_by_number_format(self, blocks: List[Dict[str, Any]]) -> Dict[DocumentType, float]:
        """Ajoute des points selon les motifs numeriques declares par type."""
        scores: Dict[DocumentType, float] = {}
        normalized_texts = [re.sub(r"[\s\-]", "", str(b.get("text", "")).upper()) for b in blocks]

        for doc_type in DOCUMENT_DEFINITIONS.keys():
            patterns = get_detection_number_patterns(doc_type)
            if not patterns:
                continue
            for normalized in normalized_texts:
                for pattern in patterns:
                    if re.search(pattern, normalized):
                        scores[doc_type] = scores.get(doc_type, 0.0) + 1.2
                        break

        return scores

    def _detect_by_structure(self, blocks: List[Dict[str, Any]]) -> Dict[DocumentType, float]:
        """Heuristiques legeres pour completer la detection par texte/patterns."""
        scores: Dict[DocumentType, float] = {}
        total_blocks = len(blocks)

        if total_blocks > 20:
            scores[DocumentType.PASSPORT_BIOMETRIC] = scores.get(DocumentType.PASSPORT_BIOMETRIC, 0.0) + 0.4
            scores[DocumentType.PASSPORT] = scores.get(DocumentType.PASSPORT, 0.0) + 0.2

        if total_blocks < 12:
            scores[DocumentType.ID_CARD] = scores.get(DocumentType.ID_CARD, 0.0) + 0.2
            scores[DocumentType.CIN_BIOMETRIC] = scores.get(DocumentType.CIN_BIOMETRIC, 0.0) + 0.2

        return scores

    def get_detection_confidence(self, blocks: List[Dict[str, Any]], detected_type: DocumentType) -> float:
        """Calcule une confiance de detection a partir des correspondances keyword."""
        full_text = " ".join(str(b.get("text", "")).upper() for b in blocks)
        keywords = self.keywords.get(detected_type, [])
        keyword_matches = sum(1 for kw in keywords if kw and kw.upper() in full_text)

        if keyword_matches >= 3:
            return 0.95
        if keyword_matches == 2:
            return 0.85
        if keyword_matches == 1:
            return 0.7
        return 0.5
