from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List


class DocumentType(Enum):
    NINA_CARD = "Carte NINA"
    ID_CARD = "Carte Nationale d'Identité"
    PASSPORT = "Passeport"
    DRIVER_LICENSE = "Permis de Conduire"
    RESIDENCE_PERMIT = "Titre de Séjour"
    VISA = "Visa"
    CIN_BIOMETRIC = "CIN Biométrique"
    PASSPORT_BIOMETRIC = "Passeport Biométrique"
    BIRTH_CERTIFICATE = "Extrait de Naissance"
    UNKNOWN = "Document inconnu"


@dataclass(frozen=True)
class DocumentDefinition:
    document_type: DocumentType
    required_fields: List[str]
    optional_fields: List[str] = field(default_factory=list)
    codes: List[str] = field(default_factory=list)
    detection_keywords: List[str] = field(default_factory=list)
    detection_number_patterns: List[str] = field(default_factory=list)
    features: List[str] = field(default_factory=list)


DOCUMENT_DEFINITIONS: Dict[DocumentType, DocumentDefinition] = {
    DocumentType.NINA_CARD: DocumentDefinition(
        document_type=DocumentType.NINA_CARD,
        required_fields=["numero_nina", "prenom", "nom", "date_naissance", "date_delivrance", "date_expiration"],
        optional_fields=["lieu_naissance", "lieu_delivrance"],
        detection_keywords=["NINA", "CARTE NINA", "IDENTIFICATION NATIONALE"],
        detection_number_patterns=[r"\b\d{12}\b", r"\b\d{14,16}[A-Z]\b"],
        features=["Numero NINA", "Support formats 12 chiffres et alphanumerique"],
    ),
    DocumentType.ID_CARD: DocumentDefinition(
        document_type=DocumentType.ID_CARD,
        required_fields=["numero_id", "prenom", "nom", "date_naissance", "date_delivrance", "date_expiration"],
        optional_fields=["lieu_delivrance", "sexe"],
        codes=["01", "03", "24"],
        detection_keywords=["CARTE NATIONALE", "IDENTITE", "CNI", "CIN"],
        detection_number_patterns=[r"\b\d{8,14}\b"],
        features=["Extraction identite standard", "Gestion date delivrance/expiration"],
    ),
    DocumentType.PASSPORT: DocumentDefinition(
        document_type=DocumentType.PASSPORT,
        required_fields=["numero_passeport", "prenom", "nom", "date_naissance", "date_delivrance", "date_expiration"],
        optional_fields=["lieu_delivrance", "sexe", "nationalite"],
        codes=["02"],
        detection_keywords=["PASSPORT", "PASSEPORT", "PASAPORT", "PP"],
        detection_number_patterns=[r"\b[A-Z]{1,2}\d{6,9}\b", r"\b[A-Z]\d{6,7}[A-Z]{2}\b"],
        features=["Support MRZ", "Extraction noms/prenoms multilingue"],
    ),
    DocumentType.DRIVER_LICENSE: DocumentDefinition(
        document_type=DocumentType.DRIVER_LICENSE,
        required_fields=["numero_permis", "prenom", "nom", "date_naissance", "date_delivrance", "date_expiration"],
        optional_fields=["categories", "lieu_delivrance", "restrictions"],
        codes=["05"],
        detection_keywords=["PERMIS", "CONDUIRE", "DRIVING LICENCE", "DRIVER LICENSE"],
        detection_number_patterns=[r"\b[A-Z0-9]{6,16}\b"],
        features=["Extraction categories", "Support date validite"],
    ),
    DocumentType.RESIDENCE_PERMIT: DocumentDefinition(
        document_type=DocumentType.RESIDENCE_PERMIT,
        required_fields=["numero_titre", "prenom", "nom", "date_naissance", "date_expiration"],
        optional_fields=["nationalite", "type_titre", "lieu_delivrance"],
        codes=["04", "23"],
        detection_keywords=["TITRE DE SEJOUR", "SEJOUR", "RESIDENCE", "PERMIT"],
        detection_number_patterns=[r"\b[A-Z0-9]{7,16}\b"],
        features=["Extraction type titre", "Support cartes biometrie"],
    ),
    DocumentType.VISA: DocumentDefinition(
        document_type=DocumentType.VISA,
        required_fields=["numero_visa", "prenom", "nom", "date_naissance", "date_expiration"],
        optional_fields=["nationalite", "type_visa", "lieu_delivrance"],
        detection_keywords=["VISA", "ENTRY", "MULTIPLE ENTRY", "SEJOUR"],
        detection_number_patterns=[r"\b[A-Z0-9]{6,16}\b"],
        features=["Extraction type visa", "Support nationalite"],
    ),
    DocumentType.CIN_BIOMETRIC: DocumentDefinition(
        document_type=DocumentType.CIN_BIOMETRIC,
        required_fields=["numero_id", "prenom", "nom", "date_naissance", "date_delivrance", "date_expiration"],
        optional_fields=["lieu_delivrance", "sexe"],
        codes=["21"],
        detection_keywords=["BIOMETRIC", "BIOMETRIQUE", "CIN", "IDENTITE"],
        detection_number_patterns=[r"\b\d{8,14}\b"],
        features=["Detection biometrie", "Extraction identite"],
    ),
    DocumentType.PASSPORT_BIOMETRIC: DocumentDefinition(
        document_type=DocumentType.PASSPORT_BIOMETRIC,
        required_fields=["numero_passeport", "prenom", "nom", "date_naissance", "date_delivrance", "date_expiration"],
        optional_fields=["lieu_delivrance", "sexe", "nationalite"],
        codes=["22"],
        detection_keywords=["BIOMETRIC PASSPORT", "PASSPORT", "P<", "ICAO"],
        detection_number_patterns=[r"\b[A-Z]{1,2}\d{6,9}\b", r"\b[A-Z]{2}\d{7}\b"],
        features=["Parsing MRZ TD3", "Support passeport biometrique"],
    ),
    DocumentType.BIRTH_CERTIFICATE: DocumentDefinition(
        document_type=DocumentType.BIRTH_CERTIFICATE,
        required_fields=["prenom", "nom", "date_naissance"],
        optional_fields=["lieu_naissance", "numero_acte"],
        codes=["17"],
        detection_keywords=["EXTRAIT DE NAISSANCE", "ACTE DE NAISSANCE", "BIRTH CERTIFICATE"],
        detection_number_patterns=[r"\b\d{4,12}\b"],
        features=["Extraction filiation", "Support numero acte"],
    ),
}


# Mapping code document -> DocumentType
DOCUMENT_CODE_MAP: Dict[str, DocumentType] = {
    code: definition.document_type
    for definition in DOCUMENT_DEFINITIONS.values()
    for code in definition.codes
}

# Champs attendus pour chaque type de document
DOCUMENT_FIELDS: Dict[DocumentType, List[str]] = {
    doc_type: definition.required_fields + definition.optional_fields
    for doc_type, definition in DOCUMENT_DEFINITIONS.items()
}

# Champs essentiels (requis) par type de document
REQUIRED_FIELDS: Dict[DocumentType, List[str]] = {
    doc_type: definition.required_fields
    for doc_type, definition in DOCUMENT_DEFINITIONS.items()
}

# Champs optionnels par type de document
OPTIONAL_FIELDS: Dict[DocumentType, List[str]] = {
    doc_type: definition.optional_fields
    for doc_type, definition in DOCUMENT_DEFINITIONS.items()
}

# Mots-cles pour la detection (utilise aussi par DocumentDetector)
DETECTION_KEYWORDS: Dict[DocumentType, List[str]] = {
    doc_type: definition.detection_keywords
    for doc_type, definition in DOCUMENT_DEFINITIONS.items()
}

DOCUMENT_FEATURES: Dict[DocumentType, List[str]] = {
    doc_type: definition.features
    for doc_type, definition in DOCUMENT_DEFINITIONS.items()
}

# Poids des champs pour le scoring (plus le poids est élevé, plus important)
FIELD_WEIGHTS: Dict[str, float] = {
    # Identifiants (très importants)
    "numero_id": 1.0,
    "numero_passeport": 1.0,
    "numero_nina": 1.0,
    "numero_permis": 0.95,
    "numero_titre": 0.95,
    "numero_visa": 0.95,
    # Données personnelles (très importants)
    "prenom": 0.95,
    "nom": 0.95,
    "date_naissance": 0.9,
    # Dates (importants)
    "date_delivrance": 0.8,
    "date_expiration": 0.8,
    "date_emission": 0.75,
    # Localisation
    "lieu_naissance": 0.7,
    "lieu_delivrance": 0.65,
    "lieu_emission": 0.65,
    # Autres champs
    "nationalite": 0.6,
    "type_visa": 0.6,
    "type_titre": 0.6,
    "sexe": 0.55,
    "categories": 0.5,
    "restrictions": 0.4,
    "numero_acte": 0.4,
    "numero_principal": 0.5
}

def get_required_fields(doc_type: DocumentType) -> List[str]:
    """Retourne la liste des champs requis pour un type de document"""
    return REQUIRED_FIELDS.get(doc_type, [])

def get_optional_fields(doc_type: DocumentType) -> List[str]:
    """Retourne la liste des champs optionnels pour un type de document"""
    return OPTIONAL_FIELDS.get(doc_type, [])

def get_field_weight(field_name: str) -> float:
    """Retourne le poids de pondération d'un champ"""
    return FIELD_WEIGHTS.get(field_name, 0.5)  # Poids par défaut: 0.5

def get_all_fields(doc_type: DocumentType) -> List[str]:
    """Retourne tous les champs (requis + optionnels) pour un type de document"""
    required = get_required_fields(doc_type)
    optional = get_optional_fields(doc_type)
    return required + optional


def get_detection_number_patterns(doc_type: DocumentType) -> List[str]:
    """Retourne les motifs regex numeriques utilises pour la detection d'un document."""
    definition = DOCUMENT_DEFINITIONS.get(doc_type)
    return definition.detection_number_patterns if definition else []


def get_document_features(doc_type: DocumentType) -> List[str]:
    """Retourne les features metier exposees pour un type de document."""
    return DOCUMENT_FEATURES.get(doc_type, [])
