# Tiptoi DE→FR Übersetzer – Projektbeschreibung

## 🚨 SICHERHEIT – NIEMALS COMMITTEN!

**`colab_pipeline_v19.ipynb` enthält einen echten HuggingFace-Token (Zeile 117):**
```
HF_TOKEN = 'hf_XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX'
```
→ **Vor jedem `git add` / `git commit` prüfen, dass diese Datei in `.gitignore` steht!**
→ Auch alle anderen `colab_pipeline_v*.ipynb` Dateien können Tokens enthalten.
→ `.env` enthält Mistral API Key → ebenfalls NIEMALS committen.

**Bevor ein Git-Repo angelegt wird:** Token im Notebook durch Platzhalter ersetzen!

## ⚠️ WICHTIG – Immer zuerst lesen!

**Die Pipeline ist noch nicht vollständig debuggt.** Zu Beginn jeder Session darauf hinweisen:

> Bevor neue Bücher verarbeitet werden: erst **ein einzelnes Buch komplett durchlaufen und debuggen**.
> Vorher alle alten Ausgaben löschen:
> ```bash
> rm -rf 02_unpacked/{BUCH} 03_transcripts/{BUCH} 04_translated/{BUCH} 05_tts_output/{BUCH} 06_output/{BUCH}*.gme
> ```
> Erst wenn dieses Buch fehlerfrei von Anfang bis Ende durchläuft → andere Bücher starten.

## Was macht dieses Projekt?

Dieses Projekt übersetzt Tiptoi-Bücher (Ravensburger) automatisch von
Deutsch nach Französisch oder Schweizerdeutsch. Es nimmt eine GME-Datei,
tauscht alle Audiodateien aus und erzeugt eine neue GME-Datei.

## Workflow (6 Schritte)

1. **GME entpacken** – `tttool export` (YAML) + `tttool media` (OGG-Dateien)
2. **Transkription** – faster-whisper (Modell: small), Sprache: DE
3. **Übersetzung** – Mistral API (`mistral-medium-latest` FR / `mistral-large-latest` CH), DE→Zielsprache
4. **TTS** – edge-tts, Stimme: `fr-FR-VivienneMultilingualNeural` (FR-Standard)
5. **OGG-Konvertierung** – ffmpeg, Mono, 22050 Hz (Tiptoi-Format)
6. **GME neu packen** – `tttool assemble`

## Regeln für Code-Änderungen

Nach **jeder** Änderung an einem Skript oder Notebook immer beide Schritte ausführen:

1. **Backup** – aktuelle Version in `backup/` speichern (Versionsnummer fortlaufend erhöhen)
2. **Changelog** – Eintrag in `CHANGELOG.md` mit neuer Versionsnummer, Datum und allen Änderungen

## Vor jedem Start prüfen

- **Swap aktiv?** → `swapon --show` muss `/dev/sdb1` mit ~15GB zeigen. Falls nicht: `sudo swapon /dev/sdb1`
- **Monitor läuft?** → `pgrep -f monitor.sh` – falls nicht: `nohup bash ~/tiptoi-translate/monitor.sh > /dev/null 2>&1 &`

## Wichtige Details

- tttool-Befehle: `export` (nicht `unpack`), `media` (nicht `extract`)
- tttool 1.11 liegt unter `~/.local/bin/tttool`
- Python venv unter `.venv/` – immer aktivieren mit `source .venv/bin/activate`
- Haupt-Startskript: `./tiptoi.sh 01_input/datei.gme`
- Mistral Rate Limit: Pipeline hat automatischen Retry + 0.5s Pause pro Anfrage
- Pipeline unterstützt Fortsetzen: bereits übersetzte Dateien werden übersprungen
- Am Ende `tttool set-language FRENCH 06_output/*.gme` nicht vergessen!
- ffmpeg-Fehler und leere MP3s werden übersprungen (kein Abbruch mehr)

## Tiptoi-Stift (USB)

- Mountpoint: `/media/dom/tiptoi` (3,6 GB, FAT32, Label: `tiptoi`)
- Gerät: `/dev/sdc`
- Inhalt: ~90 GME-Dateien, hauptsächlich französische Bücher
- GME-Dateien direkt von dort kopieren oder nach dem Packen dorthin kopieren

## Ordnerstruktur (in Verarbeitungsreihenfolge)

```
01_input/       – GME-Eingabedateien
02_unpacked/    – tttool-Output (YAML + media/)
03_transcripts/ – Whisper-Transkripte (DE)
04_translated/  – Mistral-Übersetzungen – auch für Resume genutzt
05_tts_output/  – edge-tts MP3-Dateien
06_output/      – fertige *_fr.gme / *_ch.gme Dateien
backup/         – Skript-Versionen mit Changelog
```

## Bekannte Eigenheiten

- tttool überschreibt bestehende YAML nicht → Pipeline löscht sie vorher
- Leer-Audiodateien (Stille) werden korrekt übersprungen (leeres Transkript)
- edge-tts kann 0-Byte-MP3s erzeugen → Pipeline erkennt und überspringt diese
- TTS-Qualität: `fr-FR-VivienneMultilingualNeural` > `fr-FR-DeniseNeural`

## Stack

- Python 3.13, faster-whisper, mistralai, edge-tts, python-dotenv
- tttool 1.11 (Haskell-Binary)
- ffmpeg 7.1

## TODO / Offene Ideen (besprechen ab ~4. März)

### Größeres Whisper-Modell
`small` macht zu viele Transkriptionsfehler bei ähnlich klingenden Wörtern
(Beispiel: „rücklich" statt „rötlich", „Fifferlinge" statt „Pfifferlinge").
→ Auf `medium` oder `large-v3-turbo` wechseln, sobald Windows-GPU-Maschine
  verfügbar ist (dort läuft large-v3-turbo in Sekunden statt Stunden).
→ Alle bereits transkribierten Bücher müssen dann **neu transkribiert** werden
  → `MIN_RESUME_VERSION` auf aktuelle Version setzen (invalidiert alte Transkripte)

**Option: Google Colab (kostenlos) für Transkription**
- T4-GPU in Colab: `large-v3-turbo` ~1–2s pro Datei statt Minuten lokal
- Kein Code-Umbau nötig: nur Schritt 2 (Transkription) in Colab ausführen,
  TXT-Dateien in `03_transcripts/{buch}/` ablegen, Rest läuft lokal weiter
- Gratis-Limit: ~12h/Tag, Session bricht nach ~1–2h Inaktivität ab
- Alternative kostenpflichtig: RunPod/Modal (~0,20–0,40€/h A100), vollautomatisch
- Colab-Notebook könnte OGGs direkt verarbeiten und TXTs zurückliefern
  → bei Bedarf erstellen

### Sprecher-Erkennung: Pyannote.audio via HuggingFace API
Die aktuelle `analyze_speakers()`-Funktion nutzt `librosa.yin` (Pitch-Analyse)
mit K-Means-Clustering. Das ist **sehr langsam** (~Stunden für 1000+ Dateien).

**Bessere Alternative: Pyannote.audio**
- State-of-the-Art Speaker Diarization
- Erkennt automatisch: wie viele Sprecher + wer spricht wann (mit Timestamps)
- Kostenlos über HuggingFace API (HF-Token nötig)
- Viel genauer als Pitch-Schätzung, läuft online/parallel
- Liefert direkt: `{datei: sprecher_id}` → Voice-Zuweisung ohne lokales Clustering
- `pip install pyannote.audio`
- Docs: https://github.com/pyannote/pyannote-audio
