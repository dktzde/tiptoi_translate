@echo off
echo ============================================================
echo  Tiptoi Whisper Transkription
echo ============================================================
echo.

if "%~1"=="" (
    echo Verwendung:  run.bat BUCHNAME_ogg.zip
    echo Beispiel:    run.bat Pocketwissen_Feuerwehr_ogg.zip
    echo.
    echo Optionales Modell:
    echo   run.bat Pocketwissen_Feuerwehr_ogg.zip small
    echo   run.bat Pocketwissen_Feuerwehr_ogg.zip large-v3-turbo
    echo.
    pause
    exit /b 1
)

set OGG_ZIP=%~1
set MODEL=large-v3-turbo
if not "%~2"=="" set MODEL=%~2

echo Eingabe:  %OGG_ZIP%
echo Modell:   %MODEL%
echo.

python transcribe.py "%OGG_ZIP%" --model %MODEL%

echo.
pause
