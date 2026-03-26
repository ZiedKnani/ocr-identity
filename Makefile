# Makefile pour OCR Identity Extractor V2

.PHONY: help build up down restart logs clean test

# Variables
COMPOSE=docker-compose
SERVICE=ocr-api
IMAGE_NAME=ocr-identity-extractor
VERSION=2.0.0

# Couleurs pour output
GREEN=\033[0;32m
YELLOW=\033[1;33m
RED=\033[0;31m
NC=\033[0m # No Color

##@ Aide

help: ## Afficher cette aide
	@echo "$(GREEN)OCR Identity Extractor V2 - Commandes disponibles:$(NC)"
	@awk 'BEGIN {FS = ":.*##"; printf "\n"} /^[a-zA-Z_-]+:.*?##/ { printf "  $(YELLOW)%-15s$(NC) %s\n", $$1, $$2 } /^##@/ { printf "\n$(GREEN)%s$(NC)\n", substr($$0, 5) } ' $(MAKEFILE_LIST)

##@ Développement

build: ## Construire l'image Docker
	@echo "$(GREEN)🔨 Construction de l'image Docker...$(NC)"
	$(COMPOSE) build
	@echo "$(GREEN)✅ Image construite avec succès$(NC)"

up: ## Démarrer les services
	@echo "$(GREEN)🚀 Démarrage des services...$(NC)"
	$(COMPOSE) up -d
	@echo "$(GREEN)✅ Services démarrés$(NC)"
	@echo "$(YELLOW)📝 API disponible sur: http://localhost:8000$(NC)"
	@echo "$(YELLOW)📚 Documentation: http://localhost:8000/docs$(NC)"

down: ## Arrêter les services
	@echo "$(YELLOW)🛑 Arrêt des services...$(NC)"
	$(COMPOSE) down
	@echo "$(GREEN)✅ Services arrêtés$(NC)"

restart: ## Redémarrer les services
	@echo "$(YELLOW)🔄 Redémarrage des services...$(NC)"
	$(COMPOSE) restart
	@echo "$(GREEN)✅ Services redémarrés$(NC)"

logs: ## Voir les logs en temps réel
	$(COMPOSE) logs -f $(SERVICE)

logs-all: ## Voir tous les logs
	$(COMPOSE) logs -f

##@ Maintenance

clean: ## Nettoyer les conteneurs et volumes
	@echo "$(RED)🧹 Nettoyage...$(NC)"
	$(COMPOSE) down -v
	docker image prune -f
	@echo "$(GREEN)✅ Nettoyage terminé$(NC)"

clean-all: ## Nettoyer complètement (images, volumes, cache)
	@echo "$(RED)🧹 Nettoyage complet...$(NC)"
	$(COMPOSE) down -v --rmi all
	docker system prune -af
	@echo "$(GREEN)✅ Nettoyage complet terminé$(NC)"

prune: ## Supprimer les images non utilisées
	docker image prune -af

##@ Tests

test: ## Tester l'API (nécessite curl)
	@echo "$(YELLOW)🧪 Test de l'API...$(NC)"
	@curl -s http://localhost:8000/health | jq . || echo "$(RED)❌ API non disponible$(NC)"
	@echo ""
	@curl -s http://localhost:8000/supported-types | jq '.count' || echo "$(RED)❌ Erreur$(NC)"

shell: ## Ouvrir un shell dans le conteneur
	$(COMPOSE) exec $(SERVICE) /bin/bash

ps: ## Lister les conteneurs
	$(COMPOSE) ps

stats: ## Voir les statistiques des conteneurs
	docker stats

##@ Production

prod-up: ## Démarrer en mode production (avec Nginx)
	@echo "$(GREEN)🚀 Démarrage en mode production...$(NC)"
	$(COMPOSE) --profile production up -d
	@echo "$(GREEN)✅ Services production démarrés$(NC)"
	@echo "$(YELLOW)🌐 API disponible sur: http://localhost$(NC)"

prod-down: ## Arrêter les services production
	$(COMPOSE) --profile production down

##@ Debug

debug: ## Démarrer en mode debug (logs détaillés)
	LOG_LEVEL=DEBUG $(COMPOSE) up

inspect: ## Inspecter le conteneur
	docker inspect $(SERVICE)

health: ## Vérifier la santé du service
	@echo "$(YELLOW)🏥 Vérification de la santé...$(NC)"
	@docker inspect --format='{{.State.Health.Status}}' ocr-identity-api || echo "$(RED)Service non démarré$(NC)"

##@ Backup

backup-models: ## Sauvegarder le cache des modèles
	@echo "$(YELLOW)💾 Sauvegarde des modèles...$(NC)"
	docker run --rm -v ocr-paddle-models:/data -v $(PWD)/backups:/backup alpine tar czf /backup/paddle-models-backup-$(shell date +%Y%m%d-%H%M%S).tar.gz -C /data .
	@echo "$(GREEN)✅ Sauvegarde terminée dans ./backups/$(NC)"

restore-models: ## Restaurer le cache des modèles (usage: make restore-models FILE=backup.tar.gz)
	@echo "$(YELLOW)📂 Restauration des modèles...$(NC)"
	docker run --rm -v ocr-paddle-models:/data -v $(PWD)/backups:/backup alpine sh -c "cd /data && tar xzf /backup/$(FILE)"
	@echo "$(GREEN)✅ Restauration terminée$(NC)"

##@ Informations

version: ## Afficher la version
	@echo "$(GREEN)OCR Identity Extractor V2$(NC)"
	@echo "Version: $(VERSION)"

info: ## Afficher les informations du système
	@echo "$(GREEN)=== Informations Docker ===$(NC)"
	@docker version
	@echo ""
	@echo "$(GREEN)=== Images locales ===$(NC)"
	@docker images | grep $(IMAGE_NAME) || echo "Aucune image trouvée"
	@echo ""
	@echo "$(GREEN)=== Volumes ===$(NC)"
	@docker volume ls | grep ocr || echo "Aucun volume trouvé"
