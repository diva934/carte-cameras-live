@echo off
chcp 65001 >nul
title Carte Cameras Live - installation
echo ============================================================
echo   Carte Cameras Live - installation
echo ============================================================
echo.

where python >nul 2>&1
if errorlevel 1 (
  echo [X] Python n'est pas installe, ou pas dans le PATH.
  echo     Installe-le depuis https://www.python.org/downloads/
  echo     IMPORTANT : coche "Add Python to PATH" pendant l'installation.
  echo.
  pause
  exit /b 1
)
for /f "tokens=2" %%v in ('python --version 2^>^&1') do echo [1/4] Python %%v detecte

if not exist ".venv\" (
  echo [2/4] Creation de l'environnement isole...
  python -m venv .venv
) else (
  echo [2/4] Environnement isole deja present
)

echo [3/4] Installation des dependances (quelques minutes la premiere fois)...
call .venv\Scripts\python.exe -m pip install --upgrade pip --quiet
call .venv\Scripts\python.exe -m pip install -r requirements.txt --quiet
if errorlevel 1 (
  echo [X] L'installation des dependances a echoue.
  pause
  exit /b 1
)

if not exist "keys.json" (
  copy /y keys.example.json keys.json >nul
  echo [4/4] keys.json cree a partir du modele
) else (
  echo [4/4] keys.json deja present, conserve
)

echo.
echo ============================================================
echo   Installation terminee.
echo.
echo   Lance l'application avec : lancer.bat
echo.
echo   La carte et les cameras fonctionnent immediatement.
echo   Pour l'assistant et la geolocalisation de photo, ouvre
echo   keys.json et renseigne "vlm_key" (voir INSTALLATION.md).
echo ============================================================
echo.
pause
