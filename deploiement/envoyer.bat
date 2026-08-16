@echo off
chcp 65001 >nul
REM Envoie le projet vers le VPS, sans les secrets ni les modeles.
REM   envoyer.bat root@1.2.3.4
setlocal

if "%~1"=="" (
  echo Usage : envoyer.bat utilisateur@adresse-du-vps
  echo Exemple : envoyer.bat root@51.75.12.34
  pause
  exit /b 1
)
set CIBLE=%~1
set SRC=%~dp0..

where scp >nul 2>&1
if errorlevel 1 (
  echo [X] scp introuvable. Installe OpenSSH : Parametres ^> Applications ^>
  echo     Fonctionnalites facultatives ^> Client OpenSSH.
  pause
  exit /b 1
)

echo Envoi du code vers %CIBLE%:/opt/carte ...
scp "%SRC%\earthcam_live_map.py" "%SRC%\photo_osint.py" %CIBLE%:/opt/carte/
if errorlevel 1 goto erreur
scp -r "%SRC%\web" %CIBLE%:/opt/carte/
if errorlevel 1 goto erreur

echo.
echo Le fichier keys.json contient tes cles : envoie-le seulement si tu le souhaites.
choice /c ON /m "Envoyer keys.json aussi (O/N)"
if errorlevel 2 goto fin
scp "%SRC%\keys.json" %CIBLE%:/opt/carte/

:fin
echo.
echo Termine. Sur le VPS : systemctl restart carte
pause
exit /b 0

:erreur
echo.
echo [X] L'envoi a echoue. Verifie l'adresse et que /opt/carte existe sur le VPS.
pause
exit /b 1
