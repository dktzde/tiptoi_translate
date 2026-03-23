"""
gme_patch.py v3 – GME Audio-Patcher (Binary-Patch, kein YAML-Roundtrip)
=========================================================================
Ersetzt Audio-Dateien in einer Tiptoi-GME direkt im Binary.
Spiele, Scripts und alle unbekannten Segmente bleiben bitgenau erhalten.

v3: Post-Audio-Daten (Binaries, Single Binaries, Special Symbols) werden
    korrekt mitgenommen und alle absoluten Zeiger darauf werden verschoben.

Verwendung:
  python gme_patch.py original.gme media_dir/ output.gme

  - original.gme:  Original-GME (mit funktionierenden Spielen)
  - media_dir/:    Ordner mit neuen OGG-Dateien
  - output.gme:    Neue GME mit ersetztem Audio, Spiele intakt

Namenskonvention für Ausgabedateien (zur Unterscheidung von tttool-Pipeline):
  Pocketwissen_Feuerwehr_ch_p_v2.gme   (_p = patcher, _v2 = Patcher-Version)
  Die_Erde_fr_p_v2.gme
  → Nie _v29 o.ä. (das ist die Pipeline-Version), immer _p_vN

Dateinamen in media_dir werden automatisch erkannt:
  - 0000.ogg, 0001.ogg, ...           (libtiptoi-Style mit -n)
  - Feuerwehr_0000.ogg, ...           (tttool-Style)
  → Der letzte numerische Teil im Dateinamen bestimmt den Index.

Basierend auf:
  - tip-toi-reveng/GME-Format.md
  - tip-toi-reveng/libtiptoi.c (Michael Wolf, MIT License)
"""

import re
import struct
import sys
from pathlib import Path


# ─── Low-level Helpers ────────────────────────────────────────────────────────

def r32(data, off: int) -> int:
    return struct.unpack_from('<I', data, off)[0]


def w32(buf: bytearray, off: int, val: int) -> None:
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

    Regeln (aus GME-Format.md):
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


# ─── GME-Format Parsing ───────────────────────────────────────────────────────

def parse_media_table(data: bytes) -> tuple[int, int, list[tuple[int, int]]]:
    """Liest die Media-Tabelle aus dem GME-Header.

    Tabellen-Offset steht bei 0x0004 im Header.
    Eintragsanzahl = (erster Audio-Offset - Tabellen-Offset) / 8
    Jeder Eintrag: (offset: uint32, length: uint32)

    Gibt zurück: (table_offset, xor_key, [(offset, length), ...])
    """
    table_offset = r32(data, 0x0004)
    first_audio_offset = r32(data, table_offset)  # erstes Entry.offset
    count = (first_audio_offset - table_offset) // 8

    entries = []
    for i in range(count):
        pos = table_offset + i * 8
        entries.append((r32(data, pos), r32(data, pos + 4)))

    xor = find_xor(data, first_audio_offset)
    return table_offset, xor, entries


def build_file_index(media_dir: Path) -> dict[int, Path]:
    """Scannt media_dir und mappt Audio-Index → Dateipfad.

    Erkennt Namenskonventionen:
      - 0042.ogg                    (libtiptoi-Style)
      - Feuerwehr_0042.ogg          (tttool-Style)
      - Feuerwehr_0042_v26.ogg      (tttool-Style mit Pipeline-Version)
    Der numerische Block VOR einem optionalen _v##-Suffix bestimmt den Index.
    """
    index_map: dict[int, Path] = {}
    # Optionales _v{n} am Ende ignorieren; dann letzten numerischen Block nehmen
    pattern = re.compile(r'_(\d+)(?:_v\d+)?\.ogg$', re.IGNORECASE)
    fallback = re.compile(r'^(\d+)(?:_v\d+)?\.ogg$', re.IGNORECASE)
    for f in sorted(media_dir.glob('*.ogg')):
        m = pattern.search(f.name) or fallback.match(f.name)
        if m:
            idx = int(m.group(1))
            if idx not in index_map:
                index_map[idx] = f
    return index_map


# ─── Hauptfunktion ────────────────────────────────────────────────────────────

def patch_gme(original_gme: Path, media_dir: Path, output_gme: Path) -> None:
    """Ersetzt Audio in GME ohne YAML-Roundtrip.

    Algorithmus:
    1. Audio-Tabelle parsen (Offset + Länge pro Datei)
    2. XOR-Schlüssel bestimmen
    3. Ersatz-OGGs aus media_dir laden (Index-basiert)
    4. Alles vor erster Audio-Datei UNVERÄNDERT kopieren
       (enthält Header, Scripts, Spiele, unbekannte Segmente)
    5. Neue Audio-Dateien (XOR-verschlüsselt) sequenziell schreiben
    6. Post-Audio-Daten anhängen (Binaries, Single Binaries, Special Symbols)
    7. Audio-Tabelle mit neuen Offsets/Längen aktualisieren
    8. Zusatz-Audio-Tabelle (Offset bei 0x0060) aktualisieren falls vorhanden
    9. Absolute Zeiger auf Post-Audio-Daten im Header + Binary-Headern verschieben
    10. Prüfsumme neu berechnen
    """
    data = original_gme.read_bytes()
    print(f"Eingabe:   {original_gme} ({len(data):,} Bytes)")

    # 1. Parsen
    table_offset, xor, entries = parse_media_table(data)
    first_audio_offset = entries[0][0]
    print(f"Audio-Tabelle: 0x{table_offset:08X} | {len(entries)} Einträge | XOR=0x{xor:02X}")
    print(f"Erster Audio:  0x{first_audio_offset:08X}")

    # Echtes Ende des Audio-Blocks (höchster offset+länge aller Einträge)
    last_audio_end = max(off + length for off, length in entries if off > 0 and length > 0)
    orig_file_size = len(data)

    # Post-Audio-Daten (Binaries, Single Binaries, Special Symbols) sichern
    post_audio = data[last_audio_end:orig_file_size - 4]
    if post_audio:
        print(f"Post-Audio:    0x{last_audio_end:08X} – 0x{orig_file_size-4:08X} ({len(post_audio):,} Bytes)")

    # Duplikate erkennen: mehrere Tabelleneinträge → gleiche Audio-Datei
    offset_to_canonical: dict[int, int] = {}
    for i, (off, _) in enumerate(entries):
        if off not in offset_to_canonical:
            offset_to_canonical[off] = i

    # 2. Ersatz-OGGs laden
    file_index = build_file_index(media_dir)
    replaced = 0
    kept = 0

    canonical_audio: dict[int, bytes] = {}  # canonical_idx → rohe (dekodierte) Bytes
    for i, (orig_off, orig_len) in enumerate(entries):
        canonical = offset_to_canonical[orig_off]
        if canonical in canonical_audio:
            continue  # Duplikat, bereits verarbeitet

        if i in file_index:
            raw = file_index[i].read_bytes()
            canonical_audio[canonical] = raw
            replaced += 1
        else:
            # Original beibehalten (dekodieren + später neu kodieren)
            enc = data[orig_off:orig_off + orig_len]
            canonical_audio[canonical] = xor_codec(enc, xor)
            kept += 1

    print(f"Ersetzt: {replaced} | Behalten (kein Ersatz): {kept}")

    # 3. Neue GME zusammenbauen
    # Alles vor first_audio_offset bleibt UNVERÄNDERT (inkl. Header, Scripts, Spiele)
    result = bytearray(data[:first_audio_offset])

    # 4. Neue Audio-Dateien schreiben
    new_offset_map: dict[int, int] = {}  # canonical_idx → neuer Offset
    for i, (orig_off, _) in enumerate(entries):
        canonical = offset_to_canonical[orig_off]
        if canonical not in new_offset_map:
            new_offset_map[canonical] = len(result)
            result.extend(xor_codec(canonical_audio[canonical], xor))

    new_audio_end = len(result)  # Ende des neuen Audio-Blocks
    shift = new_audio_end - last_audio_end  # Versatz für alle Post-Audio-Zeiger

    # 5. Post-Audio-Daten anhängen (Binaries, Single Binaries, ...)
    if post_audio:
        result.extend(post_audio)

    # 6. Haupt-Audio-Tabelle aktualisieren (liegt in result[:first_audio_offset])
    for i, (orig_off, _) in enumerate(entries):
        canonical = offset_to_canonical[orig_off]
        new_off = new_offset_map[canonical]
        new_len = len(canonical_audio[canonical])
        pos = table_offset + i * 8
        w32(result, pos, new_off)
        w32(result, pos + 4, new_len)

    # 7. Zusatz-Audio-Tabelle (Offset bei 0x0060) aktualisieren
    add_table_off = r32(bytes(result), 0x0060)
    if 0 < add_table_off < first_audio_offset and add_table_off != table_offset:
        # Eintragsanzahl bestimmen
        add_first_val = r32(bytes(result), add_table_off)
        if add_first_val == first_audio_offset:
            # Noch nicht aktualisiert → Original-Werte, count berechnen
            add_count = (add_first_val - add_table_off) // 8
            if add_count == len(entries):
                for i, (orig_off, _) in enumerate(entries):
                    canonical = offset_to_canonical[orig_off]
                    new_off = new_offset_map[canonical]
                    new_len = len(canonical_audio[canonical])
                    pos = add_table_off + i * 8
                    w32(result, pos, new_off)
                    w32(result, pos + 4, new_len)
                print(f"Zusatz-Tabelle aktualisiert: 0x{add_table_off:08X}")

    # 8. Absolute Zeiger auf Post-Audio-Daten verschieben (shift)
    #    Scan: pre-audio header + post-audio block (Binary-Table-Header)
    #    Alle uint32-Werte in [last_audio_end, orig_file_size-4] werden um shift verschoben.
    if post_audio and shift != 0:
        ptr_lo = last_audio_end
        ptr_hi = orig_file_size - 4
        scan_regions = [
            (0, first_audio_offset),          # Header (enthält Zeiger auf Binaries etc.)
            (new_audio_end, len(result)),      # Post-Audio-Block (Binary-Table-Header)
        ]
        updated_ptrs = 0
        for region_start, region_end in scan_regions:
            for off in range(region_start, region_end - 3, 4):
                val = r32(bytes(result), off)
                if ptr_lo <= val <= ptr_hi:
                    w32(result, off, val + shift)
                    updated_ptrs += 1
        print(f"Post-Audio-Zeiger verschoben: {updated_ptrs} Einträge (shift={shift:+,} Bytes)")

    # 9. Prüfsumme (letzte 4 Bytes der Datei, nicht geprüft vom Stift laut Doku)
    checksum = sum(result) & 0xFFFFFFFF
    result.extend(struct.pack('<I', checksum))

    # Statistik
    orig_audio = last_audio_end - first_audio_offset
    new_audio = new_audio_end - first_audio_offset
    print(f"Audio-Größe: {orig_audio:,} → {new_audio:,} Bytes ({new_audio - orig_audio:+,})")
    print(f"Gesamt:      {len(data):,} → {len(result):,} Bytes")

    output_gme.write_bytes(bytes(result))
    print(f"Ausgabe:   {output_gme}")


# ─── Info-Modus ───────────────────────────────────────────────────────────────

def info_gme(gme_path: Path) -> None:
    """Zeigt Informationen über eine GME-Datei."""
    data = gme_path.read_bytes()
    table_offset, xor, entries = parse_media_table(data)
    first_audio = entries[0][0]
    last_entry = entries[-1]
    audio_end = last_entry[0] + last_entry[1]

    add_table_off = r32(data, 0x0060)

    print(f"Datei:          {gme_path} ({len(data):,} Bytes)")
    print(f"Audio-Tabelle:  0x{table_offset:08X} ({len(entries)} Einträge)")
    print(f"XOR-Schlüssel:  0x{xor:02X}")
    print(f"Audio-Bereich:  0x{first_audio:08X} – 0x{audio_end:08X} ({audio_end - first_audio:,} Bytes)")
    print(f"Zusatz-Tabelle: 0x{add_table_off:08X}")

    # Duplikate zählen
    unique_offsets = len({off for off, _ in entries})
    if unique_offsets < len(entries):
        print(f"Duplikate:      {len(entries) - unique_offsets} (mehrere Einträge → gleiche Datei)")

    # Prüfsumme
    stored_cs = r32(data, len(data) - 4)
    calc_cs = sum(data[:-4]) & 0xFFFFFFFF
    cs_ok = "OK" if stored_cs == calc_cs else f"FEHLER (gespeichert=0x{stored_cs:08X})"
    print(f"Prüfsumme:      0x{calc_cs:08X} [{cs_ok}]")


# ─── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] in ('-i', '--info'):
        info_gme(Path(sys.argv[2]))
    elif len(sys.argv) == 4:
        patch_gme(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]))
    else:
        print("GME Audio-Patcher – Binary-Patch, kein YAML-Roundtrip")
        print()
        print("Verwendung:")
        print("  python gme_patch.py original.gme media_dir/ output.gme")
        print("  python gme_patch.py -i original.gme")
        print()
        print("  original.gme:  Original-GME (Spiele funktionieren)")
        print("  media_dir/:    Ordner mit neuen OGG-Dateien")
        print("                 (0000.ogg oder Buch_0000.ogg etc.)")
        print("  output.gme:    Neue GME, Spiele intakt")
        sys.exit(1)
