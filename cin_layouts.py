from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


NormalizedZone = Tuple[float, float, float, float]
Point = Tuple[float, float]


@dataclass(frozen=True)
class CINLayoutTemplate:
    template_id: str
    country: str
    version: str
    detection_keywords: List[str]
    anchor_keywords: List[str] = field(default_factory=list)
    field_zones: Dict[str, NormalizedZone] = field(default_factory=dict)


CIN_LAYOUT_TEMPLATES: Dict[str, CINLayoutTemplate] = {
    "MALI_NINA_V1": CINLayoutTemplate(
        template_id="MALI_NINA_V1",
        country="MALI",
        version="NINA_V1",
        detection_keywords=["MALI", "NINA", "CARTENINA", "REPUBLIOUEDUMAL", "REPUBLIQUE"],
        anchor_keywords=["NINA", "CARTENINA", "MALI", "DELIVRE"],
        field_zones={
            "numero_id": (0.32, 0.14, 0.72, 0.30),
            "prenom": (0.34, 0.24, 0.58, 0.36),
            "nom": (0.34, 0.30, 0.58, 0.44),
            "date_naissance": (0.44, 0.34, 0.68, 0.52),
            "date_delivrance": (0.60, 0.88, 0.90, 1.00),
            "date_expiration": (0.65, 0.88, 0.98, 1.00),
        },
    ),
    # Calibre a partir de l'exemple OCR fourni (Carte d'identite CEDEAO - Mali).
    "MALI_CEDEAO_V1": CINLayoutTemplate(
        template_id="MALI_CEDEAO_V1",
        country="MALI",
        version="CEDEAO_V1",
        detection_keywords=["MALI", "REPUBLIQUE DU MALI", "CEDEAO", "IDENTITE"],
        anchor_keywords=["CARTE", "IDENTITE", "CEDEAO", "MALI"],
        field_zones={
            "numero_id": (0.22, 0.16, 0.50, 0.30),
            "prenom": (0.16, 0.28, 0.40, 0.40),
            "nom": (0.14, 0.38, 0.35, 0.50),
            "date_naissance": (0.58, 0.50, 0.82, 0.62),
            "date_delivrance": (0.16, 0.72, 0.38, 0.84),
            "date_expiration": (0.58, 0.72, 0.84, 0.84),
        },
    ),
    "MALI_GENERIC_V1": CINLayoutTemplate(
        template_id="MALI_GENERIC_V1",
        country="MALI",
        version="GENERIC_V1",
        detection_keywords=["MALI", "REPUBLIQUE DU MALI", "REPUBLIOUEDUMAL", "REPUBLIQUE"],
        anchor_keywords=["CARTE", "IDENTITE", "MALI"],
        field_zones={
            "numero_id": (0.08, 0.10, 0.58, 0.30),
            "nom": (0.40, 0.22, 0.95, 0.38),
            "prenom": (0.40, 0.34, 0.95, 0.50),
            "date_naissance": (0.40, 0.48, 0.78, 0.64),
            "date_delivrance": (0.08, 0.68, 0.46, 0.90),
            "date_expiration": (0.50, 0.68, 0.95, 0.90),
        },
    ),
    "SENEGAL_GENERIC_V1": CINLayoutTemplate(
        template_id="SENEGAL_GENERIC_V1",
        country="SENEGAL",
        version="GENERIC_V1",
        detection_keywords=["SENEGAL", "REPUBLIQUE DU SENEGAL", "IDENTITE"],
        anchor_keywords=["CARTE", "NATIONALE", "IDENTITE"],
        field_zones={
            "numero_id": (0.05, 0.12, 0.55, 0.30),
            "nom": (0.40, 0.20, 0.95, 0.35),
            "prenom": (0.40, 0.34, 0.95, 0.50),
            "date_naissance": (0.40, 0.48, 0.75, 0.62),
            "date_delivrance": (0.05, 0.70, 0.45, 0.88),
            "date_expiration": (0.50, 0.70, 0.95, 0.88),
        },
    ),
    "COTE_DIVOIRE_GENERIC_V1": CINLayoutTemplate(
        template_id="COTE_DIVOIRE_GENERIC_V1",
        country="COTE_DIVOIRE",
        version="GENERIC_V1",
        detection_keywords=["COTE D'IVOIRE", "COTE DIVOIRE", "IDENTITE"],
        anchor_keywords=["CARTE", "IDENTITE", "IVOIRE"],
        field_zones={
            "numero_id": (0.05, 0.10, 0.55, 0.28),
            "nom": (0.40, 0.20, 0.95, 0.35),
            "prenom": (0.40, 0.34, 0.95, 0.50),
            "date_naissance": (0.40, 0.48, 0.75, 0.62),
            "date_delivrance": (0.05, 0.70, 0.45, 0.88),
            "date_expiration": (0.50, 0.70, 0.95, 0.88),
        },
    ),
    "GUINEE_CEDEAO_V1": CINLayoutTemplate(
        template_id="GUINEE_CEDEAO_V1",
        country="GUINEE",
        version="CEDEAO_V1",
        detection_keywords=["GUINEE", "REPUBLIQUE DE GUINEE", "CEDEAO", "IDENTITE"],
        anchor_keywords=["CARTE", "IDENTITE", "CEDEAO", "ECOWAS", "GUINEE"],
        field_zones={
            "numero_id": (0.30, 0.80, 0.76, 0.93),
            "nom": (0.26, 0.18, 0.56, 0.34),
            "prenom": (0.26, 0.30, 0.62, 0.46),
            "date_naissance": (0.26, 0.44, 0.62, 0.60),
            "date_delivrance": (0.26, 0.56, 0.66, 0.72),
            "date_expiration": (0.26, 0.66, 0.66, 0.82),
        },
    ),
    "RWANDA_NID_V1": CINLayoutTemplate(
        template_id="RWANDA_NID_V1",
        country="RWANDA",
        version="NID_V1",
        detection_keywords=["RWANDA", "NATIONAL ID", "NATIONAL IDENTIFICATION", "INDANGAMUNTU"],
        anchor_keywords=["RWANDA", "NATIONAL", "IDENTIFICATION", "ID"],
        field_zones={
            "numero_id": (0.08, 0.12, 0.60, 0.30),
            "nom": (0.40, 0.22, 0.95, 0.38),
            "prenom": (0.40, 0.34, 0.95, 0.50),
            "date_naissance": (0.40, 0.48, 0.78, 0.64),
            "date_delivrance": (0.08, 0.68, 0.46, 0.88),
            "date_expiration": (0.50, 0.68, 0.95, 0.88),
        },
    ),
    "TUNISIA_CIN_V1": CINLayoutTemplate(
        template_id="TUNISIA_CIN_V1",
        country="TUNISIE",
        version="CIN_V1",
        detection_keywords=["TUNISIE", "TUNISIA", "REPUBLIC OF TUNISIA", "CARTE D'IDENTITE", "IDENTITE"],
        anchor_keywords=["TUNISIE", "TUNISIA", "CARTE", "IDENTITE"],
        field_zones={
            "numero_id": (0.08, 0.10, 0.62, 0.30),
            "nom": (0.36, 0.20, 0.95, 0.36),
            "prenom": (0.36, 0.34, 0.95, 0.50),
            "date_naissance": (0.36, 0.48, 0.80, 0.64),
            "date_delivrance": (0.08, 0.68, 0.46, 0.88),
            "date_expiration": (0.50, 0.68, 0.95, 0.88),
        },
    ),
    "BENIN_CEDEAO_V1": CINLayoutTemplate(
        template_id="BENIN_CEDEAO_V1",
        country="BENIN",
        version="CEDEAO_V1",
        detection_keywords=["BENIN", "REPUBLIQUE DU BENIN", "CEDEAO", "IDENTITE"],
        anchor_keywords=["CARTE", "IDENTITE", "CEDEAO", "BENIN"],
        field_zones={
            "numero_id": (0.08, 0.12, 0.58, 0.30),
            "nom": (0.40, 0.22, 0.95, 0.38),
            "prenom": (0.40, 0.34, 0.95, 0.50),
            "date_naissance": (0.40, 0.48, 0.78, 0.64),
            "date_delivrance": (0.08, 0.68, 0.46, 0.88),
            "date_expiration": (0.50, 0.68, 0.95, 0.88),
        },
    ),
    "BURKINA_CEDEAO_V1": CINLayoutTemplate(
        template_id="BURKINA_CEDEAO_V1",
        country="BURKINA_FASO",
        version="CEDEAO_V1",
        detection_keywords=["BURKINA", "BURKINA FASO", "CEDEAO", "IDENTITE"],
        anchor_keywords=["CARTE", "IDENTITE", "CEDEAO", "BURKINA"],
        field_zones={
            "numero_id": (0.08, 0.12, 0.58, 0.30),
            "nom": (0.40, 0.22, 0.95, 0.38),
            "prenom": (0.40, 0.34, 0.95, 0.50),
            "date_naissance": (0.40, 0.48, 0.78, 0.64),
            "date_delivrance": (0.08, 0.68, 0.46, 0.88),
            "date_expiration": (0.50, 0.68, 0.95, 0.88),
        },
    ),
    "NIGER_CEDEAO_V1": CINLayoutTemplate(
        template_id="NIGER_CEDEAO_V1",
        country="NIGER",
        version="CEDEAO_V1",
        detection_keywords=["NIGER", "REPUBLIQUE DU NIGER", "CEDEAO", "IDENTITE"],
        anchor_keywords=["CARTE", "IDENTITE", "CEDEAO", "NIGER"],
        field_zones={
            "numero_id": (0.08, 0.12, 0.58, 0.30),
            "nom": (0.40, 0.22, 0.95, 0.38),
            "prenom": (0.40, 0.34, 0.95, 0.50),
            "date_naissance": (0.40, 0.48, 0.78, 0.64),
            "date_delivrance": (0.08, 0.68, 0.46, 0.88),
            "date_expiration": (0.50, 0.68, 0.95, 0.88),
        },
    ),
    "TOGO_CEDEAO_V1": CINLayoutTemplate(
        template_id="TOGO_CEDEAO_V1",
        country="TOGO",
        version="CEDEAO_V1",
        detection_keywords=["TOGO", "REPUBLIQUE TOGOLAISE", "CEDEAO", "IDENTITE"],
        anchor_keywords=["CARTE", "IDENTITE", "CEDEAO", "TOGO"],
        field_zones={
            "numero_id": (0.08, 0.12, 0.58, 0.30),
            "nom": (0.40, 0.22, 0.95, 0.38),
            "prenom": (0.40, 0.34, 0.95, 0.50),
            "date_naissance": (0.40, 0.48, 0.78, 0.64),
            "date_delivrance": (0.08, 0.68, 0.46, 0.88),
            "date_expiration": (0.50, 0.68, 0.95, 0.88),
        },
    ),
    "GENERIC_CIN_V1": CINLayoutTemplate(
        template_id="GENERIC_CIN_V1",
        country="GENERIC",
        version="GENERIC_V1",
        detection_keywords=[],
        anchor_keywords=["CARTE", "IDENTITE", "ID"],
        field_zones={
            "numero_id": (0.05, 0.08, 0.60, 0.30),
            "nom": (0.35, 0.18, 0.95, 0.38),
            "prenom": (0.35, 0.32, 0.95, 0.52),
            "date_naissance": (0.35, 0.46, 0.80, 0.64),
            "date_delivrance": (0.05, 0.68, 0.45, 0.90),
            "date_expiration": (0.50, 0.68, 0.95, 0.90),
        },
    ),
}


def _text_match_stats(text: str, keywords: List[str]) -> Tuple[float, int]:
    if not keywords:
        return 0.0, 0
    matches = sum(1 for keyword in keywords if keyword and keyword in text)
    score = min(matches / max(len(keywords), 1), 1.0)
    return score, matches


def _point_in_zone(point: Point, zone: NormalizedZone) -> bool:
    x, y = point
    x1, y1, x2, y2 = zone
    return x1 <= x <= x2 and y1 <= y <= y2


def _distance_to_zone(point: Point, zone: NormalizedZone) -> float:
    x, y = point
    x1, y1, x2, y2 = zone

    dx = 0.0
    if x < x1:
        dx = x1 - x
    elif x > x2:
        dx = x - x2

    dy = 0.0
    if y < y1:
        dy = y1 - y
    elif y > y2:
        dy = y - y2

    return (dx * dx + dy * dy) ** 0.5


def _spatial_score(template: CINLayoutTemplate, field_centers: Dict[str, Point]) -> float:
    if not field_centers:
        return 0.0

    scores = []
    for field_name, center in field_centers.items():
        zone = template.field_zones.get(field_name)
        if zone is None:
            continue
        if _point_in_zone(center, zone):
            scores.append(1.0)
        else:
            distance = _distance_to_zone(center, zone)
            scores.append(max(0.0, 1.0 - (distance / 0.35)))

    if not scores:
        return 0.0
    return sum(scores) / len(scores)


def detect_cin_layout(full_text: str, field_centers: Optional[Dict[str, Point]] = None) -> Dict[str, object]:
    """Selectionne le template CIN (pays + version) le plus probable."""
    text = (full_text or "").upper()
    field_centers = field_centers or {}

    best_template = CIN_LAYOUT_TEMPLATES["GENERIC_CIN_V1"]
    best_score = -1.0

    # Weights: texte pays (35%), ancres visuelles (25%), fit spatial bbox (40%).
    for template in CIN_LAYOUT_TEMPLATES.values():
        country_score, country_hits = _text_match_stats(text, template.detection_keywords)
        anchor_score, anchor_hits = _text_match_stats(text, template.anchor_keywords)
        spatial_score = _spatial_score(template, field_centers)

        specificity_bonus = 0.0
        if template.country != "GENERIC" and len(template.detection_keywords) >= 4 and country_hits >= 3:
            specificity_bonus += 0.08
        if "CEDEAO" in text and "CEDEAO" in " ".join(template.detection_keywords):
            specificity_bonus += 0.06

        total = (country_score * 0.33) + (anchor_score * 0.24) + (spatial_score * 0.37) + specificity_bonus
        if total > best_score:
            best_score = total
            best_template = template

    return {
        "template_id": best_template.template_id,
        "country": best_template.country,
        "version": best_template.version,
        "score": round(max(0.0, min(1.0, best_score)), 4),
    }


def get_zone(template_id: str, field_name: str) -> Optional[NormalizedZone]:
    template = CIN_LAYOUT_TEMPLATES.get(template_id) or CIN_LAYOUT_TEMPLATES["GENERIC_CIN_V1"]
    return template.field_zones.get(field_name)
