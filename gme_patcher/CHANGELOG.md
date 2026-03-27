# Changelog – gme_patch.py

## v6 – 2026-03-27

### Bugfix (kritisch): Duplikat-Struktur bewahren + Duplikate korrekt ersetzen

**2 Ursachen für Stift-Absturz bei Feuerwehr BY (experimentell):**

1. **Duplikate nicht ersetzt (v5-Bug):** tttool exportiert nur kanonische
   Indices. Duplikat-Einträge (gleicher Offset) bekamen keinen Ersatz →
   spielten Original-DE statt Zielsprache. 511/1160 statt 1022/1160 ersetzt.

2. **Duplikat-Struktur zerstört (v5+v6-früher Bug):** v5 gab jedem Eintrag
   eine eigene Audio-Kopie → Entries 580–1159 hatten andere Offsets als 0–579.
   Die Zusatz-Audio-Tabelle bei 0x0060 zeigt auf Entry 580 (= Mitte der
   Tabelle). Der Stift erwartet dort eine exakte Kopie von Entries 0–579.
   → 0/580 Einträge identisch → Stift-Absturz bei Spiel-Interaktion.

### Fix: `_prepare_audio()` – gemeinsame Funktion für beide Modi

- Neue Funktion `_prepare_audio()` erzeugt nur einzigartige Audio-Blobs
- Duplikate teilen sich denselben Offset wie ihr kanonischer Eintrag
- Audio-Tabelle bewahrt exakt die Duplikat-Struktur des Originals
- Ergebnis: 580/580 identische Eintragspaare (wie Original)
- Dateigröße: 26 MB statt 54 MB (kein doppeltes Audio)
- Shift: +12 MB statt +39 MB

### Files
- `gme_patch.py` v6
- `backup/gme_patch_v6.py`

---

## v5 – 2026-03-26

### Vollständige Post-Audio Pointer-Abdeckung

**Ursache:** v4 korrigierte nur 3 Header-Pointer (0x005C, 0x0064, 0x0068) –
alle drei waren bei Feuerwehr NULL. Die tatsächlichen 7 Post-Audio-Pointer
(0x0090–0x00CC) blieben unbehandelt → experimenteller Modus konnte nicht
funktionieren.

### Erweitert: 11 bekannte Header-Offsets

Neues `_POST_AUDIO_HEADERS`-Dictionary mit allen bekannten Offsets aus
GME-Format.md / tttool GMEParser.hs:

| Offset | Name | Typ |
|--------|------|-----|
| `0x005C` | Binaries 1 | Tabelle (count + Einträge) |
| `0x0064` | Single-Binaries | Tabelle (count + Einträge) |
| `0x0068` | Special Symbols | Tabelle (count + Einträge) |
| `0x008C` | Media Flags | Direkt-Pointer |
| `0x0090` | Game Binaries 2 | Tabelle (count + Einträge) |
| `0x0094` | Special OID List | Direkt-Pointer |
| `0x0098` | Game Binaries 3 | Tabelle (count + Einträge) |
| `0x00A0` | Single Binary 1 | Direkt-Pointer |
| `0x00A8` | Single Binary 2 | Direkt-Pointer |
| `0x00C8` | Single Binary 3 | Direkt-Pointer |
| `0x00CC` | Binaries Table 4 | Tabelle (count + Einträge) |

### Verbessert: `_shift_binary_table` (Scan-Ansatz)

- Nimmt `table_start` direkt entgegen (statt den Wert selbst zu lesen)
- Scan-Bereich: `count × 16 Bytes` ab `table_start + 4`
- Nur Werte im Bereich `[old_audio_end, orig_file_size)` werden verschoben
- Sicher, da Name-Strings und Lengths nie in diesem Adressbereich liegen

### Verbessert: `info_gme`

- Zeigt alle 11 bekannten Header-Pointer an
- Markiert Post-Audio-Pointer mit `← Post-Audio`
- Zählt aktive Post-Audio-Pointer

### README

- Pointer-Coverage-Tabelle in allen 4 Sprachen (EN/DE/FR/ES)
- Erweiterte Dateiformat-Referenz mit allen Header-Offsets

### Files
- `gme_patch.py` v5
- `backup/gme_patch_v5.py`

---

## v4 – 2026-03-26

### Komplett-Umbau nach libtiptoi.c-Vorbild

**Ursache:** v3 verursachte Loops und Stift-Abstürze durch blinden Pointer-Scan
(Schritt 8 in v3: jeder uint32-Wert im Zielbereich wurde als Pointer interpretiert
und verschoben → Script-Befehle, Timer, OID-Codes wurden korrumpiert).

### Zwei Modi: Safe + Experimentell

- **Safe-Modus** (kein Post-Audio): Aufbau exakt wie libtiptoi.c `replaceAudio()`:
  Header → Tabelle → Audio → Checksum. Keine Pointer-Korrektur nötig.
  Wenn keine Post-Audio-Daten vorhanden → dieser Modus wird automatisch gewählt.

- **Experimenteller Modus** (Post-Audio vorhanden):
  - Interaktive Rückfrage vor dem Patch (oder `--force`)
  - Ausgabedatei erhält `_experimentell` im Namen
  - Post-Audio-Daten (Binaries, Spiele) werden bitgenau angehängt
  - NUR bekannte Header-Pointer (0x005C, 0x0064, 0x0068) werden gezielt korrigiert
  - KEIN Blind-Scan mehr (der Killer-Bug aus v3)

### Kein Duplikate-Dedup mehr
- Jeder Tabellenindex bekommt eigene Audio-Kopie (wie libtiptoi.c)
- Sicherer, vermeidet Komplikationen bei Offset-Referenzen

### tttool-kompatible CLI (argparse)
- `gme_patch.py media -d DIR INPUT.gme` → Audio extrahieren (neu)
- `gme_patch.py assemble INPUT.gme DIR/ OUT.gme` → Audio ersetzen
- `gme_patch.py info INPUT.gme` → GME-Info anzeigen
- `-h` / `--help` für alle Befehle
- `-f` / `--force` für experimentellen Modus ohne Rückfrage

### API für Pipeline-Integration
- `patch_gme()` gibt dict zurück: `{"mode", "output", "entries", "replaced", "kept"}`
- Pipeline kann Modus und tatsächlichen Ausgabepfad auswerten

### Entfernt
- Blind-Scan über alle Byte-Positionen (v3 Schritt 8)
- libtiptoi-Style `0000.ogg` Namensformat
- Alte CLI ohne argparse

### Files
- `gme_patch.py` v4

---

## v3 – 2026-03-22

### Bugfix (kritisch)
- **Post-Audio-Daten werden jetzt korrekt mitgenommen** (Binaries, Single Binaries, Special Symbols)
  - v2 hat alles nach dem letzten Audio-Block abgeschnitten → GME war für tttool unlesbar
  - Betroffene Daten bei Feuerwehr: 262.316 Bytes (Game00-08.b × 3 + Single Binaries + Special Symbols)
- Absolute Zeiger auf Post-Audio-Daten werden im Header UND in den Binary-Table-Headern verschoben
  - Scan-Methode: alle uint32-Werte in [last_audio_end, orig_file_size-4] werden um `shift` korrigiert
  - Bei Feuerwehr: 37 Zeiger verschoben (shift = +4.459.769 Bytes)
- `last_audio_end` wird jetzt korrekt als `max(offset + length)` aller Einträge berechnet
  (statt `entries[-1][0] + entries[-1][1]`, was bei nicht-sequenziellen Tabellen falsch war)

### Files
- `gme_patch.py` v3
- `backup/gme_patch_v3.py`

---

## v2 – 2026-03-22

### Änderungen
- Namenskonvention für Ausgabedateien dokumentiert: `_p_vN` Suffix (z.B. `Feuerwehr_ch_p_v2.gme`)
  → Unterscheidet Patcher-Output klar von Pipeline-Output (`_v29` etc.)
- Docstring aktualisiert

### Files
- `gme_patch.py` v2
- `backup/gme_patch_v2.py`

---

## v1 – 2026-03-21

Initial working prototype.

### Features
- Parse GME audio table from binary (offset at 0x0004, 8 bytes/entry)
- Auto-detect XOR encryption key from first audio file magic bytes
- Replace audio files from a `media_dir/` directory
- Auto-detect file naming: `Prefix_0.ogg` (index from trailing number)
- Preserve all non-audio data bit-for-bit (header, scripts, games, unknown segments)
- Update main audio table + additional audio table (0x0060) with new offsets
- Recalculate checksum (additive sum of all bytes)
- Handle duplicate table entries (multiple indices → same audio file)
- Keep original audio for indices without a replacement file
- `-i` / `--info` mode: show GME file info without modifying
- Print statistics: entry count, XOR key, replaced/kept counts, size delta

### Tested on
- `Pocketwissen_Feuerwehr.gme` (DE): 1160 entries, XOR=0xD3, 546 CH OGGs replaced
- Header/scripts identical bit-for-bit, checksum OK, first audio decodes to `OggS` ✓

### Bugfix applied during development
- `build_file_index`: regex `r'(\d+)\.ogg$'` matched `26` in `_303_v26.ogg`
  → fixed to `r'_(\d+)(?:_v\d+)?\.ogg$'` (ignores pipeline version suffix)

### Files
- `gme_patch.py` v1
- `backup/gme_patch_v1.py`
- `README.md`
- `CLAUDE.md`
