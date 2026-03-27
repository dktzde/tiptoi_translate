# Changelog – gme_patch_same_lenght.py

## v6 – 2026-03-27

### Bugfix: Qualitätsreduktion + atempo wurden fälschlich von else-Branch überschrieben
- **Bug:** `if method not in ("atempo", "quality") and over_pct > max_diff: … else: truncate`
  → `else` feuerte auch wenn atempo/quality bereits erfolgreich war (da `if`-Bedingung False)
  → jede erfolgreich komprimierte Datei wurde zusätzlich truncated
- **Fix:** Umstrukturierung zu `if method not in (...): if over_pct > max_diff: … else: truncate`
  → Qualitätsreduktion und atempo werden jetzt korrekt als Endergebnis akzeptiert

### Neu: Qualitätsreduktion als Schritt 2 (zwischen atempo und interaktiv)
- `_reencode_lower_quality(raw, max_bytes)`: probiert q=3,2,1,0,-1 iterativ
- Gleiche Dauer wie Original – kein Inhaltsverlust, nur geringere Bitrate
- Fügt sich ein: atempo → quality → interaktiv/truncate

### Neu: DE-Transkript-Lookup statt Whisper (Option 3)
- `_find_transcript(stem, transcripts_dir)`: liest aus `03_transcripts/{buch}/`
- Kein lokaler Whisper-Lauf nötig – Text kommt aus der Pipeline

### Alle 5 Sprachen in LANG_CONFIG
- fr, ch, vo, by, nd – je mit `voices`-Liste und `shorten_prompt`

### pipeline.py Integration: `--use-patcher-sl`
- `sl_lang` Fallback auf "fr" wenn Sprache nicht in LANG_CONFIG (by/vo/nd → fr)
- Wird mit `max_diff=float("inf")` aufgerufen (nie interaktiv)

### Log-Datei
- `_write_log()` schreibt `{output_gme.stem}.log` neben die Ausgabe-GME
- Format: idx / method / orig_bytes / new_bytes / voice / stem

---

## v4 – 2026-03-26

### shift=0 erzwungen – Spieldaten bleiben immer bitgenau
- **Jedes Ersatz-Audio wird auf exakt die Originalgröße gebracht**
- Kürzer → Null-Padding (OGG-Decoder ignoriert Trailing Zeros)
- Bis `--max-diff` (default 20%) zu groß → atempo (lautlos, kein User-Input)
- Über `--max-diff` → interaktive Nachbesserung mit 3 Optionen:
  - [1] Beide anhören + kürzeren deutschen Text eingeben → Mistral → Edge-TTS
  - [2] Dauer-Reduktion (ffmpeg -t)
  - [3] Auto-Kürzung: STT (faster-whisper) → Mistral kürzt Text → Edge-TTS
    ← wird nach 3 Minuten automatisch gewählt

### Stimmen pro Datei (--speakers-json)
- Lädt `speakers.json` (Format aus pipeline.py / analyze_speakers_resemblyzer.py)
- Jede Audio-Datei erhält die korrekte Edge-TTS Stimme (Erzähler, Kind, etc.)
- Ohne `--speakers-json`: alle Dateien nutzen `--voice` (Fallback)

### Neue CLI-Parameter
- `--max-diff RATIO` (default 0.20): Schwelle für interaktive Nachbesserung
- `--speakers-json PATH`: Stimmen-Zuordnung aus pipeline.py
- `--voice`: Fallback-Stimme (wenn kein speakers.json oder Datei nicht darin)
- `--lang`: Zielsprache fr/ch
- `-h` / `--help`: vollständige Hilfe (argparse)
- `-i` / `--info`: GME-Datei-Informationen anzeigen

### Neues Skript: retranslate_oversized.py
- Eigenständig aufrufbar (CLI) oder als Modul (import)
- Option 3 (Auto-Kürzung): STT → Mistral Textkürzung → Edge-TTS
- 3 Minuten Timeout → automatisch Option 3
- Event-Loop-sicher (kein Crash bei Aufruf aus pipeline.py --use-patcher)
- Alle OGG-Kürzungen via ffmpeg Dauer-Reduktion (kein Byte-Schnitt)
- LANG_CONFIG mit Voices-Listen und Shorten-Prompts pro Sprache

### Bug-Ursache v3
- v3 Zeiger-Scan verschob alle uint32-Werte die zufällig im Post-Audio-Range
  lagen – auch Spieldaten, Zähler, Bytecode → Loops, Wiederholungen, Abstürze

### Abhängigkeiten
- `retranslate_oversized.py`: mistralai, edge-tts, emoji, python-dotenv, faster-whisper
- ffmpeg + ffplay + ffprobe
- gme_patch.py selbst: nur Python stdlib + ffmpeg

### Files
- `gme_patch.py` v4
- `retranslate_oversized.py` (neu)
- `backup/gme_patch_v4.py`

---

## v3 – 2026-03-22

### Bugfix (kritisch)
- Post-Audio-Daten (Binaries, Single Binaries, Special Symbols) werden mitgenommen
- Absolute Zeiger auf Post-Audio-Daten werden im Header + Binary-Headern verschoben
- `last_audio_end` korrekt als `max(offset + length)` berechnet

---

## v2 – 2026-03-22
- Namenskonvention `_p_vN` dokumentiert

---

## v1 – 2026-03-21
- Initial: Parse, XOR, Replace, Duplikate, Checksum, -i Info-Modus
