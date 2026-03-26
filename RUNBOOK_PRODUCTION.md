# Runbook Production - OCR Identity Extractor V2

## 1. Objectif

Ce document decrit les operations d exploitation du service OCR en environnement de production: demarrage, supervision, incidents, release, et rollback.

## 2. Perimetre

Composants couverts:

- API FastAPI dans [main_v2.py](main_v2.py)
- Pipeline metier dans [id_processor_v2.py](id_processor_v2.py)
- Deploiement Docker dans [Dockerfile](Dockerfile) et [docker-compose.yml](docker-compose.yml)

## 3. Prerequis

- Docker fonctionnel.
- Ports ouverts (8000 pour API, 80/443 si proxy nginx actif).
- Stockage persistant pour cache OCR.
- Acces aux logs applicatifs.

## 4. Commandes standard

### 4.1 Build image

```powershell
docker build -t ocr-identity-v2:local .
```

### 4.2 Run local standard

```powershell
docker rm -f ocr-identity-api
docker run --rm -d -p 8000:8000 --name ocr-identity-api -v "C:\Users\PC:/host" -v ocr-paddle-cache:/home/ocruser/.paddleocr ocr-identity-v2:local
```

### 4.3 Verification service

```powershell
Invoke-RestMethod -Uri 'http://localhost:8000/health' -Method Get | ConvertTo-Json -Depth 5
```

## 5. Sondes et checks

### 5.1 Endpoint sante

- Route: GET /health
- Critere OK: status=healthy, processor_initialized=true

### 5.2 Endpoint capacites

- Route: GET /supported-types
- Critere OK: liste non vide, count coherent

### 5.3 Probe fonctionnelle minimale

- Route: POST /ocr-only
- Attendu: success=true, blocks non vides pour image test valide

## 6. SLO proposes

- Disponibilite API: 99.5%
- Latence P95 extraction simple: <= 4s
- Taux erreur technique (5xx): < 1%

## 7. Procedure de release

1. Verifier branche et artefacts.
2. Lancer tests de non regression.
3. Build image candidate.
4. Demarrer conteneur candidate.
5. Executer smoke tests API.
6. Basculer trafic.
7. Monitorer 30 min.

## 8. Procedure rollback

Declenchement:

- hausse anormale erreurs 5xx,
- regression extraction critique,
- latence hors SLO continue.

Actions:

1. Stop instance courante.
2. Redemarrer image precedente taggee stable.
3. Rejouer smoke tests.
4. Ouvrir incident et freeze release.

## 9. Incidents frequents et remediation

### 9.1 Fichier introuvable sur endpoint path

Symptome:

- erreur 404 sur documentPath Windows brut.

Cause:

- chemin non resolu dans conteneur Linux.

Action:

- utiliser un chemin de type /host/... si volume -v C:\Users\PC:/host est monte.

### 9.2 Service unhealthy au boot

Actions:

- verifier logs conteneur,
- verifier dependances OCR,
- verifier volume cache PaddleOCR,
- redemarrer avec image reconstruite.

### 9.3 Regressions dates (delivrance/expiration)

Actions:

- executer cas de regression connus,
- verifier priorite extraction context label,
- verifier fallback chronologique.

## 10. Observabilite recommandee

- Logs JSON structures.
- Correlation ID par requete.
- Metriques:
  - latence par endpoint,
  - taux succes extraction,
  - taux champs requis manquants,
  - score moyen par type documentaire.

## 11. Securite et conformite

- Exectuer le conteneur en non-root (deja en place).
- Eviter de loguer donnees personnelles en clair.
- Limiter retention des traces OCR selon politique.
- Chiffrer transport en production (reverse proxy TLS).

## 12. Checklists

### 12.1 Checklist pre-production

- [ ] Build reproductible
- [ ] Healthcheck OK
- [ ] Supported-types OK
- [ ] Smoke test extraction OK
- [ ] Logs exploitables
- [ ] Plan rollback valide

### 12.2 Checklist post-deploiement

- [ ] Erreurs 5xx stables
- [ ] Latence P95 stable
- [ ] Scores extraction dans la plage attendue
- [ ] Aucun incident securite

## 13. References

- [DOCUMENTATION_TECHNIQUE.md](DOCUMENTATION_TECHNIQUE.md)
- [main_v2.py](main_v2.py)
- [id_processor_v2.py](id_processor_v2.py)
- [document_strategy.py](document_strategy.py)
- [Dockerfile](Dockerfile)
- [docker-compose.yml](docker-compose.yml)

## 14. Procedure d introduction d un nouveau type/pays

Objectif: eviter les regressions lors des extensions fonctionnelles.

Etapes exploitation + validation:

1. Verifier que les definitions sont ajoutees dans [document_types.py](document_types.py).
2. Verifier la detection dans [document_detector.py](document_detector.py).
3. Verifier les regles d extraction dans [document_strategy.py](document_strategy.py).
4. Si CIN pays: verifier template dans [cin_layouts.py](cin_layouts.py).
5. Rebuild image et deploiement sur environnement de test.
6. Lancer smoke tests:

- /supported-types,
- /ocr-only,
- /extract-identity,
- /extract-identity-path.

7. Comparer resultats sur dataset de regression avant passage prod.

Critere de go/no-go:

- champs requis stables,
- dates coherentes,
- pas de degradation sur pays deja en production.
