"""
gme_patch.py v6 – GME Audio-Patcher (Binary-Patch, kein YAML-Roundtrip)
=========================================================================
Ersetzt Audio-Dateien in einer Tiptoi-GME direkt im Binary.
Spiele, Scripts und alle unbekannten Segmente bleiben bitgenau erhalten.

Befehle (tttool-kompatibel):
  python gme_patch.py media  -d DIR INPUT.gme            Audio extrahieren
  python gme_patch.py assemble INPUT.gme DIR/ OUT.gme    Audio ersetzen
  python gme_patch.py info INPUT.gme                     GME-Info anzeigen

Safe-Modus (Standard):
  Wenn keine Post-Audio-Daten vorhanden sind, wird die GME exakt wie
  libtiptoi.c zusammengebaut: Header → Tabelle → Audio → Checksum.
  Bit-für-Bit sicher, keine Pointer-Korrektur nötig.

Experimenteller Modus:
  Wenn Post-Audio-Daten existieren (Binaries, Spiele-Logik), wird
  interaktiv gefragt ob ein experimenteller Patch versucht werden soll.
  Post-Audio-Daten werden bitgenau angehängt, nur bekannte Header-Pointer
  werden gezielt korrigiert (kein Blind-Scan).
  Ausgabedatei erhält den Zusatz '_experimentell' im Namen.

Basierend auf:
  - tip-toi-reveng/GME-Format.md
  - tip-toi-reveng/libtiptoi.c (Michael Wolf, MIT License)
"""

import argparse
import re
import struct
import sys
from pathlib import Path


# ─── Low-level Helpers ────────────────────────────────────────────────────────

def r32(data: bytes, off: int) -> int:
    """Liest uint32 little-endian an Position off."""
    return struct.unpack_from('<I', data, off)[0]


def w32(buf: bytearray, off: int, val: int) -> None:
    """Schreibt uint32 little-endian an Position off."""
    struct.pack_into('<I', buf, off, val)


def find_xor(data: bytes, first_audio_offset: int) -> int:
    """Bestimmt XOR-Schlüssel aus den ersten 4 Bytes der ersten Audio-Datei.
    OGG-Dateien beginnen mit 'OggS', WAV mit 'RIFF'."""
    for magic in [b'OggS', b'RIFF']:
        x = data[first_audio_offset] ^ magic[0]
        if (data[first_audio_offset + 1] ^ x == magic[1] and
                data[first_audio_offset + 2] ^ x == magic[2] and
                data[first_audio_offset + 3] ^ x == magic[3]):
            return x
    return 0


def xor_codec(audio: bytes, xor: int) -> bytes:
    """XOR-Codec (symmetrisch: encode == decode).

    Regeln (aus GME-Format.md / libtiptoi.c):
      - 0x00, 0xFF, xor, xor^0xFF bleiben unverändert
      - alles andere wird bytewise mit xor XOR-verknüpft
    """
    if xor == 0:
        return audio
    xorff = xor ^ 0xFF
    out = bytearray(len(audio))
    for i, b in enumerate(audio):
        out[i] = b if b in (0, 0xFF, xor, xorff) else b ^ xor
    return bytes(out)


def checksum(data: bytes | bytearray) -> int:
    """Additive Prüfsumme über alle Bytes (wie libtiptoi.c calculateChecksum)."""
    return sum(data) & 0xFFFFFFFF


# ─── GME-Format Parsing ───────────────────────────────────────────────────────

def parse_media_table(data: bytes) -> tuple[int, int, list[tuple[int, int]]]:
    """Liest die Media-Tabelle aus dem GME-Header.

    Tabellen-Offset steht bei 0x0004 im Header.
    Eintragsanzahl = (erster Audio-Offset - Tabellen-Offset) / 8
    Jeder Eintrag: (offset: uint32, length: uint32)

    Gibt zurück: (table_offset, xor_key, [(offset, length), ...])
    """
    table_offset = r32(data, 0x0004)
    first_audio_offset = r32(data, table_offset)
    count = (first_audio_offset - table_offset) // 8

    entries = []
    for i in range(count):
        pos = table_offset + i * 8
        entries.append((r32(data, pos), r32(data, pos + 4)))

    xor = find_xor(data, first_audio_offset)
    return table_offset, xor, entries


def build_file_index(media_dir: Path) -> dict[int, Path]:
    """Scannt media_dir und mappt Audio-Index → Dateipfad.

    Erkennt tttool-Namenskonvention:
      - Feuerwehr_0042.ogg          (tttool media)
      - Feuerwehr_0042_v26.ogg      (mit Pipeline-Version)
    Der numerische Block VOR einem optionalen _v##-Suffix bestimmt den Index.
    """
    index_map: dict[int, Path] = {}
    pattern = re.compile(r'_(\d+)(?:_v\d+)?\.ogg$', re.IGNORECASE)
    for f in sorted(media_dir.glob('*.ogg')):
        m = pattern.search(f.name)
        if m:
            idx = int(m.group(1))
            if idx not in index_map:
                index_map[idx] = f
    return index_map


# ─── Safe-Modus (exakt wie libtiptoi.c replaceAudio) ─────────────────────────

def _prepare_audio(
    data: bytes,
    xor: int,
    entries: list[tuple[int, int]],
    file_index: dict[int, Path],
) -> tuple[list[bytes], dict[int, int], int, int]:
    """Bereitet Audio-Blobs vor und bewahrt die Duplikat-Struktur.

    tttool exportiert nur kanonische Indices (erstes Vorkommen jedes
    einzigartigen Offsets). Duplikate (gleicher Offset) teilen sich
    denselben Audio-Blob – genau wie im Original.

    Gibt zurück: (unique_blobs, orig_off_to_blob_idx, replaced, kept)
      unique_blobs:         Liste der einzigartigen Audio-Blobs
      orig_off_to_blob_idx: Mapping orig_offset → Index in unique_blobs
      replaced:             Anzahl ersetzter Einträge (inkl. Duplikate)
      kept:                 Anzahl behaltener Einträge (inkl. Duplikate)
    """
    # ── Duplikat-Mapping: offset → kanonischer Index ──
    offset_to_canonical: dict[int, int] = {}
    for i, (off, _) in enumerate(entries):
        if off not in offset_to_canonical:
            offset_to_canonical[off] = i

    # ── Einzigartige Blobs in Reihenfolge des Erstauftretens ──
    unique_blobs: list[bytes] = []
    orig_off_to_blob_idx: dict[int, int] = {}
    replaced = 0
    kept = 0

    for i, (orig_off, orig_len) in enumerate(entries):
        canonical = offset_to_canonical[orig_off]
        is_canonical = (i == canonical)

        if is_canonical:
            # Kanonischer Eintrag: Blob erzeugen
            if i in file_index:
                raw = file_index[i].read_bytes()
                replaced += 1
            else:
                enc = data[orig_off:orig_off + orig_len]
                raw = xor_codec(enc, xor)
                kept += 1
            orig_off_to_blob_idx[orig_off] = len(unique_blobs)
            unique_blobs.append(raw)
        else:
            # Duplikat: zählen, aber kein neuer Blob
            if canonical in file_index:
                replaced += 1
            else:
                kept += 1

    return unique_blobs, orig_off_to_blob_idx, replaced, kept


def _patch_safe(
    data: bytes,
    table_offset: int,
    xor: int,
    entries: list[tuple[int, int]],
    file_index: dict[int, Path],
) -> tuple[bytearray, int, int]:
    """Baut GME exakt wie libtiptoi.c replaceAudio():
    Header[0..audioTableOffset] + neue Tabelle + Audio + Checksum.

    Duplikat-Einträge teilen sich denselben Offset (wie im Original).
    Kein Post-Audio. Keine Pointer-Korrektur.

    Gibt zurück: (result_bytearray, replaced_count, kept_count)
    """
    first_audio_offset = entries[0][0]
    count = len(entries)

    unique_blobs, orig_off_to_blob_idx, replaced, kept = \
        _prepare_audio(data, xor, entries, file_index)

    # ── Neue Offsets für einzigartige Blobs berechnen ──
    blob_new_offsets: list[tuple[int, int]] = []  # (new_offset, length)
    next_offset = first_audio_offset
    for blob in unique_blobs:
        blob_new_offsets.append((next_offset, len(blob)))
        next_offset += len(blob)

    # ── Audio-Tabelle: Duplikate zeigen auf denselben Offset ──
    new_table = bytearray(count * 8)
    for i, (orig_off, _) in enumerate(entries):
        blob_idx = orig_off_to_blob_idx[orig_off]
        new_off, new_len = blob_new_offsets[blob_idx]
        struct.pack_into('<II', new_table, i * 8, new_off, new_len)

    # ── Zusammenbauen ──
    result = bytearray(data[:table_offset])
    result.extend(new_table)
    for blob in unique_blobs:
        result.extend(xor_codec(blob, xor))
    cs = checksum(result)
    result.extend(struct.pack('<I', cs))

    return result, replaced, kept


# ─── Experimenteller Modus (Safe + Post-Audio + gezielte Pointer) ────────────

# Alle bekannten Header-Offsets die auf Post-Audio-Daten zeigen können
# (aus GME-Format.md / tttool GMEParser.hs)
#
# Header-Offset → (Name, hat_interne_pointer)
#
# has_internals=True:  Header zeigt auf eine Tabelle mit count + Einträgen,
#                      deren Offset-Felder ebenfalls verschoben werden müssen.
# has_internals=False: Header zeigt direkt auf Daten (kein inneres Pointer-Netz).
_POST_AUDIO_HEADERS: dict[int, tuple[str, bool]] = {
    0x005C: ("Binaries 1",        True),
    0x0064: ("Single-Binaries",   True),
    0x0068: ("Special Symbols",   True),
    0x008C: ("Media Flags",       False),
    0x0090: ("Game Binaries 2",   True),
    0x0094: ("Special OID List",  False),
    0x0098: ("Game Binaries 3",   True),
    0x00A0: ("Single Binary 1",   False),
    0x00A8: ("Single Binary 2",   False),
    0x00C8: ("Single Binary 3",   False),
    0x00CC: ("Binaries Table 4",  True),
}


def _shift_binary_table(result: bytearray, table_start: int,
                        old_audio_end: int, orig_file_size: int,
                        shift: int) -> int:
    """Verschiebt Pointer innerhalb einer Binary-Tabelle.

    Binary-Tabellen haben das Format:
      count (uint32)
      count Einträge, jeweils:
        - NULL: uint32 = 0 (4 Bytes)
        - Non-NULL: offset(4) + length(4) + name(8) = 16 Bytes
          offset zeigt auf Binary-Daten im Post-Audio-Bereich.

    Scan-Ansatz: alle uint32-Werte im Tabellenbereich prüfen.
    Sicher, weil Name-Strings (ASCII) und Lengths (klein) nie im
    Post-Audio-Adressbereich liegen.

    Gibt Anzahl verschobener Pointer zurück.
    """
    if table_start + 4 > len(result):
        return 0
    bin_count = r32(bytes(result), table_start)
    if bin_count == 0 or bin_count > 10000:
        return 0

    # Scan-Bereich: count-Feld überspringen, maximal count × 16 Bytes
    scan_size = min(bin_count * 16, 4096)
    scan_start = table_start + 4
    scan_end = min(scan_start + scan_size, len(result) - 3)

    updated = 0
    for pos in range(scan_start, scan_end, 4):
        val = r32(bytes(result), pos)
        if old_audio_end <= val < orig_file_size:
            w32(result, pos, val + shift)
            updated += 1

    return updated


def _patch_experimental(
    data: bytes,
    table_offset: int,
    xor: int,
    entries: list[tuple[int, int]],
    file_index: dict[int, Path],
    last_audio_end: int,
) -> tuple[bytearray, int, int]:
    """Wie Safe-Modus, plus:
    - Post-Audio-Daten (Binaries, Spiele) bitgenau anhängen
    - Gezielte Pointer-Korrektur (nur bekannte Header-Felder)
    - Duplikat-Struktur wird bewahrt (Zusatz-Tabelle bleibt konsistent)
    - KEIN Blind-Scan

    Gibt zurück: (result_bytearray, replaced_count, kept_count)
    """
    first_audio_offset = entries[0][0]
    orig_file_size = len(data)
    count = len(entries)

    # Post-Audio-Daten sichern (ohne abschließende 4-Byte-Checksum)
    post_audio = data[last_audio_end:orig_file_size - 4]
    print(f"Post-Audio:    0x{last_audio_end:08X} – 0x{orig_file_size - 4:08X} "
          f"({len(post_audio):,} Bytes)")

    unique_blobs, orig_off_to_blob_idx, replaced, kept = \
        _prepare_audio(data, xor, entries, file_index)

    # ── Neue Offsets für einzigartige Blobs berechnen ──
    blob_new_offsets: list[tuple[int, int]] = []
    next_offset = first_audio_offset
    for blob in unique_blobs:
        blob_new_offsets.append((next_offset, len(blob)))
        next_offset += len(blob)

    # ── Audio-Tabelle: Duplikate zeigen auf denselben Offset ──
    new_table = bytearray(count * 8)
    for i, (orig_off, _) in enumerate(entries):
        blob_idx = orig_off_to_blob_idx[orig_off]
        new_off, new_len = blob_new_offsets[blob_idx]
        struct.pack_into('<II', new_table, i * 8, new_off, new_len)

    # ── Zusammenbauen ──
    result = bytearray(data[:table_offset])
    result.extend(new_table)
    for blob in unique_blobs:
        result.extend(xor_codec(blob, xor))

    new_audio_end = len(result)
    shift = new_audio_end - last_audio_end

    # Post-Audio-Daten anhängen
    result.extend(post_audio)

    # Gezielte Pointer-Korrektur (alle bekannten Header-Felder)
    updated_ptrs = 0
    for hdr_off, (name, has_internals) in _POST_AUDIO_HEADERS.items():
        if hdr_off + 4 > len(result):
            continue
        val = r32(bytes(result), hdr_off)
        if val == 0 or val == 0xFFFFFFFF:
            continue
        if last_audio_end <= val < orig_file_size:
            new_val = val + shift
            w32(result, hdr_off, new_val)
            updated_ptrs += 1
            print(f"  0x{hdr_off:04X} {name:20s} 0x{val:08X} → 0x{new_val:08X}")
            if has_internals:
                n = _shift_binary_table(
                    result, new_val, last_audio_end, orig_file_size, shift
                )
                if n:
                    updated_ptrs += n
                    print(f"         └─ {n} interne Pointer verschoben")

    if updated_ptrs > 0:
        print(f"Post-Audio-Zeiger verschoben: {updated_ptrs} (shift={shift:+,} Bytes)")

    # Checksum
    cs = checksum(result)
    result.extend(struct.pack('<I', cs))

    return result, replaced, kept


# ─── Hauptfunktion: patch_gme ─────────────────────────────────────────────────

def patch_gme(original_gme: Path, media_dir: Path, output_gme: Path,
              force: bool = False) -> dict:
    """Ersetzt Audio in GME ohne YAML-Roundtrip.

    Safe-Modus: kein Post-Audio → exakt wie libtiptoi.c
    Experimentell: Post-Audio vorhanden → interaktive Rückfrage (oder --force)

    Returns: {
        "mode": "safe" | "experimental" | "aborted",
        "output": Path,
        "entries": int,
        "replaced": int,
        "kept": int,
    }
    """
    data = original_gme.read_bytes()
    print(f"Eingabe:       {original_gme} ({len(data):,} Bytes)")

    # 1. Parsen
    table_offset, xor, entries = parse_media_table(data)
    first_audio_offset = entries[0][0]
    count = len(entries)
    print(f"Audio-Tabelle: 0x{table_offset:08X} | {count} Einträge | XOR=0x{xor:02X}")
    print(f"Erster Audio:  0x{first_audio_offset:08X}")

    # Audio-Ende bestimmen (höchster offset+length aller Einträge)
    last_audio_end = max(off + length for off, length in entries if off > 0 and length > 0)
    orig_file_size = len(data)

    # Post-Audio-Daten vorhanden?
    has_post_audio = (last_audio_end + 4) < orig_file_size
    post_audio_size = orig_file_size - 4 - last_audio_end if has_post_audio else 0

    # 2. Ersatz-OGGs laden
    file_index = build_file_index(media_dir)
    print(f"Ersatz-OGGs:   {len(file_index)} Dateien in {media_dir}")

    # 3. Modus bestimmen
    if not has_post_audio:
        # ── Safe-Modus (exakt wie libtiptoi.c) ──
        print(f"\nModus:         SAFE (keine Post-Audio-Daten)")
        result, replaced, kept = _patch_safe(data, table_offset, xor, entries, file_index)

        # Statistik
        new_audio_end = first_audio_offset + sum(len(file_index[i].read_bytes()) if i in file_index
                                                  else entries[i][1] for i in range(count))
        orig_audio = last_audio_end - first_audio_offset
        print(f"Ersetzt:       {replaced} | Behalten: {kept}")
        print(f"Gesamt:        {len(data):,} → {len(result):,} Bytes")

        output_gme.parent.mkdir(parents=True, exist_ok=True)
        output_gme.write_bytes(bytes(result))
        print(f"Ausgabe:       {output_gme}")

        return {"mode": "safe", "output": output_gme,
                "entries": count, "replaced": replaced, "kept": kept}

    else:
        # ── Post-Audio-Daten vorhanden ──
        print(f"\n{'!'*60}")
        print(f"  ACHTUNG: Post-Audio-Daten gefunden ({post_audio_size:,} Bytes)")
        print(f"  Bereich: 0x{last_audio_end:08X} – 0x{orig_file_size - 4:08X}")
        print(f"  (enthält vermutlich Binaries / Spiele-Logik)")
        print(f"{'!'*60}")

        if not force:
            print()
            print("  Im Safe-Modus (wie libtiptoi.c) wird bei Post-Audio-Daten")
            print("  abgebrochen, da die Funktion nicht garantiert werden kann.")
            print()
            try:
                answer = input("  [EXPERIMENTELL] Trotzdem versuchen? (j/N): ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                answer = ""
            if answer not in ("j", "ja", "y", "yes"):
                print("\n  Abgebrochen.")
                return {"mode": "aborted", "output": output_gme,
                        "entries": count, "replaced": 0, "kept": 0}

        # Experimenteller Dateiname
        stem = output_gme.stem
        exp_name = f"{stem}_experimentell{output_gme.suffix}"
        exp_output = output_gme.with_name(exp_name)

        print(f"\nModus:         EXPERIMENTELL")
        result, replaced, kept = _patch_experimental(
            data, table_offset, xor, entries, file_index, last_audio_end,
        )

        # Statistik
        orig_audio = last_audio_end - first_audio_offset
        print(f"Ersetzt:       {replaced} | Behalten: {kept}")
        print(f"Gesamt:        {len(data):,} → {len(result):,} Bytes")

        exp_output.parent.mkdir(parents=True, exist_ok=True)
        exp_output.write_bytes(bytes(result))
        print(f"Ausgabe:       {exp_output}")
        print(f"\n  ⚠ EXPERIMENTELL – bitte auf dem Stift testen!")

        return {"mode": "experimental", "output": exp_output,
                "entries": count, "replaced": replaced, "kept": kept}


# ─── Audio extrahieren (wie tttool media) ─────────────────────────────────────

def extract_media(gme_path: Path, output_dir: Path) -> None:
    """Extrahiert Audio-Dateien aus GME (wie tttool media -d DIR).

    Dateinamen: {GME-Stem}_{Index}.ogg (tttool-kompatibel)
    Duplikate (mehrere Indices → gleicher Offset) werden nur einmal geschrieben,
    weitere Indices zeigen auf den kanonischen Index.
    """
    data = gme_path.read_bytes()
    table_offset, xor, entries = parse_media_table(data)
    prefix = gme_path.stem

    output_dir.mkdir(parents=True, exist_ok=True)

    exported = 0
    skipped_dupes = 0
    offset_to_idx: dict[int, int] = {}

    for i, (off, length) in enumerate(entries):
        # Duplikat-Erkennung (wie libtiptoi.c)
        if off in offset_to_idx:
            skipped_dupes += 1
            # Duplikat: Datei existiert bereits unter kanonischem Index
            canonical = offset_to_idx[off]
            # Optional: Symlink oder einfach nochmal schreiben
            # Wir schreiben einfach nochmal (wie tttool)
            canonical_file = output_dir / f"{prefix}_{canonical}.ogg"
            dupe_file = output_dir / f"{prefix}_{i}.ogg"
            if canonical_file.exists() and not dupe_file.exists():
                dupe_file.write_bytes(canonical_file.read_bytes())
            continue

        offset_to_idx[off] = i

        # Audio dekodieren
        enc = data[off:off + length]
        raw = xor_codec(enc, xor)

        # Dateityp bestimmen
        if raw[:4] == b'OggS':
            ext = '.ogg'
        elif raw[:4] == b'RIFF':
            ext = '.wav'
        else:
            ext = '.raw'

        out_file = output_dir / f"{prefix}_{i}{ext}"
        out_file.write_bytes(raw)
        exported += 1

    print(f"Extrahiert:    {exported} Dateien nach {output_dir}/")
    if skipped_dupes:
        print(f"Duplikate:     {skipped_dupes} (gleicher Offset → gleiche Datei)")


# ─── Info-Modus ───────────────────────────────────────────────────────────────

def info_gme(gme_path: Path) -> None:
    """Zeigt Informationen über eine GME-Datei (wie tttool info)."""
    data = gme_path.read_bytes()
    table_offset, xor, entries = parse_media_table(data)
    first_audio = entries[0][0]
    last_audio_end = max(off + length for off, length in entries if off > 0 and length > 0)
    orig_file_size = len(data)

    add_table_off = r32(data, 0x0060)
    book_code = r32(data, 0x0014)

    print(f"Datei:          {gme_path} ({orig_file_size:,} Bytes)")
    print(f"Book-Code:      {book_code}")
    print(f"Audio-Tabelle:  0x{table_offset:08X} ({len(entries)} Einträge)")
    print(f"XOR-Schlüssel:  0x{xor:02X}")
    print(f"Audio-Bereich:  0x{first_audio:08X} – 0x{last_audio_end:08X} "
          f"({last_audio_end - first_audio:,} Bytes)")
    print(f"Zusatz-Tabelle: 0x{add_table_off:08X}")

    # Post-Audio-Daten?
    post_audio_size = orig_file_size - 4 - last_audio_end
    if post_audio_size > 0:
        print(f"Post-Audio:     0x{last_audio_end:08X} – 0x{orig_file_size - 4:08X} "
              f"({post_audio_size:,} Bytes)")
        # Alle bekannten Header-Pointer anzeigen
        post_count = 0
        for hdr_off, (name, _) in _POST_AUDIO_HEADERS.items():
            val = r32(data, hdr_off)
            if val and val != 0xFFFFFFFF:
                if last_audio_end <= val < orig_file_size:
                    print(f"  {name:20s}  0x{hdr_off:04X} → 0x{val:08X}  ← Post-Audio")
                    post_count += 1
                else:
                    print(f"  {name:20s}  0x{hdr_off:04X} → 0x{val:08X}")
        print(f"  Post-Audio-Pointer: {post_count}")
    else:
        print(f"Post-Audio:     keine")

    # Duplikate
    unique_offsets = len({off for off, _ in entries})
    if unique_offsets < len(entries):
        print(f"Duplikate:      {len(entries) - unique_offsets}")

    # Prüfsumme
    stored_cs = r32(data, orig_file_size - 4)
    calc_cs = checksum(data[:-4])
    cs_ok = "OK" if stored_cs == calc_cs else f"FEHLER (erwartet=0x{calc_cs:08X})"
    print(f"Prüfsumme:      0x{stored_cs:08X} [{cs_ok}]")


# ─── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog="gme_patch.py",
        description=(
            "GME Audio-Patcher – ersetzt Audio in Tiptoi-GME-Dateien "
            "per Binary-Patch. Spiele und Scripts bleiben erhalten "
            "(kein YAML-Roundtrip wie bei tttool export/assemble)."
        ),
        epilog=(
            "Beispiele:\n"
            "  %(prog)s media  -d media_dir/ Feuerwehr.gme\n"
            "  %(prog)s assemble Feuerwehr.gme tts_output/ Feuerwehr_fr.gme\n"
            "  %(prog)s assemble Feuerwehr.gme tts_output/ Feuerwehr_fr.gme --force\n"
            "  %(prog)s info Feuerwehr.gme\n"
            "\n"
            "Dateinamen in media_dir (tttool-kompatibel):\n"
            "  Feuerwehr_0.ogg, Feuerwehr_1.ogg, ...\n"
            "  Feuerwehr_42_v32.ogg  (Pipeline-Version wird ignoriert)\n"
            "  → Der letzte numerische Block vor .ogg bestimmt den Index.\n"
            "\n"
            "Modi:\n"
            "  SAFE:           Kein Post-Audio → exakt wie libtiptoi.c\n"
            "  EXPERIMENTELL:  Post-Audio (Spiele) vorhanden → interaktive Rückfrage\n"
            "                  Ausgabedatei erhält '_experimentell' im Namen\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest="command", help="Befehl")

    # ── media ──
    p_media = subparsers.add_parser(
        "media",
        help="Audio-Dateien aus GME extrahieren (wie tttool media)",
        description="Extrahiert alle Audio-Dateien aus einer GME-Datei.",
    )
    p_media.add_argument(
        "-d", "--dir", required=True, type=Path, metavar="DIR",
        help="Zielverzeichnis für extrahierte Audio-Dateien",
    )
    p_media.add_argument(
        "input", type=Path, metavar="INPUT.gme",
        help="Eingabe-GME-Datei",
    )

    # ── assemble ──
    p_assemble = subparsers.add_parser(
        "assemble",
        help="Audio in GME ersetzen (Binary-Patch, kein YAML)",
        description=(
            "Ersetzt Audio-Dateien in einer GME per Binary-Patch. "
            "Dateien in MEDIA_DIR mit passendem Index ersetzen die "
            "Original-Audio-Dateien; alle anderen bleiben erhalten."
        ),
    )
    p_assemble.add_argument(
        "input", type=Path, metavar="INPUT.gme",
        help="Original-GME-Datei",
    )
    p_assemble.add_argument(
        "media_dir", type=Path, metavar="MEDIA_DIR",
        help="Ordner mit neuen OGG-Dateien (tttool-Namenskonvention)",
    )
    p_assemble.add_argument(
        "output", type=Path, metavar="OUTPUT.gme",
        help="Ausgabe-GME-Datei",
    )
    p_assemble.add_argument(
        "-f", "--force", action="store_true",
        help="Experimentellen Modus ohne Rückfrage aktivieren",
    )

    # ── info ──
    p_info = subparsers.add_parser(
        "info",
        help="GME-Datei-Informationen anzeigen (wie tttool info)",
        description="Zeigt Header, Audio-Tabelle und Prüfsumme einer GME-Datei.",
    )
    p_info.add_argument(
        "input", type=Path, metavar="INPUT.gme",
        help="GME-Datei",
    )

    # ── Parse ──
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    if args.command == "media":
        if not args.input.exists():
            print(f"Fehler: Datei nicht gefunden: {args.input}")
            sys.exit(1)
        extract_media(args.input, args.dir)

    elif args.command == "assemble":
        if not args.input.exists():
            print(f"Fehler: Datei nicht gefunden: {args.input}")
            sys.exit(1)
        if not args.media_dir.is_dir():
            print(f"Fehler: Verzeichnis nicht gefunden: {args.media_dir}")
            sys.exit(1)
        result = patch_gme(args.input, args.media_dir, args.output, force=args.force)
        if result["mode"] == "aborted":
            sys.exit(1)

    elif args.command == "info":
        if not args.input.exists():
            print(f"Fehler: Datei nicht gefunden: {args.input}")
            sys.exit(1)
        info_gme(args.input)


if __name__ == "__main__":
    main()
