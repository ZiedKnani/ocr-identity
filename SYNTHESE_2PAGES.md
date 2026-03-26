# Synthese Executive (2 pages) - OCR Identity Extractor V2

## 1. En une phrase

OCR Identity Extractor V2 est une API qui transforme des images de documents d identite en donnees structurees exploitables pour les processus KYC.

## 2. Valeur business

- Reduction du temps de saisie manuelle.
- Diminution des erreurs de recopie.
- Standardisation du traitement multi-documents.
- Meilleure tracabilite de la qualite (score extraction).

## 3. Ce que le systeme fait aujourd hui

- Detecte automatiquement le type de document.
- Extrait numero, nom, prenom, dates et autres champs.
- Gere upload fichier, base64, chemin fichier, batch.
- Supporte recto/verso.
- Retourne des metadonnees de localisation pour certains champs CIN.

References techniques:

- [main_v2.py](main_v2.py)
- [id_processor_v2.py](id_processor_v2.py)
- [document_strategy.py](document_strategy.py)

## 4. Architecture en bref

- API FastAPI expose les endpoints.
- OCR traite l image.
- Detector determine le type de document.
- Strategy applique les regles d extraction par type.
- Validator calcule un score de qualite.

Fichiers cle:

- [document_detector.py](document_detector.py)
- [document_types.py](document_types.py)

## 5. Cas d usage cibles

- Onboarding client (KYC)
- Pre-qualification de dossiers
- Controle de pieces dans un workflow interne
- Integration avec SI bancaire/assurance/administration

## 6. Risques actuels

- Sensibilite a la qualite image.
- Variabilite pays/formats (surtout CEDEAO) necessitant calibration continue.
- Regles encore en partie heuristiques.
- Observabilite et tests de regression a renforcer.

## 7. Plan d amelioration (priorites)

### P0 - Fiabilite

- Suite de non regression par pays.
- Dataset de reference anonyme.
- Rapport qualite a chaque release.

### P1 - Performance et resilience

- Cache OCR par hash image.
- Preechauffage optionnel modeles.
- Timeouts/retries parametrables.

### P1 - Pilotage

- Metriques service et metier.
- Logs structures + correlation id.

### P2 - Evolutivite

- Externalisation des regles pays en config versionnee.
- Validation automatique de coherence des regles.

## 8. KPI recommandes

- Precision champs requis par type document.
- Taux documents valides.
- Latence P95 par endpoint.
- Taux erreurs 5xx.
- Taux de reprocessing manuel.

## 9. Decisions recommandees

1. Industrialiser les tests de non regression avant nouvelles extensions pays.
2. Mettre en place metriques et dashboard qualite.
3. Structurer gouvernance des regles documentaires.
4. Planifier benchmark trimestriel precision/latence.

## 10. Message final

La solution est operationnelle et bien structuree. Le principal levier de gain maintenant est l industrialisation: qualite mesuree, regles gouvernees, et exploitation outillee.

## Annexes

- [DOCUMENTATION_TECHNIQUE.md](DOCUMENTATION_TECHNIQUE.md)
- [DOCUMENTATION_ACADEMIQUE.md](DOCUMENTATION_ACADEMIQUE.md)
- [RUNBOOK_PRODUCTION.md](RUNBOOK_PRODUCTION.md)
