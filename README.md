# 🎫 OCR Identity Extractor v2

> **Extraction intelligente de données d'identité à partir de documents OCR**

Plateforme automatisée pour extraire et labelliser des informations personnelles (nom, dates, numéro de pièce) de documents d'identité scannés via OCR avec haute précision.

---

## ✨ Fonctionnalités

### 🔍 **Extraction Multi-Document**
- **Passeports** : Extraction MRZ + récupération de noms et dates
- **Cartes d'Identité (CIN)** : Détection de zones, parsing de structures
- **Documents génériques** : Fallback intelligent pour formats non-standard

### 📅 **Extraction de Dates Robuste**
- Support de **15+ formats** de dates (DD/MM/YYYY, DDMMYYYY, DD/MMY, compacts, etc.)
- **Gestion des variantes OCR** : A0UT→AOUT, 0CT→OCT, années 2 chiffres (00-29→2000-2029)
- **Validation chronologique** : date_naissance ≤ date_delivrance ≤ date_expiration

### 👤 **Validation Intelligente de Noms**
- Rejet automatique des artefacts OCR (strings alphanumérique, marqueurs MRZ)
- 4 niveaux de filtrage : longueur, caractères, tokens interdits, ratio alphabétique
- Reconnaissance multilingue (français, anglais, caractères spéciaux)

### 🎯 **API FastAPI**
- Endpoints REST simples et documentés
- Support upload d'images ou envoi de texte OCR brut
- Réponses JSON structurées

---

## 🚀 Démarrage Rapide

### Avec Docker (recommandé)

```bash
# 1. Cloner le repo
git clone https://github.com/ZiedKnani/ocr-identity.git
cd ocr-identity

# 2. Lancer l'image Docker
docker-compose up -d

# 3. Vérifier que le service tourne
curl http://localhost:8000/health

# 4. Encoder une image en base64
python -c "import base64; print(base64.b64encode(open('test_images/sample.jpg', 'rb').read()).decode())" > img_b64.txt

# 5. Envoyer une requête
curl -X POST http://localhost:8000/extract \
  -H "Content-Type: application/json" \
  -d '{
    "ocr_text": "REPUBLIQUE DE GUINEE PASSEPORT...",
    "document_type": "PASSPORT"
  }'
```

### Localement (dev)

```bash
# 1. Setup environment
python -m venv .venv
source .venv/Scripts/Activate  # Windows
source .venv/bin/activate       # Linux/Mac

# 2. Install dependencies
pip install -r requirements.txt
python -m spacy download fr_core_news_sm  # Pour NLP

# 3. Run API
python main_v2.py

# 4. Test
curl http://localhost:8000/health
```

---

## 📊 Architecture

```
┌──────────────────────────────────────┐
│         FastAPI Server               │
│      (main_v2.py → 8000)             │
└──────────────────┬───────────────────┘
                   │
    ┌──────────────┼──────────────┬──────────────┐
    ▼              ▼              ▼              ▼
┌─────────┐  ┌──────────┐  ┌──────────────┐  ┌───────────┐
│  OCR    │  │  Doc     │  │  MRZ         │  │ Document  │
│ Processor│  │ Detector │  │ Parser       │  │ Strategy  │
└────┬────┘  └────┬─────┘  └──────┬───────┘  └─────┬─────┘
     │            │               │               │
     └────────────┴───────────────┴───────────────┘
                   │
      ┌────────────┼────────────┐
      ▼            ▼            ▼
  ┌────────┐  ┌──────────┐  ┌──────────────┐
  │ Names  │  │ Dates    │  │ ID Numbers   │
  │ (NER)  │  │ (Regex)  │  │ (Pattern)    │
  └────┬───┘  └────┬─────┘  └──────┬───────┘
       │           │               │
       └───────────┴───────────────┘
               │
               ▼
          ┌─────────────┐
          │ Validation  │
          │ + Fallback  │
          └──────┬──────┘
                 │
                 ▼
          ┌─────────────┐
          │ JSON Result │
          └─────────────┘
```

---

## 📁 Structure du Projet

```
ocr-identity-v2/
├── main_v2.py                      # Point d'entrée API FastAPI
├── document_strategy.py             # 🔑 Extraction multi-type (core)
├── document_types.py                # Énumération des types
├── document_detector.py             # Détection du type de document
├── mrz_parser.py                    # Parsing MRZ (Machine Readable Zone)
├── ocr_processor.py                 # Pipeline PaddleOCR
├── id_processor_v2.py               # Traitement IDs génériques
├── validator.py                     # Validation des données
├── cin_layouts.py                   # Layouts CIN pour parsing
│
├── Dockerfile                       # Image Docker
├── docker-compose.yml               # Config prod/dev
├── requirements.txt                 # Dépendances Python
│
├── test_images/                     # Images d'exemple
├── logs/                            # Logs de l'application
│
└── docs/                            # Documentation
```

---

## 🔧 Configuration

### Variables d'Environnement

```env
# .env
LOG_LEVEL=INFO                       # DEBUG, INFO, WARNING
MAX_WORKERS=4                        # Workers pour traitement parallèle
OCR_LANGUAGE=fr                      # Langue OCR (fr, en, etc.)
PYTHONUNBUFFERED=1                   # Logs en temps réel
```

### Docker Compose

```yaml
# docker-compose.yml
services:
  ocr-api:
    image: your-username/ocr-identity:2.0.0
    ports:
      - "8000:8000"
    environment:
      LOG_LEVEL: INFO
      MAX_WORKERS: 4
    volumes:
      - ./logs:/app/logs
      - ./test_images:/app/test_images:ro
```

---

## 📡 API Endpoints

### `POST /extract`

Extrait les données d'une image ou texte OCR.

**Request:**
```json
{
  "ocr_text": "REPUBLIQUE DE GUINEE PASSEPORT...",
  "document_type": "PASSPORT",
  "confidence_threshold": 0.65
}
```

**Response:**
```json
{
  "case_id": "PER1001D000000001",
  "document_type": "PASSPORT",
  "numero_id": {
    "value": "000123456",
    "confidence": 0.95
  },
  "nom": {
    "value": "DIALLO",
    "confidence": 0.90
  },
  "prenom": {
    "value": "AMADOU",
    "confidence": 0.88
  },
  "date_naissance": {
    "value": "1992-05-15",
    "confidence": 0.92
  },
  "date_delivrance": {
    "value": "2020-03-10",
    "confidence": 0.95
  },
  "date_expiration": {
    "value": "2030-03-10",
    "confidence": 0.95
  },
  "extraction_status": "SUCCESS",
  "errors": []
}
```

### `GET /health`

Vérifie que le service est opérationnel.

**Response:**
```json
{
  "status": "OK",
  "timestamp": "2026-04-01T10:30:00Z"
}
```

---

## 🎯 Formats Supportés

### Dates Extraites

| Format | Exemple | Détection |
|--------|---------|-----------|
| Standard | 15/05/1992 | ✅ |
| Compact | 15051992 | ✅ |
| Texte | 15 MAI 1992 | ✅ |
| Texte court | 15 MAY 92 | ✅ |
| Noisy OCR | 15/051992 | ✅ |
| Month abbr | 15MAY1992 | ✅ |
| 2-digit year | 15/05/92 | ✅ → 1992 |

### Noms & Prénoms

- Caractères latins + accents (é, è, ê, à, ç, etc.)
- Caractères spéciaux autorisés : `-`, `'`, ` ` (tiret, apostrophe, espace)
- Rejet automatique : nombres, MRZ markers (`<`, `/`), tokens non-nominaux

---

## 🧪 Tests

```bash
# Extraction simple
python -c "
from document_strategy import DocumentStrategy
text = open('test_images/sample_ocr.txt').read()
result = DocumentStrategy._extract_passport([{'id': 1, 'text': text, 'confidence': 0.95}])
print(result)
"

# Test API
python test_api.py
```

---

## 📈 Améliorations Apportées

### v2.0 (Current)
- ✅ Date extraction robuste (15+ formats)
- ✅ OCR noise handling (A0UT → AOUT)
- ✅ 2-digit year normalization
- ✅ Name validation avec 4 niveaux de filtrage
- ✅ Chronological date assignment
- ✅ FastAPI async endpoints

### Roadmap v2.1
- 🔄 spaCy NLP fallback pour noms non-détectés
- 🔄 GLiNER pour extraction DATE/PERSON améliorée
- 🔄 Ollama local LLM pour cas extrêmes
- 🔄 Dashboard web pour monitoring

---

## 🐛 Troubleshooting

| Problème | Solution |
|----------|----------|
| `Module not found: spacy` | `pip install -r requirements.txt` |
| PORT 8000 already in use | `docker-compose down` puis restart |
| PaddleOCR downloads slowly | Normal (modèles ~500MB), usage cache après |
| Dates not extracted | Vérifiez le format OCR (regex patterns) |
| Noms vides malgré OCR | Validation trop stricte, voir `_is_plausible_person_name()` |

---

## 🤝 Contribution

Les contributions sont bienvenues!

```bash
# 1. Fork the repo
# 2. Create feature branch
git checkout -b feature/amazing-feature

# 3. Commit changes
git commit -m "Add amazing feature"

# 4. Push to branch
git push origin feature/amazing-feature

# 5. Open Pull Request
```

---

## ⚖️ License

MIT License - Voir [LICENSE](LICENSE) pour détails.

---

## 📧 Support

**Questions? Issues?**
- 📌 Ouvrir une [GitHub Issue](https://github.com/ZiedKnani/ocr-identity/issues)
- 💬 Discussions: [GitHub Discussions](https://github.com/ZiedKnani/ocr-identity/discussions)

---

## 🎓 Références Techniques

- **PaddleOCR**: https://github.com/PaddlePaddle/PaddleOCR
- **FastAPI**: https://fastapi.tiangolo.com/
- **MRZ Parser**: ISO/IEC 7501-1 standard
- **spaCy NER**: https://spacy.io/

---

<div align="center">

**Fait avec ❤️ par l'équipe OCR Identity**

[⬆ back to top](#-ocr-identity-extractor-v2)

</div>
