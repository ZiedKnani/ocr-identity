# Rapport Technique Academique - OCR Identity Extractor V2

## Resume

Ce projet propose un service d extraction automatique de donnees d identite a partir d images de documents (CIN, NINA, passeport, etc.). L approche combine OCR, detection de type documentaire, extraction par regles metier, et validation ponderee des champs.

Le systeme est oriente Afrique/CEDEAO, avec extension progressive par pays et par templates de mise en page.

## 1. Contexte et problematique

Dans de nombreux flux KYC, la saisie manuelle des champs d identite est lente, couteuse et source d erreurs. Les documents presents sur le terrain posent des difficultes pratiques:

- qualite image variable (flou, compression, reflets),
- heterogeneite forte des formats entre pays,
- bruit OCR sur les labels et les dates,
- presence frequente de recto/verso.

Objectif du projet:

- automatiser extraction et structuration des champs,
- fournir un score de confiance exploitable,
- garder une architecture modulaire et evolutive.

## 2. Objectifs du systeme

- Detecter le type de document automatiquement.
- Extraire les champs critiques: numero, nom, prenom, dates, etc.
- Ajouter metadonnees de localisation pour certains champs (bbox).
- Evaluer la qualite d extraction via un score pondere.
- Exposer ces fonctions via API REST.

## 3. Choix d architecture

Le projet suit une architecture modulaire:

- API FastAPI pour l exposition des services.
- Orchestrateur de pipeline dans [id_processor_v2.py](id_processor_v2.py).
- Detection de document dans [document_detector.py](document_detector.py).
- Strategies d extraction par type dans [document_strategy.py](document_strategy.py).
- Definitions metier (types/champs/poids) dans [document_types.py](document_types.py).

### 3.1 Justification du Strategy Pattern

Le choix d une strategie par type documentaire permet:

- isolation des regles pays/type,
- reduction du couplage entre detection et extraction,
- evolution independante des regles,
- meilleure maintenabilite.

### 3.2 Flux de traitement

1. Reception requete (upload, base64, path).
2. Pretraitement image et OCR.
3. Detection du type documentaire.
4. Extraction par strategie.
5. Enrichissement (MRZ passeport, annotation CIN).
6. Validation et calcul du score.
7. Retour JSON standardise.

## 4. Description des composants

### 4.1 Couche API

Fichier principal: [main_v2.py](main_v2.py)

Endpoints majeurs:

- GET /health
- GET /supported-types
- POST /extract-identity
- POST /extract-identity-base64
- POST /extract-identity-path
- POST /ocr-only
- POST /extract-batch

Le endpoint path est utile pour integrer des flux fichiers internes (partage reseau, dossier de depose).

### 4.2 Orchestrateur

Fichier: [id_processor_v2.py](id_processor_v2.py)

Responsabilites:

- execution OCR,
- identification du type,
- appel de la strategie,
- validation des resultats,
- gestion recto/verso,
- lazy loading MRZ.

### 4.3 Detection documentaire

Fichier: [document_detector.py](document_detector.py)

Detection hybride:

- mots cles,
- patterns de numeros,
- heuristiques structurelles,
- bonus MRZ pour passeport.

### 4.4 Extraction

Fichier: [document_strategy.py](document_strategy.py)

Mecanismes utilises:

- extraction contextuelle basee labels,
- fallback regex,
- normalisation des dates,
- fallback chronologique,
- annotation de zones attendues CIN via templates.

### 4.5 Metier et validation

Fichier: [document_types.py](document_types.py)

Apporte:

- taxonomie des types de documents,
- champs requis/optionnels,
- mapping codes documentaires,
- poids de champs pour score global.

## 5. Resultats observables

Forces actuelles:

- couverture multi format d entree,
- support recto/verso,
- extraction stable sur cas deja calibres,
- enrichissement bbox sur CIN,
- support multilingue OCR (fr/ar) avec mode auto possible.

## 6. Limites

- forte dependance a la qualite image.
- regles encore heuristiques sur certains pays.
- besoin de calibration continue CEDEAO.
- absence d un protocole de benchmark automatise visible.

## 7. Proposition d amelioration methodologique

### 7.1 Qualite logicielle

- Mettre en place un jeu de non regression par pays.
- Verrouiller les bugs corriges via tests cibles.
- Produire un rapport qualite par version.

### 7.2 Performance

- Cache OCR base hash image.
- Preechauffage optionnel des modeles.
- Gestion fine des timeouts/retries.

### 7.3 Observabilite

- Metriques latence, taux erreur OCR, score moyen extraction.
- Logs structures et correlation id.

### 7.4 Industrialisation des regles

- Externaliser labels/patterns en fichiers de config versionnes.
- Ajouter un validateur automatique de coherence des regles.

## 8. Plan experimental recommande

1. Constituer dataset anonyme multi pays.
2. Mesurer precision par champ et par type.
3. Comparer baseline et versions optimisees.
4. Suivre evolutions via tableau de bord qualite.

## 9. Conclusion

Le projet presente une base robuste pour l extraction d identite OCR, adaptee aux contextes heterogenes Afrique/CEDEAO. L architecture modulaire facilite les evolutions, mais la fiabilite a grande echelle dependra surtout de l industrialisation des tests de regression et de la gouvernance des regles pays.

## 10. Comment ajouter un nouveau type ou un nouveau pays

Pour etendre le systeme sans casser l existant:

1. Declarer le type/champs/poids dans [document_types.py](document_types.py).
2. Ajouter detection mots-cles et patterns dans [document_detector.py](document_detector.py).
3. Ajouter les regles d extraction dans [document_strategy.py](document_strategy.py).
4. Pour une CIN pays, declarer les zones dans [cin_layouts.py](cin_layouts.py).
5. Valider sur un jeu d images representatif et ajouter tests de non regression.

Principe methodologique:

- extraction contextuelle par label d abord,
- fallback regex ensuite,
- fallback chronologique des dates en dernier recours.

## Bibliographie technique interne

- [DOCUMENTATION_TECHNIQUE.md](DOCUMENTATION_TECHNIQUE.md)
- [main_v2.py](main_v2.py)
- [id_processor_v2.py](id_processor_v2.py)
- [document_strategy.py](document_strategy.py)
- [document_detector.py](document_detector.py)
- [document_types.py](document_types.py)
- [Dockerfile](Dockerfile)
- [docker-compose.yml](docker-compose.yml)
