TIPTOI DE → FR / CH ÜBERSETZER
================================

Übersetzt Tiptoi-Bücher (Ravensburger) von Deutsch nach Französisch oder
Schweizerdeutsch. Nimmt eine GME-Datei, tauscht alle Audiodateien aus
und erzeugt eine neue GME-Datei.

Workflow:
  GME entpacken → Sprecher-Analyse (resemblyzer) → Transkription (Whisper)
  → Übersetzung (Mistral) → TTS (edge-tts) → OGG-Konvertierung → GME packen


VORAUSSETZUNGEN
---------------
- Python 3.13+
- ffmpeg 7.1+          (sudo apt install ffmpeg)
- tttool 1.11          (~/.local/bin/tttool)
  Download: https://github.com/entropia/tip-toi-reveng/releases
- Mistral API Key      (https://console.mistral.ai/)


EINMALIGE EINRICHTUNG
---------------------
1. tttool installieren:
     mkdir -p ~/.local/bin
     cp tttool ~/.local/bin/tttool
     chmod +x ~/.local/bin/tttool

2. Virtuelle Umgebung & Pakete installieren:
     python3 -m venv .venv
     source .venv/bin/activate
     pip install -r requirements.txt

3. API Key eintragen:
     cp .env.example .env
     nano .env
     → MISTRAL_API_KEY=dein_key_hier

4. Skript ausführbar machen:
     chmod +x tiptoi.sh


VOR JEDEM START PRÜFEN
-----------------------
- Swap aktiv?
     swapon --show   → muss /dev/sdb1 ~15GB zeigen
     Falls nicht: sudo swapon /dev/sdb1

- RAM-Monitor läuft?
     pgrep -f monitor.sh
     Falls nicht: nohup bash ~/tiptoi-translate/monitor.sh > /dev/null 2>&1 &

- RAM-Logger läuft?
     pgrep -f ram_log.sh
     Falls nicht: nohup bash ~/tiptoi-translate/ram_log.sh > /dev/null 2>&1 &


VERWENDUNG
----------
GME-Datei in den Ordner 01_input/ kopieren, dann:

  ./tiptoi.sh 01_input/buch.gme

Das Skript aktiviert automatisch die virtuelle Umgebung.
Die fertige Datei liegt danach in 06_output/buch_fr.gme


ALLE PARAMETER
--------------
  python pipeline.py 01_input/buch.gme [OPTIONEN]

  --language SPRACHE      Zielsprache: fr (Französisch) oder ch (Schweizerdeutsch)
                          Standard: fr

  --voice STIMME          edge-tts Stimme (überschreibt Sprachstandard)
                          Standard: automatisch je nach Sprache

  --whisper-model MODELL  Whisper-Modell: tiny, base, small, medium, large-v3-turbo
                          Standard: small

  --limit N               Nur die ersten N Audiodateien verarbeiten
                          (0 = alle, nützlich für Testläufe)

Beispiele:
  ./tiptoi.sh 01_input/buch.gme
  ./tiptoi.sh 01_input/buch.gme --language ch
  ./tiptoi.sh 01_input/buch.gme --language fr --whisper-model base
  ./tiptoi.sh 01_input/buch.gme --voice fr-FR-VivienneMultilingualNeural
  ./tiptoi.sh 01_input/buch.gme --limit 10


STIMMEN
-------
Die Sprecher-Zuordnung erfolgt automatisch via resemblyzer (GE2E Embeddings).
Das Ergebnis wird als speakers.json pro Buch gespeichert und bei weiteren
Sprachen wiederverwendet. Manuelle Zuordnung via --voice überschreibt alles.

Französisch (--language fr):  [4 Stimmen, automatisch zugewiesen]
  fr-FR-HenriNeural                Männlich, tief     (Stimme 0 – Erzähler)
  fr-FR-VivienneMultilingualNeural Weiblich, natürlich (Stimme 1)
  fr-FR-RemyMultilingualNeural     Männlich, natürlich (Stimme 2)
  fr-FR-EloiseNeural               Weiblich, Kinderstimme (Stimme 3)

Schweizerdeutsch (--language ch):  [3 Stimmen, automatisch zugewiesen]
  de-CH-JanNeural                  Männlich, Schweizerdeutsch (Stimme 0)
  de-CH-LeniNeural                 Weiblich, Schweizerdeutsch (Stimme 1)
  de-AT-JonasNeural                Männlich, Österreichisch   (Stimme 2)


ORDNERSTRUKTUR (in Verarbeitungsreihenfolge)
---------------------------------------------
  01_input/       GME-Dateien hier ablegen
  02_unpacked/    Entpackte Dateien (tttool-Output: YAML + OGG)
  03_transcripts/ Deutsche Transkripte (Whisper)
  04_translated/  Übersetzte Texte (Mistral)
  05_tts_output/  Generierte MP3-Dateien (edge-tts)
  06_output/      Fertige *_fr.gme / *_ch.gme Dateien
  backup/         Versionierte Skript-Backups


NACH DEM LAUF
-------------
Sprache in der GME setzen (nötig für Tiptoi-Stift):
  ~/.local/bin/tttool set-language FRENCH 06_output/buch_fr.gme

Resume (Fortsetzen nach Abbruch):
  Einfach denselben Befehl nochmal ausführen.
  Bereits vorhandene Transkripte, Übersetzungen und MP3s werden übersprungen.


DIREKTER PYTHON-AUFRUF
-----------------------
  source .venv/bin/activate
  python pipeline.py 01_input/buch.gme --language fr
