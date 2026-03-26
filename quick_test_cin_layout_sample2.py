import json

from document_types import DocumentType
from document_strategy import DocumentStrategy

blocks = [
    {"id": 0, "text": "REPUBLIOUEDUMAL", "confidence": 0.861, "bbox": [[308, 45], [712, 50], [712, 73], [308, 68]], "label": "UNLABELED"},
    {"id": 1, "text": "CARTENINA", "confidence": 0.995, "bbox": [[405, 97], [636, 100], [636, 126], [405, 123]], "label": "UNLABELED"},
    {"id": 2, "text": "18306101999099K", "confidence": 0.993, "bbox": [[427, 151], [704, 153], [703, 176], [427, 173]], "label": "UNLABELED"},
    {"id": 3, "text": "Abdoulaye", "confidence": 0.994, "bbox": [[457, 184], [586, 189], [585, 215], [456, 210]], "label": "UNLABELED"},
    {"id": 4, "text": "HAIDARA", "confidence": 0.997, "bbox": [[459, 219], [580, 219], [580, 242], [459, 242]], "label": "UNLABELED"},
    {"id": 5, "text": "05/04/1983", "confidence": 0.981, "bbox": [[525, 251], [660, 251], [660, 274], [525, 274]], "label": "UNLABELED"},
    {"id": 6, "text": "Fombouctou", "confidence": 0.973, "bbox": [[532, 283], [677, 283], [677, 306], [532, 306]], "label": "UNLABELED"},
    {"id": 7, "text": "AliouHaidara", "confidence": 0.985, "bbox": [[426, 316], [591, 319], [591, 342], [426, 339]], "label": "UNLABELED"},
    {"id": 8, "text": "Dioumawoye.Maiga", "confidence": 0.946, "bbox": [[427, 351], [669, 351], [669, 377], [427, 377]], "label": "UNLABELED"},
    {"id": 9, "text": "essior", "confidence": 0.864, "bbox": [[396, 384], [438, 384], [438, 400], [396, 400]], "label": "UNLABELED"},
    {"id": 10, "text": "Ouvrier EtAssim.", "confidence": 0.966, "bbox": [[459, 384], [676, 380], [676, 406], [459, 410]], "label": "UNLABELED"},
    {"id": 11, "text": "Domicile", "confidence": 0.991, "bbox": [[358, 416], [433, 416], [433, 435], [358, 435]], "label": "UNLABELED"},
    {"id": 12, "text": "ParisAmb)", "confidence": 0.981, "bbox": [[457, 428], [609, 425], [610, 455], [457, 459]], "label": "UNLABELED"},
    {"id": 13, "text": "Empreinte", "confidence": 0.99, "bbox": [[356, 485], [443, 481], [444, 499], [357, 503]], "label": "UNLABELED"},
    {"id": 14, "text": "dieitale", "confidence": 0.797, "bbox": [[360, 505], [414, 505], [414, 521], [360, 521]], "label": "UNLABELED"},
    {"id": 15, "text": "Delivrele01/05/2015", "confidence": 0.974, "bbox": [[613, 576], [827, 572], [827, 594], [614, 597]], "label": "UNLABELED"},
]

extracted = DocumentStrategy.extract(DocumentType.ID_CARD, blocks)

summary = {}
for field in ["numero_id", "prenom", "nom", "date_naissance", "date_delivrance", "date_expiration"]:
    if field in extracted and isinstance(extracted[field], dict):
        loc = extracted[field].get("location", {})
        summary[field] = {
            "value": extracted[field].get("value"),
            "method": extracted[field].get("method"),
            "template_id": loc.get("template_id"),
            "country": loc.get("country_template"),
            "version": loc.get("layout_version"),
            "template_score": loc.get("template_score"),
            "in_expected_zone": loc.get("in_expected_zone"),
            "center": loc.get("center"),
        }

print(json.dumps(summary, ensure_ascii=False, indent=2))
