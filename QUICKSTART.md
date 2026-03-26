# 🚀 Démarrage Rapide - OCR Identity Extractor V2

## ⚡ Installation en 3 Minutes

### Méthode 1 : Avec Docker (Recommandé) 🐳

```bash
# 1. Cloner ou copier les fichiers
cd ocr-identity-v2/

# 2. Construire l'image Docker
docker-compose build

# 3. Démarrer l'API
docker-compose up -d

# 4. Vérifier que ça fonctionne
curl http://localhost:8000/health
```

**✅ C'est tout ! L'API est prête sur http://localhost:8000**

### Méthode 2 : Installation Locale (Sans Docker)

```bash
# 1. Créer un environnement virtuel
python -m venv venv
source venv/bin/activate  # Linux/Mac
# OU
venv\Scripts\activate     # Windows

# 2. Installer les dépendances
pip install -r requirements.txt

# 3. Lancer l'API
python main_v2.py
```

**✅ API prête sur http://localhost:8000**

---

## 📝 Premiers Tests

### Test 1 : Vérifier la Santé

```bash
curl http://localhost:8000/health
```

**Réponse attendue :**
```json
{
  "status": "healthy",
  "service": "ocr-identity-extractor-v2"
}
```

### Test 2 : Types de Documents Supportés

```bash
curl http://localhost:8000/supported-types
```

**Réponse :**
```json
{
  "success": true,
  "count": 6,
  "supported_types": [
    "Carte NINA (Mali)",
    "Carte d'Identité Nationale (Sénégal)",
    "Passeport Biométrique",
    ...
  ]
}
```

### Test 3 : Upload d'un Document

```bash
curl -X POST "http://localhost:8000/extract-identity" \
  -F "file=@votre_document.jpg"
```

**Réponse (exemple CIN Mali) :**
```json
{
  "success": true,
  "document": {
    "type": "CIN_MALI",
    "description": "Carte NINA (Mali)",
    "detection_confidence": 0.95
  },
  "extracted_data": {
    "numero": {
      "value": "123456789012",
      "confidence": 0.98
    },
    "nom": {
      "value": "TRAORE",
      "confidence": 0.95
    },
    "prenom": {
      "value": "Amadou",
      "confidence": 0.93
    }
  },
  "validation": {
    "is_valid": true,
    "global_score": 0.92
  }
}
```

---

## 📚 Documentation Interactive

Une fois l'API démarrée, visitez :

- **Swagger UI** : http://localhost:8000/docs
- **ReDoc** : http://localhost:8000/redoc

Vous pouvez tester directement les endpoints depuis l'interface !

---

## 🐳 Commandes Docker Essentielles

```bash
# Démarrer
docker-compose up -d

# Arrêter
docker-compose down

# Voir les logs
docker-compose logs -f

# Redémarrer
docker-compose restart

# Nettoyer
docker-compose down -v
```

**Avec Make (si installé) :**
```bash
make up      # Démarrer
make down    # Arrêter
make logs    # Voir les logs
make clean   # Nettoyer
```

---

## 🎯 Cas d'Usage Typiques

### Extraire une CIN Mali (NINA)

```bash
curl -X POST "http://localhost:8000/extract-identity" \
  -F "file=@cin_mali.jpg" \
  | jq .
```

### Extraire un Passeport Biométrique

```bash
curl -X POST "http://localhost:8000/extract-identity" \
  -F "file=@passeport.jpg" \
  | jq .
```

### Traitement Batch (Plusieurs Documents)

```bash
curl -X POST "http://localhost:8000/extract-batch" \
  -F "files=@doc1.jpg" \
  -F "files=@doc2.jpg" \
  -F "files=@doc3.jpg" \
  | jq .
```

### OCR Seulement (Sans Extraction)

```bash
curl -X POST "http://localhost:8000/ocr-only" \
  -F "file=@document.jpg" \
  | jq '.full_text'
```

---

## 🔧 Configuration Rapide

### Changer le Port

**Docker :**
```yaml
# docker-compose.yml
ports:
  - "9000:8000"  # Port 9000 au lieu de 8000
```

**Local :**
```python
# main_v2.py (ligne finale)
uvicorn.run(app, host="0.0.0.0", port=9000)
```

### Activer le GPU (pour performances)

```bash
# .env
USE_GPU=true

# Nécessite nvidia-docker
```

### Augmenter les Workers

```bash
# .env
MAX_WORKERS=8
```

---

## 🐛 Résolution Rapide de Problèmes

### Problème : "Port 8000 already in use"

```bash
# Trouver le processus
lsof -i :8000

# Tuer le processus
kill -9 <PID>

# OU changer le port dans docker-compose.yml
```

### Problème : "Container fails to start"

```bash
# Voir les logs d'erreur
docker-compose logs ocr-api

# Reconstruire sans cache
docker-compose build --no-cache
docker-compose up -d
```

### Problème : "Models not downloading"

```bash
# Supprimer le volume et relancer
docker volume rm ocr-paddle-models
docker-compose up -d
```

### Problème : "Out of memory"

```bash
# Augmenter la limite dans docker-compose.yml
deploy:
  resources:
    limits:
      memory: 6G  # Au lieu de 4G
```

---

## 📊 Performances Attendues

| Type Document | Précision | Temps Moyen |
|--------------|-----------|-------------|
| CIN Mali (NINA) | ~95% | 1.5-2s |
| Passeport MRZ | ~98% | 1.5-2s |
| CIN Sénégal | ~90% | 2-2.5s |
| CIN générique | ~75% | 2-3s |

---

## 🎓 Prochaines Étapes

1. **Lire la documentation complète** : `README.md`
2. **Comprendre l'architecture** : `GUIDE_MIGRATION.md`
3. **Apprendre Docker** : `DOCKER_GUIDE.md`
4. **Tester en production** : Voir section Production

---

## 📞 Besoin d'Aide ?

1. Vérifier les logs : `docker-compose logs -f`
2. Tester la santé : `curl http://localhost:8000/health`
3. Exécuter les tests : `./test-docker.sh`
4. Consulter : `DOCKER_GUIDE.md`

---

## ✨ Fonctionnalités Principales

- ✅ Détection automatique du type de document
- ✅ Extraction MRZ pour passeports (98% précision)
- ✅ Support NINA Mali (format 12 chiffres)
- ✅ Support multi-pays (Mali, Sénégal, Côte d'Ivoire, etc.)
- ✅ Preprocessing adaptatif par type
- ✅ Validation pondérée des champs
- ✅ API REST complète
- ✅ Documentation interactive
- ✅ Dockerisé et prêt pour production

---

**🎉 Bon développement avec OCR Identity Extractor V2 ! 🚀**
