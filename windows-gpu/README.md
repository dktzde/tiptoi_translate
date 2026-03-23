# Tiptoi Whisper – Windows Intel GPU

Transkribiert Tiptoi-OGG-Dateien mit Whisper auf Windows (Intel GPU via OpenVINO oder CPU-Fallback).
Output ist ein ZIP mit `.txt`-Transkripten und `_ts.json`-Timestamps – kompatibel mit der Tiptoi-Pipeline auf Linux.

## Voraussetzungen

- Windows 10/11
- Python 3.10+ ([python.org](https://python.org))
- Intel CPU/GPU (Arc, Iris Xe, UHD) – CPU reicht auch als Fallback

## Installation (einmalig)

Doppelklick auf `install.bat`

Oder manuell:
```
pip install faster-whisper openvino soundfile
```

## Workflow

### 1. OGG-ZIP von Linux holen

Auf der Linux-Maschine liegt die ZIP in `02_upload/`:
```
02_upload/Pocketwissen_Feuerwehr_ogg.zip
```
→ Auf den Windows-PC kopieren (USB, Netzwerk etc.)

### 2. Transkription starten

```
run.bat Pocketwissen_Feuerwehr_ogg.zip
```

Oder mit kleinerem Modell (schneller, etwas ungenauer):
```
run.bat Pocketwissen_Feuerwehr_ogg.zip small
```

Direkt mit Python:
```
python transcribe.py Pocketwissen_Feuerwehr_ogg.zip --model large-v3-turbo
```

### 3. Transcript-ZIP zurück auf Linux kopieren

Output: `Pocketwissen_Feuerwehr_transcripts.zip` (gleicher Ordner wie Eingabe)

Auf Linux entpacken:
```bash
unzip -o Pocketwissen_Feuerwehr_transcripts.zip \
    -d ~/tiptoi-translate/03_transcripts/Pocketwissen_Feuerwehr/
```

### 4. Pipeline weiter laufen lassen

```bash
cd ~/tiptoi-translate && source .venv/bin/activate
python pipeline.py 01_input/Pocketwissen_Feuerwehr.gme --language ch --skip-assemble
```

## Modelle und Geschwindigkeit (Intel iGPU, ca.)

| Modell | Qualität | ~Zeit für 580 OGGs |
|--------|----------|---------------------|
| `small` | gut | ~15–30 Min |
| `medium` | sehr gut | ~40–80 Min |
| `large-v3-turbo` | beste | ~60–120 Min |

*Mit OpenVINO auf Intel Arc/Iris: deutlich schneller als CPU allein.*

## Fehlerbehebung

**`ModuleNotFoundError: faster_whisper`**
→ `install.bat` nochmal ausführen

**OpenVINO schlägt fehl, fällt auf CPU zurück**
→ Normal – läuft weiter auf CPU, nur langsamer

**Kein Ton / leere Transkripte**
→ OGG-Dateien sind Geräusche (kein Sprache) – das ist korrekt, Pipeline überspringt diese

## Versions-Kompatibilität

`VERSION = "v30"` muss mit `PIPELINE_VERSION` in `pipeline.py` übereinstimmen.
Bei Versions-Wechsel: `transcribe.py` Zeile 18 anpassen.
