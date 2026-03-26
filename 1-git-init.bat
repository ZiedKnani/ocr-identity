@echo off
echo ========================================
echo Configuration Git et Push vers GitHub
echo ========================================
echo.

REM Initialiser Git
echo [1/6] Initialisation Git...
git init
if errorlevel 1 (
    echo ERREUR: Git n'est pas installe ou pas dans le PATH
    pause
    exit /b 1
)

REM Configurer l'utilisateur
echo [2/6] Configuration utilisateur...
git config user.name "ZiedKnani"
git config user.email "ziedknani0@gmail.com"

REM Ajouter tous les fichiers
echo [3/6] Ajout des fichiers...
git add .

REM Créer le commit initial
echo [4/6] Creation du commit initial...
git commit -m "Initial commit: OCR Identity Extractor V2" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"

REM Ajouter le remote
echo [5/6] Ajout du remote GitHub...
git remote add origin https://github.com/ZiedKnani/ocr-identity.git

REM Renommer la branche en main
echo [6/6] Push vers GitHub...
git branch -M main
git push -u origin main

echo.
echo ========================================
echo SUCCESS! Code pousse vers GitHub
echo ========================================
pause
