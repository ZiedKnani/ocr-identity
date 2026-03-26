# Dockerfile pour OCR Identity Extractor V2

# Image de base Python 3.10
FROM python:3.10-slim

# Métadonnées
LABEL maintainer="OCR Identity Team"
LABEL version="2.0.0"
LABEL description="OCR service pour extraction de données d'identité"

# Variables d'environnement
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Installer les dépendances système pour OpenCV et PaddleOCR
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    libgomp1 \
    libgl1 \
    libglib2.0-0 \
    wget \
    curl \
    ca-certificates \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Créer un utilisateur non-root pour sécurité
RUN useradd -m -u 1000 ocruser && \
    mkdir -p /app && \
    chown -R ocruser:ocruser /app

# Définir le répertoire de travail
WORKDIR /app

# Copier requirements.txt en premier (pour cache Docker)
COPY --chown=ocruser:ocruser requirements.txt .

# Installer les dépendances Python
RUN pip install --no-cache-dir -r requirements.txt

# Copier le code de l'application
COPY --chown=ocruser:ocruser document_types.py .
COPY --chown=ocruser:ocruser document_detector.py .
COPY --chown=ocruser:ocruser mrz_parser.py .
COPY --chown=ocruser:ocruser document_strategy.py .
COPY --chown=ocruser:ocruser cin_layouts.py .
COPY --chown=ocruser:ocruser ocr_processor.py .
COPY --chown=ocruser:ocruser validator.py .
COPY --chown=ocruser:ocruser id_processor_v2.py .
COPY --chown=ocruser:ocruser main_v2.py .

# Créer les répertoires pour les modèles PaddleOCR (cache)
RUN mkdir -p /home/ocruser/.paddleocr && \
    chown -R ocruser:ocruser /home/ocruser/.paddleocr

# Changer vers l'utilisateur non-root
USER ocruser

# Exposer le port
EXPOSE 8000

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Commande de démarrage
CMD ["python", "main_v2.py"]
