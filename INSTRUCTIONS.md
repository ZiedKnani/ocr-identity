# 🚀 Instructions de Déploiement

## Prérequis

Avant de commencer, assurez-vous d'avoir :
- ✅ Git installé
- ✅ Docker Desktop installé et lancé
- ✅ Créé le repository GitHub "ocr-identity" sur https://github.com/new

## 📝 Étapes

### Étape 1 : Créer le Repository GitHub

1. Allez sur https://github.com/new
2. Nom du repository : `ocr-identity`
3. Visibilité : Public ou Private (selon votre choix)
4. **NE COCHEZ PAS** "Initialize with README"
5. Cliquez sur "Create repository"

### Étape 2 : Push le Code vers GitHub

Double-cliquez sur le fichier : **`1-git-init.bat`**

Le script va :
- Initialiser Git
- Configurer votre utilisateur (ZiedKnani)
- Vous demander votre email GitHub
- Ajouter tous les fichiers
- Créer le commit initial
- Pousser vers GitHub

### Étape 3 : Build et Push Docker

Double-cliquez sur le fichier : **`2-docker-build-push.bat`**

Le script va :
- Vérifier que Docker est installé
- Se connecter à Docker Hub (username: zied2711)
- Construire l'image Docker (5-10 minutes)
- Créer les tags (latest et v2.0.0)
- Pousser vers Docker Hub

## 📦 Résultats

Après avoir exécuté les deux scripts :

✅ **GitHub** : https://github.com/ZiedKnani/ocr-identity
✅ **Docker Hub** : https://hub.docker.com/r/zied2711/ocr-identity

## 🧪 Tester l'Image Docker

Pour tester votre image Docker :

```bash
docker pull zied2711/ocr-identity:latest
docker run -p 8000:8000 zied2711/ocr-identity:latest
```

Puis ouvrez : http://localhost:8000/health

## ⚠️ En cas de problème

### Git n'est pas reconnu
- Installez Git : https://git-scm.com/download/win
- Redémarrez votre terminal

### Docker n'est pas reconnu
- Installez Docker Desktop : https://www.docker.com/products/docker-desktop
- Lancez Docker Desktop
- Redémarrez votre terminal

### Erreur "repository not found" sur GitHub
- Assurez-vous d'avoir créé le repository sur GitHub
- Vérifiez que le nom est bien "ocr-identity"

### Erreur Docker Hub login
- Vérifiez votre username : zied2711
- Vérifiez votre mot de passe Docker Hub
