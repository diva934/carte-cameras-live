@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Carte Cameras Live - garde cette fenetre ouverte
echo ============================================================
echo   Carte Cameras Live
echo   La carte va s'ouvrir. GARDE CETTE FENETRE OUVERTE :
echo   c'est elle qui fait tourner l'application.
echo ============================================================
echo.

if not exist ".venv\Scripts\python.exe" (
  echo [X] Environnement introuvable. Lance d'abord installer.bat
  echo.
  pause
  exit /b 1
)

.venv\Scripts\python.exe earthcam_live_map.py
echo.
echo Application arretee.
pause
