"""
validator.py - Validation des champs extraits avec scoring pondéré
"""

import re
import logging
from typing import Dict, Any
from datetime import datetime

from document_types import DocumentType, get_required_fields, get_optional_fields, get_field_weight

logger = logging.getLogger(__name__)


class FieldValidator:
    """Validateur de champs avec scoring pondéré"""
    
    def __init__(self):
        pass
    
    def validate(self, extracted: Dict[str, Any], doc_type: DocumentType) -> Dict[str, Any]:
        """
        Valide les données extraites et calcule les scores
        """
        # Champs requis et optionnels
        required = get_required_fields(doc_type)
        optional = get_optional_fields(doc_type)
        
        # Champs trouvés
        found_required = [f for f in required if f in extracted]
        found_optional = [f for f in optional if f in extracted]
        missing_required = [f for f in required if f not in extracted]
        
        # Score de complétude (pondéré: requis 80%, optionnel 20%)
        required_score = len(found_required) / len(required) if required else 0
        optional_score = len(found_optional) / len(optional) if optional else 0
        completeness_score = (required_score * 0.8) + (optional_score * 0.2)
        
        # Score de confiance pondéré
        weighted_confidence = self._calculate_weighted_confidence(extracted)
        
        # Score de validité des champs
        validity_score = self._calculate_validity_score(extracted, doc_type)
        
        # Score global (combinaison)
        global_score = (
            completeness_score * 0.4 +
            weighted_confidence * 0.4 +
            validity_score * 0.2
        )
        
        # Vérifier si le document est valide
        is_valid = (
            global_score >= 0.6 and
            len(found_required) >= max(2, len(required) * 0.5)  # Au moins 50% des requis
        )
        
        return {
            "is_valid": is_valid,
            "global_score": round(global_score, 3),
            "completeness_score": round(completeness_score, 3),
            "avg_confidence": round(weighted_confidence, 3),
            "validity_score": round(validity_score, 3),
            "fields_found": list(extracted.keys()),
            "fields_found_required": found_required,
            "fields_found_optional": found_optional,
            "fields_missing_required": missing_required,
            "total_required": len(required),
            "total_optional": len(optional)
        }
    
    def _calculate_weighted_confidence(self, extracted: Dict[str, Any]) -> float:
        """
        Calcule la confiance moyenne pondérée par importance des champs
        """
        total_score = 0
        total_weight = 0
        
        for field, data in extracted.items():
            if not isinstance(data, dict):
                continue
            
            weight = get_field_weight(field)
            confidence = data.get("confidence", 0)
            
            total_score += confidence * weight
            total_weight += weight
        
        return total_score / total_weight if total_weight > 0 else 0
    
    def _calculate_validity_score(self, extracted: Dict[str, Any], doc_type: DocumentType) -> float:
        """
        Calcule le score de validité des champs (format correct)
        """
        valid_count = 0
        total_count = 0
        
        for field, data in extracted.items():
            if not isinstance(data, dict):
                continue
            
            value = data.get("value", "")
            is_valid = self._validate_field_format(field, value, doc_type)
            
            if is_valid:
                valid_count += 1
            total_count += 1
        
        return valid_count / total_count if total_count > 0 else 0
    
    def _validate_field_format(self, field_name: str, value: str, doc_type: DocumentType) -> bool:
        """
        Valide le format d'un champ
        """
        if not value or len(value.strip()) < 2:
            return False
        
        value_clean = value.strip()
        
        # Validation par type de champ
        if field_name == "numero":
            return self._validate_numero(value_clean, doc_type)
        
        if field_name in ["date_naissance", "date_expiration", "date_delivrance"]:
            return self._validate_date(value_clean)
        
        if field_name in ["nom", "prenom"]:
            return self._validate_name(value_clean)
        
        if field_name == "sexe":
            return value_clean.upper() in ["M", "F", "MASCULIN", "FEMININ", "MALE", "FEMALE"]
        
        if field_name == "nationalite":
            return len(value_clean) >= 2 and value_clean.replace(" ", "").isalpha()
        
        # Par défaut, accepter si non vide
        return True
    
    def _validate_numero(self, value: str, doc_type: DocumentType) -> bool:
        """Valide le numéro selon le type de document"""
        value_clean = re.sub(r'[\s\-]', '', value)
        
        if doc_type == DocumentType.NINA_CARD:
            # NINA: 12 chiffres ou variante alphanumerique longue.
            return bool(re.match(r'^(\d{12}|\d{14,16}[A-Z])$', value_clean.upper()))

        if doc_type in [DocumentType.PASSPORT, DocumentType.PASSPORT_BIOMETRIC]:
            # Alphanumérique 7-9 caractères (passeports standards).
            return bool(re.match(r'^[A-Z0-9]{7,9}$', value_clean.upper()))

        if doc_type in [DocumentType.ID_CARD, DocumentType.CIN_BIOMETRIC]:
            return 8 <= len(value_clean) <= 14 and value_clean.isalnum()
        
        # Générique: 6-15 caractères alphanumériques
        return 6 <= len(value_clean) <= 15
    
    def _validate_date(self, value: str) -> bool:
        """Valide une date"""
        # Format DD/MM/YYYY
        match = re.match(r'^(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{4})$', value)
        if match:
            try:
                day, month, year = map(int, match.groups())
                
                # Vérifications basiques
                if not (1 <= day <= 31):
                    return False
                if not (1 <= month <= 12):
                    return False
                if not (1900 <= year <= 2100):
                    return False
                
                # Vérifier que la date est valide
                datetime(year, month, day)
                return True
            except ValueError:
                return False
        
        # Format YYMMDD (MRZ)
        match_mrz = re.match(r'^(\d{2})(\d{2})(\d{2})$', value)
        if match_mrz:
            try:
                yy, mm, dd = map(int, match_mrz.groups())
                
                # Déterminer le siècle
                yyyy = 2000 + yy if yy < 50 else 1900 + yy
                
                if not (1 <= dd <= 31):
                    return False
                if not (1 <= mm <= 12):
                    return False
                
                datetime(yyyy, mm, dd)
                return True
            except ValueError:
                return False
        
        return False
    
    def _validate_name(self, value: str) -> bool:
        """Valide un nom ou prénom"""
        # Au moins 70% de lettres
        letter_count = sum(1 for c in value if c.isalpha() or c.isspace() or c in "-'")
        total_count = len(value)
        
        return letter_count >= total_count * 0.7 if total_count > 0 else False
