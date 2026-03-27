# Changelog – gme_patch_same_lenght.py

## v10 – 2026-03-27

### 10%-Beschleunigung als erster Schritt

- **Neuer Schritt 0:** `_apply_speed(raw, 1.1)` beschleunigt jedes zu große Audio um 10%
  bevor quality reduction oder atempo versucht werden
- **Warum:** edge-tts spricht sehr langsam mit Pausen → 10% schneller klingt natürlicher
  UND reduziert Dateigröße um ~10% ohne Qualitätsverlust
- **Neue Reihenfolge:** speed10 → quality → quality+atempo → atempo → Retranslation → Truncate
- **speed10 allein genug:** method = `"speed10"` (neuer Methodenname im Log)
- **speed10 als Basis:** Wenn speed10 nicht reicht, wird das bereits kleinere Audio als
  Ausgangspunkt für quality reduction übergeben → weniger Qualitätsverlust nötig
- **Phase 2 (retranslated):** Gleiche Logik: speed10 → quality → quality+atempo → truncated
  Neuer Methodenname `"retranslated+speed10"` wenn speed10 allein reicht
- **Methoden-Check aktualisiert:** `"speed10"` zu den erfolgreichen Methoden hinzugefügt
- Backup: `backup/gme_patch_same_lenght_v9.py`

---

## v9 – 2026-03-27

### Batch-Retranslation + erweiterte OGG-Kompression
- **Batch-Retranslation:** `_batch_retranslate_mistral()` sammelt alle Oversized-Einträge und
  schickt sie in Gruppen (max 20 ODER 1000 Zeichen) an Mistral → drastisch weniger Rate-Limits
  (z.B. ~5 API-Calls statt 108)
- **Zwei-Phasen in `patch_gme`:** Phase 1 quality+atempo → sammle Failures → Batch-Mistral →
  Phase 2 quality+atempo auf retranslatierten TTS → truncate als letzter Ausweg
- **Zeichenziel-Formel geändert:** `min(0.90, max(0.65, (orig_len/new_len)×4))` statt starr 85%
  → Ziel jetzt immer 65–90% des DE-Textes (realistisch erreichbar, ≠ früheres ambitioniertes 28%)
- **Bugfix:** `if method not in ("atempo", "quality")` fehlte `"quality+atempo"` → Retranslation
  wurde fälschlich auch nach erfolgreichem quality+atempo gestartet
- **Erweiterte Qualitätsreduktion:** Nach q=-1 folgen nun explizite Bitraten 24k→16k→12k→8k
  (Vorbis, 22050 Hz mono). Bei 8 kbps ~5× kleiner als q=-1 → viele Fälle werden ohne Mistral lösbar
- **Log + Terminal:** Mistral-Prompt (System+User) und Response bei jedem Batch angezeigt;
  im Log: `→ Mistral: "..."` Zeile unter betroffenen Einträgen
- **`batch_prompt`** in LANG_CONFIG für alle 5 Sprachen (fr/ch/vo/by/nd)
- Backup: `backup/gme_patch_same_lenght_v8.py`

---

## v8 – 2026-03-27

### Qualitätsreduktion als Schritt 1 (vor atempo) + Kombination quality+atempo
- **Neue Reihenfolge:** quality → quality+atempo → atempo → Retranslation → Truncate
- **Warum:** Qualitätsreduktion bei 22050 Hz mono reduziert Dateigröße um ~60% ohne Speedup.
  Als Basis für atempo ermöglicht die Kombination Dateien bis ~4× Originalgröße zu retten.
  Vorher: atempo allein scheiterte ab >2×.
- **`_reencode_lower_quality` gibt jetzt `(fitted, min_quality)` zurück:**
  - `fitted`: erstes Ergebnis ≤ max_bytes (mit Padding) oder None
  - `min_quality`: Ergebnis bei q=-1 (ohne Padding, kann zu groß sein) als Basis für atempo
- **Neue Log-Methode:** `quality+atempo` (Qualitätsreduktion + Beschleunigung kombiniert)
- **Bugfix:** `_tts_to_ogg`: `asyncio.run()` schlug fehl wenn pipeline.py bereits eine Event Loop
  betrieb → `asyncio.get_running_loop()` + `ThreadPoolExecutor` als Workaround (analog
  zu `retranslate_oversized.py._text_to_ogg_bytes`)
- Backup: `backup/gme_patch_same_lenght_v7.py`

---

## v7 – 2026-03-27

### Retranslation automatisch im Pipeline-Modus
- **Bug:** `max_diff=float('inf')` → `over_pct > max_diff` immer False → `_interactive_menu` und
  damit `_retranslate()` (Option 3) niemals erreichbar → alles direkt truncated
- **Fix:** Neue erste Verzweigung `if max_diff == float('inf'):` im Oversized-Block:
  1. `_find_transcript()` → DE-Text aus `03_transcripts/{buch}/`
  2. `_retranslate()` → DE-Text → Mistral kürzt+übersetzt → Edge-TTS
  3. Ergebnis noch zu groß → `_shrink_ogg()` (atempo)
  4. Atempo auch zu groß → `_truncate_ogg_inline()` (letzter Ausweg)
  5. Kein Transkript / Mistral-Fehler → direkt `_truncate_ogg_inline()`
- **Neue Methoden im Log:** `retranslated`, `retranslated+atempo`, `retranslated+truncated`
- Max-Diff-Anzeige: bei `inf` zeigt Hinweis "Pipeline: Retranslation → Truncate"
- **Bugfix:** `_extract_text()` für `magistral-medium-latest`: Content kommt als Liste von Blöcken
  (reasoning + text) – `.strip()` auf Liste schlug fehl; analog zu `pipeline.py._extract_text()`
- **Rate-Limit-Retry:** `_shorten_translate_mistral` wartet bei 429 nun 60s/90s/180s (3 Versuche);
  0.5s Sleep nach jedem erfolgreichen Aufruf zum Schonen des Rate Limits
- `import time` hinzugefügt
- Backup: `backup/gme_patch_same_lenght_v6.py`

---

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
