# Changelog – gme_patch.py

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
- Auto-detect file naming: `0000.ogg` or `Prefix_0.ogg` (index from trailing number)
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
