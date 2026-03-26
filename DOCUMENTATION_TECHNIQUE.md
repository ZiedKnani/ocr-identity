# Documentation Technique - OCR Identity Extractor V2

## 1. Objectif du programme

OCR Identity Extractor V2 est un service API qui:

- détecte le type de document d'identité,
- extrait les champs métier (nom, prénom, numéro, dates, etc.),
- calcule un score de validation,
- renvoie des métadonnées de localisation (bounding boxes) pour les champs CIN.

Le service est conçu pour des flux Afrique/CEDEAO, avec un focus fort sur les cartes d'identité et les passeports.

## 2. Portée fonctionnelle actuelle

### Documents pris en charge

- Carte NINA
- Carte Nationale d'Identité
- CIN biométrique
- Passeport
- Passeport biométrique (avec MRZ)
- Permis de conduire
- Titre de séjour
- Visa
- Extrait de naissance

Référence: [document_types.py](document_types.py)

### Modes d'entrée supportés

- Fichier upload multipart
- Base64 (recto/verso ou image unique)
- Chemin fichier via JSON (endpoint path)
- Batch multi-fichiers

Référence: [main_v2.py](main_v2.py)

## 3. Architecture logique

### Composants principaux

- API REST FastAPI: orchestration des endpoints et normalisation des requêtes
- IdProcessorV2: pipeline principal OCR -> détection -> extraction -> validation
- OCRProcessor: prétraitement image + exécution PaddleOCR
- DocumentDetector: détection du type via scoring texte/patterns/structure
- DocumentStrategy: règles d'extraction par type de document
- Validator: scoring de complétude/qualité selon les champs requis
- MRZParser: parsing MRZ des passeports
- cin_layouts: templates de zones attendues par pays/version

Références:

- [main_v2.py](main_v2.py)
- [id_processor_v2.py](id_processor_v2.py)
- [document_detector.py](document_detector.py)
- [document_strategy.py](document_strategy.py)
- [document_types.py](document_types.py)

### Flux de traitement (simplifié)

1. Réception de la requête et validation des paramètres.
2. Prétraitement image.
3. OCR principal (PaddleOCR).
4. Détection du type documentaire.
5. Extraction des champs avec stratégie adaptée.
6. Enrichissement (exemple: MRZ pour passeports, zones CIN).
7. Validation et scoring.
8. Construction de la réponse JSON.

## 4. Endpoints API

Endpoints exposés:

- GET /
- GET /health
- GET /supported-types
- POST /extract-identity
- POST /extract-identity-base64
- POST /extract-identity-path
- POST /extract-identity-sync
- POST /ocr-only
- POST /ocr-only-base64
- POST /ocr-only-sync
- POST /extract-batch

Référence: [main_v2.py](main_v2.py#L238)

### Notes d'usage importantes

- En conteneur Linux, un chemin Windows brut peut ne pas être résolu tel quel.
- Avec le montage standard -v C:\Users\PC:/host, utiliser préférentiellement un chemin de type /host/....

## 5. Détection et extraction

### Détection

La détection combine:

- mots-clés documentaires,
- formats regex de numéros,
- heuristiques de structure (exemple: présence MRZ, densité blocs).

Référence: [document_detector.py](document_detector.py)

### Extraction

L'extraction repose sur:

- règles spécifiques par type,
- recherche contextuelle par labels,
- parsing de dates multi-formats,
- fallback chronologique,
- annotation de localisation pour les champs CIN.

Référence: [document_strategy.py](document_strategy.py)

### Validation

Le score est pondéré par importance de champs (ID, nom, prénom, dates, etc.).

Référence: [document_types.py](document_types.py#L171)

## 6. Déploiement et exploitation

### Docker

- Image Python 3.10 slim
- Exécution non-root
- Healthcheck HTTP
- Volume cache PaddleOCR recommandé

Références:

- [Dockerfile](Dockerfile)
- [docker-compose.yml](docker-compose.yml)

### Configuration opérationnelle

- Activer les logs applicatifs côté FastAPI
- Persister le cache modèles OCR
- Mettre en place un reverse proxy pour la production (nginx profile)

## 7. Forces techniques actuelles

- Architecture modulaire claire (détection/extraction/validation séparées)
- Support multi-canaux d'entrée (upload, base64, path, batch)
- Support recto-verso
- Localisation des champs avec bounding boxes et templates pays
- Lazy loading MRZ pour réduire le temps de démarrage
- Cache OCR par langue (fr/ar)

## 8. Limites connues

- Dépendance élevée à la qualité OCR brute (flou, reflets, compression)
- Règles métier encore fortement heuristiques pour certains pays
- Variabilité CEDEAO inter-pays encore en calibration continue
- Pas de jeu de tests de régression formalisé visible dans le repo
- Observabilité limitée (pas de métriques Prometheus ni tracing distribué)

## 9. Plan d'amélioration priorisé

## 9.1 Priorité P0 (stabilité et qualité immédiate)

- Créer une suite de non-régression avec des cas représentatifs par pays.
- Versionner un dataset de référence anonymisé (recto/verso, formats variés).
- Ajouter des tests automatiques sur:
  - mapping dates (naissance, délivrance, expiration),
  - extraction nom/prénom,
  - extraction numéro ID,
  - extraction champs optionnels (sexe, lieu de délivrance).
- Ajouter un rapport de qualité par release (précision champ par champ).

Impact attendu:

- diminution des régressions en production,
- montée en fiabilité des évolutions pays.

## 9.2 Priorité P1 (performance et résilience)

- Mettre en cache les résultats OCR/détection sur hash image pour éviter les recalculs.
- Définir un mode de préchauffage optionnel des modèles au démarrage.
- Introduire des timeouts et retries configurables selon endpoint.
- Ajouter circuit breaker sur les traitements lourds en cas de charge.

Impact attendu:

- latence plus stable,
- meilleure tenue en charge.

## 9.3 Priorité P1 (observabilité)

- Ajouter métriques techniques et métier:
  - latence par endpoint,
  - taux d'échec OCR,
  - taux de validité extraction,
  - score moyen par type document.
- Exposer un endpoint metrics.
- Structurer logs JSON avec identifiant de corrélation.

Impact attendu:

- diagnostic plus rapide,
- pilotage data-driven des optimisations.

## 9.4 Priorité P2 (gouvernance des règles documentaires)

- Externaliser règles d'extraction (labels, patterns, fallback) en YAML/JSON versionnés.
- Séparer les règles par pays et version de template.
- Ajouter un validateur de cohérence des règles au build.

Impact attendu:

- maintenance simplifiée,
- contribution plus rapide de nouveaux pays.

## 9.5 Priorité P2 (amélioration IA/OCR)

- Évaluer un ensemble OCR (PaddleOCR + Tesseract) avec vote par champ.
- Ajouter post-correction lexicale par dictionnaires métiers (noms labels, mois, pays).
- Mettre en place un score de confiance calibré par type champ.

Impact attendu:

- hausse de rappel en conditions OCR difficiles,
- réduction des inversions et substitutions texte.

## 10. Roadmap recommandée sur 90 jours

### Semaine 1 a 2

- Mettre en place jeux de tests et baseline qualité.
- Bloquer les régressions critiques sur ID/date/nom/prénom.

### Semaine 3 a 6

- Instrumentation métriques et logs structurés.
- Optimisations de cache et timeouts.

### Semaine 7 a 10

- Externalisation des règles pays/version.
- Process de review des règles et validation automatique.

### Semaine 11 a 12

- Expérimentation OCR ensemble et calibration des scores.
- Rapport de gains sur dataset de validation.

## 11. Bonnes pratiques pour continuer le projet

- Toujours tester un changement règle sur au moins 3 pays avant fusion.
- Prioriser extraction par label contextuel avant fallback chronologique.
- Documenter chaque nouvelle règle pays avec exemple OCR et résultat attendu.
- Ajouter un test de non-régression pour chaque bug corrigé.

## 12. Guide d extension - Nouveau type de document et nouveau pays

### 12.1 Ajouter un nouveau type de document

Etape 1 - Declarer le type dans [document_types.py](document_types.py)

- Ajouter une entree dans l enum DocumentType.
- Ajouter une DocumentDefinition avec:
  - required_fields,
  - optional_fields,
  - codes (si disponible),
  - detection_keywords,
  - detection_number_patterns,
  - features.

Etape 2 - Ajouter la logique de detection dans [document_detector.py](document_detector.py)

- Verifier que les mots-cles et patterns sont couverts.
- Ajouter des heuristiques structurelles si necessaire.

Etape 3 - Ajouter la strategie d extraction dans [document_strategy.py](document_strategy.py)

- Soit creer une methode dediee (recommande),
- Soit enrichir une methode existante si le format est tres proche.
- Prioriser extraction contextuelle (labels) puis fallback regex.

Etape 4 - Brancher l extraction dans [document_strategy.py](document_strategy.py)

- Mettre a jour la methode extract(...) pour router le nouveau type vers la bonne strategie.

Etape 5 - Verifier l API dans [main_v2.py](main_v2.py)

- Confirmer que le type apparait dans /supported-types.
- Confirmer la compatibilite code_document (si code metier utilise).

### 12.2 Ajouter un nouveau pays pour une CIN

Etape 1 - Ajouter un template de layout dans [cin_layouts.py](cin_layouts.py)

- Ajouter un template_id (exemple: PAYS_CEDEAO_V1).
- Definir les zones normalisees par champ (x1, y1, x2, y2).
- Ajouter les indices utilises pour detect_cin_layout(...).

Etape 2 - Ajouter les labels metier du pays dans [document_strategy.py](document_strategy.py)

- Ajouter variantes FR/EN/locales et variantes OCR bruites.
- Ajouter extraction contextuelle pour:
  - numero_id,
  - nom,
  - prenom,
  - date_naissance,
  - date_delivrance,
  - date_expiration,
  - champs optionnels (sexe, lieu_delivrance).

Etape 3 - Ajuster les dates et normalisations

- Couvrir formats DD/MM/YYYY, DDMONYYYY, MM/YYYY, etc.
- Garder fallback chronologique uniquement en dernier recours.

Etape 4 - Validation terrain

- Tester sur plusieurs specimens du meme pays (recto/verso si disponible).
- Verifier in_expected_zone sur les champs critiques.
- Mesurer precision champ par champ.

### 12.3 Checklist minimale avant merge

- [ ] Le nouveau type/pays est detecte correctement.
- [ ] Les champs requis sont extraits sur un jeu de tests representatif.
- [ ] Les dates ne sont pas inversees (delivrance vs expiration).
- [ ] Les labels de bruit ne polluent pas nom/prenom.
- [ ] Les tests de non regression existants passent.
- [ ] La documentation est mise a jour (regles + exemples).

### 12.4 Exemple de sequence de travail recommandee

1. Ajouter definitions et patterns dans [document_types.py](document_types.py).
2. Ajouter detection complementaire dans [document_detector.py](document_detector.py).
3. Ajouter extraction dans [document_strategy.py](document_strategy.py).
4. Ajouter template zones dans [cin_layouts.py](cin_layouts.py) si CIN.
5. Tester via /ocr-only puis /extract-identity et /extract-identity-path.
6. Rebuild docker et valider sur un lot d images.

### 12.5 Erreurs frequentes a eviter

- Oublier de router le nouveau type dans extract(...).
- Ajouter des labels trop generiques qui creent des faux positifs.
- Utiliser la chronologie des dates avant l extraction par label.
- Oublier les variantes OCR (caracteres confondus, ponctuation absente).
- Calibrer avec un seul exemple image.

## 13. Annexe - Références code utiles

- API et endpoints: [main_v2.py](main_v2.py)
- Orchestrateur pipeline: [id_processor_v2.py](id_processor_v2.py)
- Détection documentaire: [document_detector.py](document_detector.py)
- Règles d'extraction: [document_strategy.py](document_strategy.py)
- Types/champs/pondérations: [document_types.py](document_types.py)
- Déploiement conteneur: [Dockerfile](Dockerfile), [docker-compose.yml](docker-compose.yml)

## 14. Export de la documentation en PDF

Un script est disponible pour convertir un fichier Markdown en PDF:

- Script: [scripts/export_markdown_pdf.py](scripts/export_markdown_pdf.py)
- Dépendances docs: [requirements-docs.txt](requirements-docs.txt)

### Installation des dépendances docs

Commande:
pip install -r requirements-docs.txt

### Générer un PDF

Exemple:
python scripts/export_markdown_pdf.py DOCUMENTATION_TECHNIQUE.md -o DOCUMENTATION_TECHNIQUE.pdf -t "Documentation OCR Identity Extractor V2"

### Personnaliser le style

Le script inclut un style professionnel par défaut et accepte une surcharge CSS:

- Option: --css chemin/vers/style.css

### Notes Windows

- WeasyPrint peut nécessiter des dépendances système (runtime graphique).
- Si une erreur de bibliothèque apparaît, installer les prérequis WeasyPrint pour Windows puis relancer.
