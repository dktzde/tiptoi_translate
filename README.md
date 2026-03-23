# Tiptoi DE → FR / CH Übersetzer

Übersetzt Tiptoi-Bücher (Ravensburger) automatisch von Deutsch nach
**Französisch** oder **Schweizerdeutsch**. Nimmt eine GME-Datei, tauscht
alle Audiodateien aus und erzeugt eine neue abspielbare GME-Datei.

---

## Warum Google Colab für die Transkription?

Der lokale Linux-PC hat eine **Intel Haswell-GPU (2013)** – zu alt für
OpenVINO (min. Skylake 6th Gen erforderlich) und kein NVIDIA-Chip, also
kein CUDA. Whisper läuft damit ausschließlich auf der CPU.

Ein typisches Tiptoi-Buch hat **1.000–2.000 OGG-Dateien**. Mit dem
`small`-Modell auf CPU dauert die Transkription **mehrere Stunden**; das
genauere `large-v3-turbo`-Modell wäre lokal **praktisch unbenutzbar**.

**Lösung: Schritt 2 (Transkription) auf Google Colab auslagern.**
Colab stellt kostenlos eine **NVIDIA T4-GPU** zur Verfügung – dort läuft
`large-v3-turbo` ca. 1–2 Sekunden pro Datei statt Minuten. Die fertigen
TXT-Transkripte werden zurück in `03_transcripts/` gelegt; alle anderen
Schritte laufen weiterhin lokal.

```
Lokaler PC:  GME entpacken → OGGs zippen → hochladen
Colab:       OGGs entpacken → Whisper large-v3-turbo → TXTs zippen → runterladen
Lokaler PC:  TXTs entpacken → Übersetzen → TTS → GME packen
```

---

## Workflow (6 Schritte)

| Schritt | Beschreibung | Tool |
|---------|-------------|------|
| 1 | GME entpacken (YAML + OGG) | `tttool export` / `tttool media` |
| 2 | Transkription DE | faster-whisper (`small` lokal / `large-v3-turbo` Colab) |
| 3 | Übersetzung DE → Zielsprache | Mistral API |
| 4 | TTS | edge-tts |
| 5 | OGG-Konvertierung | ffmpeg (Mono, 22050 Hz) |
| 6 | GME neu packen | `tttool assemble` |

---

## Voraussetzungen

- Python 3.13+
- ffmpeg 7.1+ (`sudo apt install ffmpeg`)
- tttool 1.11 unter `~/.local/bin/tttool`
  → Download: https://github.com/entropia/tip-toi-reveng/releases
- Mistral API Key (https://console.mistral.ai/)

---

## Einmalige Einrichtung

```bash
# tttool installieren
mkdir -p ~/.local/bin
cp tttool ~/.local/bin/tttool
chmod +x ~/.local/bin/tttool

# Python-Umgebung
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# API Key
cp .env.example .env
nano .env   # MISTRAL_API_KEY=dein_key_hier
```

---

## Vor jedem Start prüfen

```bash
# Swap aktiv? (wird für große Bücher benötigt)
swapon --show   # → muss /dev/sdb1 ~15 GB zeigen
# Falls nicht:
sudo swapon /dev/sdb1

# RAM-Monitor läuft?
pgrep -f monitor.sh
# Falls nicht:
nohup bash ~/tiptoi-translate/monitor.sh > /dev/null 2>&1 &
```

---

## Verwendung

```bash
# GME in 01_input/ ablegen, dann:
./tiptoi.sh 01_input/buch.gme

# Schweizerdeutsch
./tiptoi.sh 01_input/buch.gme --language ch

# Nur ersten 10 Dateien (Testlauf)
./tiptoi.sh 01_input/buch.gme --limit 10

# Größeres Whisper-Modell
./tiptoi.sh 01_input/buch.gme --whisper-model medium
```

Die fertige Datei liegt danach in `06_output/buch_fr.gme`.
Resume funktioniert automatisch – einfach denselben Befehl erneut ausführen.

### Alle Parameter

```bash
python pipeline.py 01_input/buch.gme [OPTIONEN]

  --language SPRACHE      Zielsprache: fr (Französisch) oder ch (Schweizerdeutsch)
                          Standard: fr

  --voice STIMME          edge-tts Stimme (überschreibt Sprachstandard)

  --whisper-model MODELL  Whisper-Modell: tiny, base, small, medium, large-v3-turbo
                          Standard: small

  --limit N               Nur die ersten N Audiodateien verarbeiten
                          (0 = alle, nützlich für Testläufe)
```

---

## Nach dem Lauf

```bash
# Sprache in der GME setzen (nötig für Tiptoi-Stift):
~/.local/bin/tttool set-language FRENCH 06_output/buch_fr.gme
```

Resume: Einfach denselben Befehl nochmal ausführen – bereits vorhandene
Transkripte, Übersetzungen und MP3s werden übersprungen.

---

## Direkter Python-Aufruf

```bash
source .venv/bin/activate
python pipeline.py 01_input/buch.gme --language fr
```

---

## Stimmen

**Französisch (`--language fr`)**

| Stimme | Typ |
|--------|-----|
| `fr-FR-HenriNeural` | Männlich, tief (Erzähler) |
| `fr-FR-VivienneMultilingualNeural` | Weiblich, natürlich |
| `fr-FR-RemyMultilingualNeural` | Männlich, natürlich |
| `fr-FR-EloiseNeural` | Weiblich, Kinderstimme |

**Schweizerdeutsch (`--language ch`)**

| Stimme | Typ |
|--------|-----|
| `de-CH-JanNeural` | Männlich |
| `de-CH-LeniNeural` | Weiblich |
| `de-AT-JonasNeural` | Männlich, Österreichisch |

Sprecher werden automatisch via **resemblyzer** (GE2E Embeddings) erkannt
und den Stimmen zugeordnet. Das Ergebnis wird als `speakers.json` pro Buch
gespeichert und bei weiteren Sprachen wiederverwendet.

---

## Ordnerstruktur

```
01_input/       GME-Eingabedateien
02_unpacked/    tttool-Output (YAML + OGG)
03_transcripts/ Whisper-Transkripte (DE)
04_translated/  Mistral-Übersetzungen
05_tts_output/  edge-tts MP3-Dateien
06_output/      Fertige *_fr.gme / *_ch.gme
backup/         Versionierte Skript-Backups
```

---

## Stack

- Python 3.13, faster-whisper, mistralai, edge-tts, resemblyzer, python-dotenv
- tttool 1.11 (Haskell-Binary)
- ffmpeg 7.1
