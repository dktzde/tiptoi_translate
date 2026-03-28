#!/usr/bin/env python3
"""
Sucht ALLE uint32-Pointer im Post-Audio-Bereich einer GME-Datei.
Zeigt welche _shift_binary_table findet vs. welche es übersieht.

Aufruf: python3 find_embedded_pointers.py <datei.gme>
"""
import struct
import sys
from pathlib import Path


def r32(data, off): return struct.unpack_from("<I", data, off)[0]
def r16(data, off): return struct.unpack_from("<H", data, off)[0]


POST_AUDIO_HEADERS = [0x0090, 0x0094, 0x0098, 0x00A0, 0x00A8, 0x00C8, 0x00CC]


def find_audio_end(data):
    candidates = [r32(data, off) for off in POST_AUDIO_HEADERS
                  if r32(data, off) > 0x100000 and r32(data, off) < len(data)]
    return min(candidates)


def find_audio_start(data):
    media_table   = r32(data, 0x0004)
    add_media_table = r32(data, 0x0060)
    n = (add_media_table - media_table) // 8
    min_off = None
    for t in [media_table, add_media_table]:
        for i in range(n):
            v = r32(data, t + i*8)
            if v > 0 and (min_off is None or v < min_off):
                min_off = v
    return min_off


def simulate_shift_binary_table(data, table_start, old_audio_end, orig_size):
    """Simuliert _shift_binary_table: gibt Set von Offsets zurück die GEFUNDEN werden."""
    found = set()
    if table_start + 4 > len(data):
        return found
    bin_count = r32(data, table_start)
    if bin_count == 0 or bin_count > 10000:
        return found
    scan_size = min(bin_count * 16, 4096)
    scan_start = table_start + 4
    scan_end = min(scan_start + scan_size, len(data) - 3)
    for pos in range(scan_start, scan_end, 4):
        val = r32(data, pos)
        if old_audio_end <= val < orig_size:
            found.add(pos)
    return found


def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("../../01_input/Pocketwissen_Feuerwehr.gme")
    print(f"Analysiere: {path}")
    data = path.read_bytes()
    orig_size = len(data)

    audio_start = find_audio_start(data)
    audio_end   = find_audio_end(data)
    post_audio_size = orig_size - 4 - audio_end

    print(f"  Audio:      0x{audio_start:08X} – 0x{audio_end:08X} ({audio_end - audio_start:,} Bytes)")
    print(f"  Post-Audio: 0x{audio_end:08X} – 0x{orig_size-4:08X} ({post_audio_size:,} Bytes)")
    print()

    # 1) ALLE uint32-Werte im Post-Audio-Bereich die auf Post-Audio zeigen
    all_ptrs = {}   # offset_in_file → value
    for pos in range(audio_end, orig_size - 3, 4):
        val = r32(data, pos)
        if audio_end <= val < orig_size - 4:
            all_ptrs[pos] = val

    print(f"ALLE Post-Audio→Post-Audio Pointer: {len(all_ptrs)}")

    # 2) Was findet _shift_binary_table aktuell?
    found_by_sbt = set()
    for header_off in POST_AUDIO_HEADERS:
        table_start = r32(data, header_off)
        if table_start < audio_end or table_start >= orig_size:
            continue
        hits = simulate_shift_binary_table(data, table_start, audio_end, orig_size)
        found_by_sbt |= hits

    # 3) Was findet der Header-Update (feste Offsets 0x0090-0x00CC)?
    found_by_header = set()
    for header_off in POST_AUDIO_HEADERS:
        val = r32(data, header_off)
        if audio_end <= val < orig_size:
            found_by_header.add(header_off)

    # 4) Analyse
    all_ptr_offsets = set(all_ptrs.keys())
    covered = found_by_sbt | found_by_header
    missed = all_ptr_offsets - covered

    print(f"Davon durch Header-Update gefunden:      {len(found_by_header)}")
    print(f"Davon durch _shift_binary_table gefunden: {len(found_by_sbt)}")
    print(f"Gesamt abgedeckt:                        {len(covered)}")
    print(f"NICHT abgedeckt (potential missing!):    {len(missed)}")
    print()

    if missed:
        print("=== NICHT ABGEDECKTE POINTER ===")
        print(f"  {'Offset':>12}  {'Wert':>12}  Kontext")
        for pos in sorted(missed):
            val = all_ptrs[pos]
            # Welchem Abschnitt gehört pos an?
            section = "?"
            for h in POST_AUDIO_HEADERS:
                t = r32(data, h)
                # Finde welcher Header-Bereich
                next_t = orig_size
                for h2 in POST_AUDIO_HEADERS:
                    t2 = r32(data, h2)
                    if t < t2 < next_t:
                        next_t = t2
                if t <= pos < next_t:
                    section = f"0x{h:04X}_section@0x{t:08X}"
                    break
            print(f"  0x{pos:08X}  0x{val:08X}  {section}")
    else:
        print("✓ ALLE Post-Audio-Pointer werden vom Patcher abgedeckt!")
        print("  → Crash liegt NICHT an fehlenden Pointer-Updates im Post-Audio-Bereich")
        print("  → Wahrscheinlich ein Audio-/Header-Problem (XOR? Media-Tabelle?)")

    # 5) Detailansicht: was findet _shift_binary_table pro Tabelle?
    print()
    print("=== _shift_binary_table DETAIL PRO TABELLE ===")
    for header_off in POST_AUDIO_HEADERS:
        table_start = r32(data, header_off)
        if table_start < audio_end or table_start >= orig_size:
            print(f"  0x{header_off:04X} → 0x{table_start:08X}: NICHT im Post-Audio-Bereich (übersprungen)")
            continue
        hits = simulate_shift_binary_table(data, table_start, audio_end, orig_size)
        bin_count = r32(data, table_start)
        print(f"  0x{header_off:04X} → 0x{table_start:08X}: bin_count={bin_count}, {len(hits)} Pointer gefunden")
        for h in sorted(hits):
            print(f"    pos=0x{h:08X}  val=0x{r32(data,h):08X}")


if __name__ == "__main__":
    main()
