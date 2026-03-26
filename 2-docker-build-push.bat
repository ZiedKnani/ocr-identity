@echo off
echo ========================================
echo Construction et Push Docker Image
echo ========================================
echo.

REM Vérifier Docker
echo [1/5] Verification Docker...
docker --version
if errorlevel 1 (
    echo ERREUR: Docker n'est pas installe ou Docker Desktop n'est pas lance
    pause
    exit /b 1
)

REM Login Docker Hub
echo [2/5] Connexion a Docker Hub...
echo Username: zied2711
docker login -u zied2711
if errorlevel 1 (
    echo ERREUR: Echec de connexion a Docker Hub
    pause
    exit /b 1
)

REM Construire l'image
echo [3/5] Construction de l'image Docker (cela peut prendre 5-10 minutes)...
docker build -t zied2711/ocr-identity:latest .
if errorlevel 1 (
    echo ERREUR: Echec de construction de l'image
    pause
    exit /b 1
)

REM Tag version
echo [4/5] Creation du tag de version...
docker tag zied2711/ocr-identity:latest zied2711/ocr-identity:v2.0.0

REM Push vers Docker Hub
echo [5/5] Push vers Docker Hub...
docker push zied2711/ocr-identity:latest
docker push zied2711/ocr-identity:v2.0.0

echo.
echo ========================================
echo SUCCESS! Image Docker poussee vers Docker Hub
echo Image: zied2711/ocr-identity:latest
echo Image: zied2711/ocr-identity:v2.0.0
echo ========================================
pause
