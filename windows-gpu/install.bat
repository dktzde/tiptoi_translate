@echo off
echo ============================================================
echo  Tiptoi Whisper – Installation (Windows, Intel GPU)
echo ============================================================
echo.

REM Python prüfen
python --version >nul 2>&1
if errorlevel 1 (
    echo FEHLER: Python nicht gefunden!
    echo Bitte Python 3.10+ von https://python.org installieren.
    pause
    exit /b 1
)
python --version

echo.
echo Installiere Pakete...
echo.

pip install faster-whisper
pip install openvino
pip install soundfile

echo.
echo ============================================================
echo  Installation abgeschlossen!
echo  Test: python transcribe.py --help
echo ============================================================
pause
