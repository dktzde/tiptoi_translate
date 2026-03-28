# Tiptoi DE → FR / CH / VO / BY / ND Übersetzer

Ein persönliches Bastelprojekt: Tiptoi-Bücher (Ravensburger) automatisch
von Deutsch in eine andere Sprache übersetzen. Nimmt eine GME-Datei,
tauscht die Audiodateien aus und erzeugt eine neue abspielbare GME-Datei.

Unterstützte Zielsprachen: Französisch, Schweizerdeutsch, Vogtländisch,
Bairisch, Plattdeutsch.

> **Hinweis:** Das ist kein offizielles Tool und kein fertig poliertes Produkt.
> Es funktioniert für meinen Anwendungsfall — aber es gibt sicher Bücher,
> bei denen es hakt. Feedback und Verbesserungen sind willkommen.

---

## Abhängigkeit von tttool und tip-toi-reveng

Dieses Projekt baut vollständig auf der Arbeit der
[tip-toi-reveng](https://github.com/entropia/tip-toi-reveng)-Community auf.
Ohne `tttool` (GME entpacken, YAML, assemble) und die dort dokumentierten
Formatdetails wäre dieses Projekt nicht möglich.

---

## Warum Google Colab für die Transkription?

Mein PC hat keine GPU, also kein CUDA. Whisper läuft damit ausschließlich auf der CPU.

Ein typisches Tiptoi-Buch hat **1.000–2.000 OGG-Dateien**. Mit dem
`small`-Modell auf CPU dauert die Transkription mehrere Stunden; das
genauere `large-v3-turbo`-Modell wäre lokal praktisch unbenutzbar.

**Lösung: Schritt 2 (Transkription) auf Google Colab auslagern.**
Colab stellt kostenlos eine NVIDIA T4-GPU zur Verfügung – dort läuft
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
| 3 | Übersetzung DE → Zielsprache | Mistral API (`magistral-medium-latest`) |
| 4 | TTS | edge-tts |
| 5 | OGG-Konvertierung | ffmpeg (Mono, 22050 Hz) |
| 6 | GME neu packen | `tttool assemble` oder `gme_patch.py` (Binary-Patch) |

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

## Verwendung

```bash
# GME in 01_input/ ablegen, dann:
./tiptoi.sh 01_input/buch.gme

# Schweizerdeutsch
./tiptoi.sh 01_input/buch.gme --language ch

# Bairisch
./tiptoi.sh 01_input/buch.gme --language by

# Vogtländisch
./tiptoi.sh 01_input/buch.gme --language vo

# Plattdeutsch
./tiptoi.sh 01_input/buch.gme --language nd

# Binary-Patch (erhält Spiele-Logik, experimentell):
./tiptoi.sh 01_input/buch.gme --use-patcher

# Nur ersten 10 Dateien (Testlauf)
./tiptoi.sh 01_input/buch.gme --limit 10

# Größeres Whisper-Modell
./tiptoi.sh 01_input/buch.gme --whisper-model medium
```

Die fertige Datei liegt danach in `06_output/buch_fr.gme` (bzw. `_ch`, `_vo`, `_by`, `_nd`).
Resume funktioniert automatisch – einfach denselben Befehl erneut ausführen.

### Alle Parameter

```bash
python pipeline.py 01_input/buch.gme [OPTIONEN]

  --language SPRACHE      Zielsprache: fr, ch, vo, by, nd
                          Standard: fr

  --voice STIMME          edge-tts Stimme (überschreibt Sprachstandard)

  --whisper-model MODELL  Whisper-Modell: tiny, base, small, medium, large-v3-turbo
                          Standard: small

  --limit N               Nur die ersten N Audiodateien verarbeiten
                          (0 = alle, nützlich für Testläufe)

  --use-patcher           [experimentell] Schritt 6 via gme_patch.py statt tttool assemble
                          (erhält Spiele-Logik per Binary-Patch)

  --skip-assemble         Schritt 6 überspringen (OGGs bleiben für manuellen Patch)

  --offline               Alles lokal ausführen (kein Colab-Pause)

  --min-k N               Mindestanzahl Sprecher-Cluster (Standard: 2)
```

---

## Dialekte: ein Hinweis

**Schweizerdeutsch** funktioniert erfahrungsgemäß gut — die CH-Stimmen von
edge-tts klingen überzeugend und Mistral übersetzt solide ins Schweizerdeutsche.

**Vogtländisch, Bairisch und Plattdeutsch** klingen leider weitgehend wie
Hochdeutsch. Echte Dialekt-TTS-Stimmen gibt es dafür nicht; die verfügbaren
Stimmen (DE/AT/CH) geben den Dialektcharakter kaum wieder. Auch die
Übersetzungsqualität von Mistral ist für diese Dialekte eingeschränkt.
Diese Sprachoptionen sind daher eher experimentell.

---

## Stimmen (8 pro Sprache)

Jede Sprache hat 8 edge-tts-Stimmen (4m/4f). Sprecher werden automatisch
via **resemblyzer** (GE2E Embeddings) erkannt und den Stimmen zugeordnet.
Das Ergebnis wird als `speakers.json` pro Buch gespeichert.

**Französisch (`--language fr`)**

| # | Stimme | Typ |
|---|--------|-----|
| 0 | `fr-FR-HenriNeural` | m, tiefer Erzähler |
| 1 | `fr-FR-EloiseNeural` | f, Kinderstimme |
| 2 | `fr-BE-CharlineNeural` | f, belgisch (Kind 2) |
| 3 | `fr-FR-RemyMultilingualNeural` | m, natürlich |
| 4 | `fr-FR-VivienneMultilingualNeural` | f, Erzählerin |
| 5 | `fr-FR-DeniseNeural` | f, warm/reif |
| 6 | `fr-BE-GerardNeural` | m, belgisch |
| 7 | `fr-CH-FabriceNeural` | m, Schweizer FR |

**Schweizerdeutsch (`--language ch`)**

| # | Stimme | Typ |
|---|--------|-----|
| 0 | `de-CH-JanNeural` | m, Schweizerdeutsch |
| 1 | `de-CH-LeniNeural` | f, Schweizerdeutsch |
| 2 | `de-AT-JonasNeural` | m, Österreichisch |
| 3 | `de-AT-IngridNeural` | f, Österreichisch |
| 4 | `de-DE-FlorianMultilingualNeural` | m, multilingual |
| 5 | `de-DE-SeraphinaMultilingualNeural` | f, multilingual |
| 6 | `de-DE-ConradNeural` | m, Hochdeutsch |
| 7 | `de-DE-KatjaNeural` | f, Hochdeutsch |

**Vogtländisch (`--language vo`)**

| # | Stimme | Typ |
|---|--------|-----|
| 0 | `de-DE-FlorianMultilingualNeural` | m, multilingual |
| 1 | `de-DE-SeraphinaMultilingualNeural` | f, multilingual |
| 2 | `de-DE-ConradNeural` | m |
| 3 | `de-DE-KatjaNeural` | f |
| 4 | `de-DE-KillianNeural` | m |
| 5 | `de-DE-AmalaNeural` | f |
| 6 | `de-CH-JanNeural` | m |
| 7 | `de-AT-IngridNeural` | f |

**Bairisch (`--language by`)**

| # | Stimme | Typ |
|---|--------|-----|
| 0 | `de-AT-JonasNeural` | m, Österreichisch |
| 1 | `de-AT-IngridNeural` | f, Österreichisch |
| 2 | `de-DE-FlorianMultilingualNeural` | m, multilingual |
| 3 | `de-DE-SeraphinaMultilingualNeural` | f, multilingual |
| 4 | `de-CH-JanNeural` | m |
| 5 | `de-CH-LeniNeural` | f |
| 6 | `de-DE-ConradNeural` | m |
| 7 | `de-DE-KatjaNeural` | f |

**Plattdeutsch (`--language nd`)**

| # | Stimme | Typ |
|---|--------|-----|
| 0 | `de-DE-FlorianMultilingualNeural` | m, multilingual |
| 1 | `de-DE-SeraphinaMultilingualNeural` | f, multilingual |
| 2 | `de-DE-KillianNeural` | m |
| 3 | `de-DE-KatjaNeural` | f |
| 4 | `de-DE-ConradNeural` | m |
| 5 | `de-DE-AmalaNeural` | f |
| 6 | `de-AT-JonasNeural` | m |
| 7 | `de-CH-LeniNeural` | f |

---

## Ordnerstruktur

```
01_input/       GME-Eingabedateien
02_unpacked/    tttool-Output (YAML + OGG)
03_transcripts/ Whisper-Transkripte (DE)
04_translated/  Mistral-Übersetzungen
05_tts_output/  edge-tts MP3-Dateien
06_output/      Fertige *_fr / *_ch / *_vo / *_by / *_nd .gme
backup/         Versionierte Skript-Backups
```

---

## Stack

- Python 3.13, faster-whisper, mistralai (Magistral), edge-tts, resemblyzer, python-dotenv
- tttool 1.11 (Haskell-Binary, von der tip-toi-reveng-Community)
- gme_patch.py / gme_patch_same_lenght.py (Binary-Patch, experimentell)
- ffmpeg 7.1

---

## Danke

Dieses Projekt wäre ohne die Vorarbeit der
[tip-toi-reveng](https://github.com/entropia/tip-toi-reveng)-Community
nicht möglich — insbesondere die vollständige GME-Format-Dokumentation,
`tttool` und `libtiptoi.c` (Michael Wolf). Vielen Dank für die jahrelange
Reverse-Engineering-Arbeit.

---

## Lizenz

MIT License — siehe [LICENSE](LICENSE)
