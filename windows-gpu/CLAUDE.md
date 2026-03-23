# Windows GPU Transkriptions-Tool – Projektbeschreibung

## Was macht dieses Tool?

Ersatz für den Colab-Whisper-Schritt: transkribiert Tiptoi-OGGs auf dem Windows-PC
mit Intel GPU (OpenVINO) oder CPU. Output ist ein ZIP kompatibel mit `pipeline.py`.

## Dateien

- `transcribe.py` – Hauptskript (Whisper, ZIP in/out)
- `install.bat` – Einmalige Installation der Python-Pakete
- `run.bat` – Einfacher Start per Doppelklick

## Workflow

```
Linux: 02_upload/BUCH_ogg.zip
  → Windows: run.bat BUCH_ogg.zip
  → Windows: BUCH_transcripts.zip
  → Linux: 03_transcripts/BUCH/ (entpacken)
  → Linux: python pipeline.py ... --skip-assemble
  → Linux: python gme_patcher/gme_patch.py ...
```

## Technische Details

- `faster-whisper` mit `device="openvino"` für Intel GPU
- Fallback: `device="cpu"` mit `compute_type="int8"`
- `pick_device()`: versucht OpenVINO, dann CPU – niemals Crash
- Output-Format identisch mit Colab: `{stem}_{VERSION}.txt` + `{stem}_{VERSION}_ts.json`
- `VERSION = "v30"` – muss mit `PIPELINE_VERSION` in `pipeline.py` übereinstimmen

## Unterschied zu Colab

| Feature | Colab | Windows |
|---------|-------|---------|
| GPU | NVIDIA T4 | Intel (OpenVINO) |
| Sprecher-Analyse | pyannote ✓ | ✗ (nicht enthalten) |
| speakers.json | ✓ im ZIP | ✗ |
| Resume | ✓ | ✓ |

**speakers.json fehlt:** Die Pipeline nutzt dann lokales resemblyzer-Clustering.
Für optimale Stimmverteilung weiterhin Colab bevorzugen.

## Debugging-Regeln

1. Bei OpenVINO-Fehler: prüfe ob `pip install openvino` durchgelaufen ist
2. Bei leeren Transkripten: Normal für Geräusch-OGGs (kein Bug)
3. Bei `VERSION`-Mismatch: `transcribe.py` Zeile 18 anpassen
4. Bei Windows-Pfad-Problemen: Pfade in Anführungszeichen übergeben

## Versions-Historie

| Version | Datum | Änderungen |
|---------|-------|------------|
| v1 | 2026-03-22 | Initial: OpenVINO + CPU-Fallback, ZIP I/O, ts.json |
