import json

from document_types import DocumentType
from document_strategy import DocumentStrategy

blocks = [
    {"id": 0, "text": "REPUBLIQUE DU MALI", "confidence": 0.946, "bbox": [[147, 73], [345, 74], [345, 91], [147, 90]], "label": "UNLABELED"},
    {"id": 1, "text": "CARTEDIDENTITECEDEAO", "confidence": 0.974, "bbox": [[180, 96], [314, 96], [314, 106], [180, 106]], "label": "UNLABELED"},
    {"id": 2, "text": "CCOEA", "confidence": 0.771, "bbox": [[313, 106], [343, 106], [343, 116], [313, 116]], "label": "UNLABELED"},
    {"id": 3, "text": "19004708001065P", "confidence": 0.951, "bbox": [[202, 118], [332, 116], [332, 130], [203, 132]], "label": "UNLABELED"},
    {"id": 4, "text": "FATOUMATA", "confidence": 0.947, "bbox": [[200, 144], [280, 144], [280, 158], [200, 158]], "label": "UNLABELED"},
    {"id": 5, "text": "MAIGA", "confidence": 0.948, "bbox": [[196, 167], [247, 167], [247, 185], [196, 185]], "label": "UNLABELED"},
    {"id": 6, "text": "SexelSer", "confidence": 0.769, "bbox": [[196, 184], [245, 184], [245, 195], [196, 195]], "label": "UNLABELED"},
    {"id": 7, "text": "MALIENNE", "confidence": 0.988, "bbox": [[251, 195], [307, 195], [307, 206], [251, 206]], "label": "UNLABELED"},
    {"id": 8, "text": "01/01/2003", "confidence": 0.983, "bbox": [[339, 191], [407, 193], [407, 210], [338, 208]], "label": "UNLABELED"},
    {"id": 9, "text": "BAMAKO", "confidence": 0.98, "bbox": [[197, 220], [245, 220], [245, 230], [197, 230]], "label": "UNLABELED"},
    {"id": 10, "text": "RUOF", "confidence": 0.506, "bbox": [[201, 211], [228, 211], [228, 218], [201, 218]], "label": "UNLABELED"},
    {"id": 11, "text": "0", "confidence": 0.692, "bbox": [[469, 221], [482, 221], [482, 238], [469, 238]], "label": "UNLABELED"},
    {"id": 12, "text": "2/01/2023", "confidence": 0.934, "bbox": [[201, 244], [263, 244], [263, 258], [201, 258]], "label": "UNLABELED"},
    {"id": 13, "text": "12/01/2028", "confidence": 0.9, "bbox": [[343, 243], [407, 243], [407, 260], [343, 260]], "label": "UNLABELED"},
    {"id": 14, "text": "03", "confidence": 0.975, "bbox": [[430, 292], [443, 292], [443, 305], [430, 305]], "label": "UNLABELED"},
]

extracted = DocumentStrategy.extract(DocumentType.ID_CARD, blocks)

summary = {}
for field in ["numero_id", "prenom", "nom", "date_naissance", "date_delivrance", "date_expiration"]:
    if field in extracted and isinstance(extracted[field], dict):
        loc = extracted[field].get("location", {})
        summary[field] = {
            "value": extracted[field].get("value"),
            "template_id": loc.get("template_id"),
            "country": loc.get("country_template"),
            "version": loc.get("layout_version"),
            "template_score": loc.get("template_score"),
            "in_expected_zone": loc.get("in_expected_zone"),
            "center": loc.get("center"),
        }

print(json.dumps(summary, ensure_ascii=False, indent=2))
