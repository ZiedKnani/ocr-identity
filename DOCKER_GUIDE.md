# 🐳 Guide Docker - OCR Identity Extractor V2

## 📋 Prérequis

- **Docker** : Version 20.10+
- **Docker Compose** : Version 2.0+
- **Make** (optionnel) : Pour utiliser le Makefile

### Installation Docker

**Linux (Ubuntu/Debian) :**
```bash
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER
```

**macOS :**
```bash
brew install --cask docker
```

**Windows :**
Télécharger [Docker Desktop](https://www.docker.com/products/docker-desktop)

Vérifier l'installation :
```bash
docker --version
docker-compose --version
```

## 🚀 Démarrage Rapide

### Option 1 : Avec Make (Recommandé)

```bash
# Voir toutes les commandes disponibles
make help

# Construire l'image
make build

# Démarrer les services
make up

# Voir les logs
make logs
```

### Option 2 : Avec Docker Compose

```bash
# Construire l'image
docker-compose build

# Démarrer les services
docker-compose up -d

# Voir les logs
docker-compose logs -f
```

### Option 3 : Docker simple

```bash
# Construire l'image
docker build -t ocr-identity-extractor:2.0.0 .

# Démarrer le conteneur
docker run -d -p 8000:8000 --name ocr-api ocr-identity-extractor:2.0.0

# Voir les logs
docker logs -f ocr-api
```

## 📁 Structure des Fichiers Docker

```
votre-projet/
├── Dockerfile              # Configuration de l'image
├── docker-compose.yml      # Orchestration des services
├── .dockerignore          # Fichiers à exclure
├── .env.example           # Variables d'environnement exemple
├── nginx.conf             # Configuration Nginx (optionnel)
├── Makefile               # Commandes simplifiées
└── logs/                  # Dossier pour les logs (créé auto)
```

## ⚙️ Configuration

### 1. Variables d'Environnement

Copier le fichier exemple :
```bash
cp .env.example .env
```

Éditer `.env` :
```bash
# Configuration de base
LOG_LEVEL=INFO
OCR_LANGUAGE=fr
MAX_WORKERS=4

# Configuration serveur
API_HOST=0.0.0.0
API_PORT=8000

# PaddleOCR
USE_GPU=false
PADDLE_USE_ANGLE_CLS=true

# Limites
MAX_FILE_SIZE_MB=10
MAX_BATCH_SIZE=10
```

### 2. Ressources Docker

Modifier dans `docker-compose.yml` :
```yaml
deploy:
  resources:
    limits:
      cpus: '2.0'      # Max 2 CPU
      memory: 4G       # Max 4 GB RAM
    reservations:
      cpus: '1.0'      # Min 1 CPU
      memory: 2G       # Min 2 GB RAM
```

### 3. Ports

Par défaut : `8000`

Pour changer :
```yaml
# docker-compose.yml
ports:
  - "9000:8000"  # Port 9000 sur la machine hôte
```

## 🔧 Utilisation

### Démarrer l'API

```bash
make up
# ou
docker-compose up -d
```

**Accès :**
- API : http://localhost:8000
- Documentation : http://localhost:8000/docs
- Redoc : http://localhost:8000/redoc

### Tester l'API

```bash
# Avec Make
make test

# Avec curl
curl http://localhost:8000/health

# Upload d'un document
curl -X POST "http://localhost:8000/extract-identity" \
  -F "file=@/chemin/vers/document.jpg"
```

### Voir les Logs

```bash
# Logs en temps réel
make logs

# Tous les services
make logs-all

# Dernières 100 lignes
docker-compose logs --tail=100
```

### Redémarrer

```bash
make restart
# ou
docker-compose restart
```

### Arrêter

```bash
make down
# ou
docker-compose down
```

## 🔍 Debug et Maintenance

### Ouvrir un Shell dans le Conteneur

```bash
make shell
# ou
docker-compose exec ocr-api /bin/bash
```

### Vérifier la Santé du Service

```bash
make health
# ou
docker inspect --format='{{.State.Health.Status}}' ocr-identity-api
```

### Voir les Statistiques

```bash
make stats
# ou
docker stats
```

### Lister les Conteneurs

```bash
make ps
# ou
docker-compose ps
```

## 🧹 Nettoyage

### Nettoyage Simple

```bash
make clean
# Arrête les conteneurs et supprime les volumes
```

### Nettoyage Complet

```bash
make clean-all
# Supprime tout : conteneurs, volumes, images
```

### Supprimer les Images Non Utilisées

```bash
make prune
```

## 📦 Volumes Docker

### Volumes Créés

1. **paddle-models** : Cache des modèles PaddleOCR
2. **logs** : Logs de l'application

### Sauvegarder les Modèles

```bash
make backup-models
# Crée un backup dans ./backups/
```

### Restaurer les Modèles

```bash
make restore-models FILE=paddle-models-backup-20250212-153000.tar.gz
```

### Lister les Volumes

```bash
docker volume ls | grep ocr
```

### Supprimer un Volume

```bash
docker volume rm ocr-paddle-models
```

## 🌐 Mode Production avec Nginx

### Démarrer avec Nginx

```bash
make prod-up
# ou
docker-compose --profile production up -d
```

**Accès :**
- HTTP : http://localhost
- HTTPS : https://localhost (si SSL configuré)

### Configuration SSL

1. Générer des certificats :
```bash
mkdir ssl
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout ssl/key.pem -out ssl/cert.pem
```

2. Décommenter la section HTTPS dans `nginx.conf`

3. Redémarrer :
```bash
docker-compose --profile production restart nginx
```

## 🚀 Optimisations

### 1. Build avec Cache

```bash
docker-compose build --no-cache  # Sans cache
docker-compose build --pull      # Avec dernières images
```

### 2. Limiter la Taille de l'Image

L'image utilise déjà `python:3.10-slim` (optimisée).

Taille approximative : **~2 GB** (à cause de PaddleOCR et OpenCV)

### 3. Multi-stage Build (Avancé)

Pour réduire davantage, modifier le Dockerfile :
```dockerfile
# Stage 1: Builder
FROM python:3.10 as builder
RUN pip install --user -r requirements.txt

# Stage 2: Runtime
FROM python:3.10-slim
COPY --from=builder /root/.local /root/.local
# ...
```

## 📊 Monitoring

### Logs Structurés

Modifier `main_v2.py` pour JSON logging :
```python
import logging.config
logging.basicConfig(
    format='{"time":"%(asctime)s","level":"%(levelname)s","msg":"%(message)s"}',
    level=logging.INFO
)
```

### Prometheus Metrics (Optionnel)

Ajouter dans `requirements.txt` :
```
prometheus-client==0.19.0
```

Ajouter dans `main_v2.py` :
```python
from prometheus_client import make_asgi_app

metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)
```

## 🔐 Sécurité

### 1. Utilisateur Non-Root

Déjà configuré dans le Dockerfile :
```dockerfile
USER ocruser
```

### 2. Limiter les Ressources

Déjà configuré dans `docker-compose.yml`

### 3. Réseau Isolé

Le service utilise un réseau bridge personnalisé.

### 4. Secrets (pour Production)

Utiliser Docker secrets :
```yaml
secrets:
  db_password:
    file: ./secrets/db_password.txt

services:
  ocr-api:
    secrets:
      - db_password
```

## 🐛 Troubleshooting

### Problème : Conteneur ne démarre pas

```bash
# Voir les logs d'erreur
docker-compose logs ocr-api

# Vérifier la santé
docker inspect ocr-identity-api
```

### Problème : Port déjà utilisé

```bash
# Trouver le process
lsof -i :8000

# Changer le port dans docker-compose.yml
ports:
  - "9000:8000"
```

### Problème : Erreur de mémoire

Augmenter la limite :
```yaml
deploy:
  resources:
    limits:
      memory: 6G  # Au lieu de 4G
```

### Problème : Modèles PaddleOCR non téléchargés

```bash
# Supprimer le volume et relancer
docker volume rm ocr-paddle-models
docker-compose up -d
```

### Problème : Performance lente

1. Activer GPU si disponible :
```bash
# Modifier .env
USE_GPU=true

# Installer nvidia-docker
# https://github.com/NVIDIA/nvidia-docker
```

2. Augmenter les workers :
```bash
# .env
MAX_WORKERS=8
```

## 📚 Commandes Utiles

```bash
# Reconstruire sans cache
docker-compose build --no-cache

# Forcer la recréation des conteneurs
docker-compose up -d --force-recreate

# Suivre les logs d'un service spécifique
docker-compose logs -f ocr-api

# Exécuter une commande dans le conteneur
docker-compose exec ocr-api python -c "print('Hello')"

# Voir les variables d'environnement
docker-compose exec ocr-api env

# Copier un fichier depuis le conteneur
docker cp ocr-identity-api:/app/logs/app.log ./

# Inspecter le réseau
docker network inspect ocr-network
```

## 🎓 Best Practices

1. **Toujours utiliser des versions spécifiques** dans requirements.txt
2. **Ne pas stocker de secrets** dans le Dockerfile ou docker-compose.yml
3. **Utiliser .dockerignore** pour exclure les fichiers inutiles
4. **Tagger vos images** avec des versions
5. **Surveiller les ressources** avec `docker stats`
6. **Nettoyer régulièrement** avec `make clean`
7. **Sauvegarder les volumes** importants

## 📞 Support

En cas de problème :
1. Vérifier les logs : `make logs`
2. Vérifier la santé : `make health`
3. Redémarrer : `make restart`
4. Nettoyer et reconstruire : `make clean && make build && make up`

---

**Bonne utilisation de Docker ! 🐳**
