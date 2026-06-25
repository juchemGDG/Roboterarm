@echo off
setlocal enableextensions enabledelayedexpansion

set PROJECT_ROOT=%~dp0\..
cd /d "%PROJECT_ROOT%"

py -m pip install -r requirements.txt -r requirements-build.txt
if errorlevel 1 goto :error

py -m PyInstaller --noconfirm --clean roboterarm_gui.spec
if errorlevel 1 goto :error

if "%ISCC_PATH%"=="" (
  where iscc >nul 2>nul
  if errorlevel 1 (
    echo Inno Setup (iscc) nicht gefunden. Nur PyInstaller-Ausgabe erstellt.
    echo EXE liegt in dist\RoboterarmSteuerung\
    goto :done
  )
  set ISCC_PATH=iscc
)

"%ISCC_PATH%" installer\windows\roboterarm_gui.iss
if errorlevel 1 goto :error

echo Setup erstellt: dist\RoboterarmSteuerung-Setup.exe
goto :done

:error
echo Build fehlgeschlagen.
exit /b 1

:done
exit /b 0
