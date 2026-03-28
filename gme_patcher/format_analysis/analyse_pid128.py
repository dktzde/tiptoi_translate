#!/usr/bin/env python3
"""
GME Format Analysis: PID 128 DE vs FR
Pocketwissen_Feuerwehr.gme (DE) vs Mini_Doc-Les_pompiers.gme (FR)

Ziel: Alle Bytes finden, die sich außerhalb der Audio-Daten unterscheiden.
Das zeigt uns, welche Pointer/Offsets beim Audio-Ersetzen angepasst werden müssen.
"""
import struct
import sys
from pathlib import Path

DE = Path("../../01_input/Pocketwissen_Feuerwehr.gme")
FR = Path("../../01_input/Mini_Doc-Les_pompiers.gme")


def read_u32(data, offset):
    return struct.unpack_from("<I", data, offset)[0]


def read_u16(data, offset):
    return struct.unpack_from("<H", data, offset)[0]


def parse_header(data, label):
    print(f"\n=== HEADER: {label} ===")
    fields = [
        (0x0000, "script_table_offset"),
        (0x0004, "media_table_offset"),
        (0x0008, "magic_0x238b"),
        (0x000C, "additional_script_table_offset"),
        (0x0010, "game_table_offset"),
        (0x0014, "product_id"),
        (0x0018, "register_init_offset"),
        (0x001C, "xor_raw (u8)"),
        (0x0060, "additional_media_table_offset"),
        (0x0071, "power_on_sound_offset"),
        (0x008C, "media_flag_table_offset"),
        (0x0090, "game_binaries_table_offset"),
        (0x0094, "special_oid_list_offset"),
        (0x0098, "additional_game_binaries_offset"),
        (0x009C, "unknown_009C"),
        (0x00A0, "single_game_binary_offset"),
        (0x00A4, "flag_A4"),
        (0x00A8, "single_game_binary_2_offset"),
        (0x00C8, "single_game_binary_3_offset"),
        (0x00CC, "additional_game_binaries_3_offset"),
    ]
    results = {}
    for off, name in fields:
        if off == 0x001C:
            val = data[off]
            print(f"  0x{off:04X}  {name:45s} = 0x{val:02X}")
        elif off == 0x0071:
            val = read_u32(data, off)
            print(f"  0x{off:04X}  {name:45s} = 0x{val:08X}")
        else:
            val = read_u32(data, off)
            print(f"  0x{off:04X}  {name:45s} = 0x{val:08X}")
        results[name] = val
    return results


def find_audio_start(data, media_table_offset, additional_media_table_offset):
    """Findet erstes Audio-Offset anhand aller Tabelleneinträge (main + additional)."""
    # Eintragsanzahl = Differenz der Tabellen-Offsets / 8
    n_main = (additional_media_table_offset - media_table_offset) // 8
    # Beide Tabellen scannen: main + additional (gleich viele Einträge)
    min_offset = None
    for table_start in [media_table_offset, additional_media_table_offset]:
        for i in range(n_main):
            entry_off = table_start + i * 8
            if entry_off + 8 > len(data):
                break
            audio_off = read_u32(data, entry_off)
            if audio_off > 0 and (min_offset is None or audio_off < min_offset):
                min_offset = audio_off
    return min_offset


def find_audio_end_from_header(data):
    """Findet Ende des Audio-Bereichs aus den Post-Audio-Header-Pointern.
    Das kleinste Post-Audio-Pointer zeigt auf den Beginn der Spieldaten."""
    post_audio_fields = [0x0090, 0x0094, 0x0098, 0x00A0, 0x00A8, 0x00C8, 0x00CC]
    candidates = []
    for off in post_audio_fields:
        val = read_u32(data, off)
        if val > 0x100000 and val < len(data):  # muss nach dem Header-Bereich liegen
            candidates.append(val)
    return min(candidates) if candidates else len(data) - 4


def diff_region(de_data, fr_data, start, end, label, max_diffs=50):
    """Vergleicht einen Bereich und zeigt Unterschiede."""
    end_de = min(end, len(de_data))
    end_fr = min(end, len(fr_data))
    end_common = min(end_de, end_fr)

    diffs = []
    i = start
    while i < end_common:
        if de_data[i] != fr_data[i]:
            # Versuche 4-Byte Wort zu lesen
            if i + 4 <= end_common:
                val_de = read_u32(de_data, i)
                val_fr = read_u32(fr_data, i)
                diffs.append((i, val_de, val_fr))
                i += 4
            else:
                diffs.append((i, de_data[i], fr_data[i]))
                i += 1
        else:
            i += 1

    if diffs:
        print(f"\n--- DIFF in {label} (0x{start:08X}–0x{end:08X}) ---")
        print(f"  {'Offset':>10}  {'DE':>12}  {'FR':>12}  {'Delta':>12}")
        for off, de_val, fr_val in diffs[:max_diffs]:
            if isinstance(de_val, int) and de_val > 0xFF:
                delta = fr_val - de_val
                print(f"  0x{off:08X}  0x{de_val:08X}  0x{fr_val:08X}  {delta:+d}")
            else:
                print(f"  0x{off:08X}  0x{de_val:02X}        0x{fr_val:02X}        -")
        if len(diffs) > max_diffs:
            print(f"  ... ({len(diffs) - max_diffs} weitere Unterschiede)")
    else:
        print(f"\n  [IDENTISCH] {label} (0x{start:08X}–0x{end:08X})")

    return diffs


def analyse_header_diffs(de_data, fr_data):
    """Vergleicht alle bekannten Header-Felder."""
    print("\n=== HEADER-DIFF (bekannte Felder) ===")
    print(f"  {'Offset':>10}  {'Feld':45s}  {'DE':>12}  {'FR':>12}  {'Delta':>12}")
    fields = [
        (0x0000, "script_table_offset"),
        (0x0004, "media_table_offset"),
        (0x000C, "additional_script_table_offset"),
        (0x0010, "game_table_offset"),
        (0x0018, "register_init_offset"),
        (0x0060, "additional_media_table_offset"),
        (0x0071, "power_on_sound_offset"),
        (0x008C, "media_flag_table_offset"),
        (0x0090, "game_binaries_table_offset"),
        (0x0094, "special_oid_list_offset"),
        (0x0098, "additional_game_binaries_offset"),
        (0x009C, "unknown_009C"),
        (0x00A0, "single_game_binary_offset"),
        (0x00A4, "flag_A4"),
        (0x00A8, "single_game_binary_2_offset"),
        (0x00C8, "single_game_binary_3_offset"),
        (0x00CC, "additional_game_binaries_3_offset"),
    ]
    for off, name in fields:
        de_val = read_u32(de_data, off)
        fr_val = read_u32(fr_data, off)
        delta = fr_val - de_val
        marker = " ← DIFFERS" if de_val != fr_val else ""
        print(f"  0x{off:04X}      {name:45s}  0x{de_val:08X}  0x{fr_val:08X}  {delta:+d}{marker}")


def analyse_post_audio(de_data, fr_data, de_audio_end, fr_audio_end):
    """Analysiert den Bereich nach den Audio-Daten (Spiele, etc.)."""
    de_post_len = len(de_data) - de_audio_end - 4  # -4 für Checksum
    fr_post_len = len(fr_data) - fr_audio_end - 4

    print(f"\n=== POST-AUDIO BEREICH ===")
    print(f"  DE: 0x{de_audio_end:08X} – 0x{len(de_data)-4:08X} ({de_post_len} Bytes)")
    print(f"  FR: 0x{fr_audio_end:08X} – 0x{len(fr_data)-4:08X} ({fr_post_len} Bytes)")

    if de_post_len != fr_post_len:
        print(f"  WARNUNG: Post-Audio-Bereich hat unterschiedliche Größe!")
        print(f"  Das macht direkten Byte-Vergleich schwierig.")
        return

    print(f"  Größe identisch: {de_post_len} Bytes ✓")

    # Diff des Post-Audio-Bereichs (am FR-Offset)
    de_section = de_data[de_audio_end:len(de_data)-4]
    fr_section = fr_data[fr_audio_end:len(fr_data)-4]

    diffs = []
    i = 0
    while i < len(de_section) and i < len(fr_section):
        if de_section[i] != fr_section[i]:
            if i + 4 <= min(len(de_section), len(fr_section)):
                de_val = struct.unpack_from("<I", de_section, i)[0]
                fr_val = struct.unpack_from("<I", fr_section, i)[0]
                diffs.append((i, de_val, fr_val))
                i += 4
            else:
                diffs.append((i, de_section[i], fr_section[i]))
                i += 1
        else:
            i += 1

    if diffs:
        print(f"\n  Unterschiede im Post-Audio-Bereich ({len(diffs)} Stellen):")
        print(f"  {'Rel.Offset':>12}  {'DE abs':>12}  {'FR abs':>12}  {'DE val':>12}  {'FR val':>12}  {'Delta':>12}")
        for rel_off, de_val, fr_val in diffs[:100]:
            de_abs = de_audio_end + rel_off
            fr_abs = fr_audio_end + rel_off
            delta = fr_val - de_val
            de_audio_shift = de_audio_end  # Audio-Start DE
            fr_audio_shift = fr_audio_end  # Audio-Start FR
            # Prüfe ob der Wert ein Pointer auf den Post-Audio-Bereich ist
            is_de_ptr = de_audio_end <= de_val < len(de_data)
            is_fr_ptr = fr_audio_end <= fr_val < len(fr_data)
            note = " [PTR→post-audio]" if is_de_ptr and is_fr_ptr else ""
            print(f"  +0x{rel_off:08X}  0x{de_abs:08X}  0x{fr_abs:08X}  0x{de_val:08X}  0x{fr_val:08X}  {delta:+d}{note}")
        if len(diffs) > 100:
            print(f"  ... ({len(diffs) - 100} weitere)")
    else:
        print("  Post-Audio-Bereich identisch! ✓")


def main():
    print(f"Lade DE: {DE}")
    print(f"Lade FR: {FR}")

    de_data = DE.read_bytes()
    fr_data = FR.read_bytes()

    print(f"\nDateigrößen:")
    print(f"  DE: {len(de_data):,} Bytes ({len(de_data):#010x})")
    print(f"  FR: {len(fr_data):,} Bytes ({len(fr_data):#010x})")
    print(f"  Delta: {len(fr_data) - len(de_data):+,} Bytes")

    # Header parsen
    de_hdr = parse_header(de_data, "DE Feuerwehr")
    fr_hdr = parse_header(fr_data, "FR Les pompiers")

    # Header-Diff
    analyse_header_diffs(de_data, fr_data)

    # Audio-Grenzen bestimmen
    de_media_off = de_hdr["media_table_offset"]
    fr_media_off = fr_hdr["media_table_offset"]
    de_add_media_off = de_hdr["additional_media_table_offset"]
    fr_add_media_off = fr_hdr["additional_media_table_offset"]

    de_audio_start = find_audio_start(de_data, de_media_off, de_add_media_off)
    fr_audio_start = find_audio_start(fr_data, fr_media_off, fr_add_media_off)
    de_audio_end = find_audio_end_from_header(de_data)
    fr_audio_end = find_audio_end_from_header(fr_data)

    de_entry_count = (de_add_media_off - de_media_off) // 8
    fr_entry_count = (fr_add_media_off - fr_media_off) // 8

    print(f"\n=== AUDIO-TABELLE ===")
    print(f"  DE: {de_entry_count} Einträge in Main-Tabelle")
    print(f"  FR: {fr_entry_count} Einträge in Main-Tabelle")

    print(f"\n=== AUDIO-GRENZEN ===")
    print(f"  DE Audio: 0x{de_audio_start:08X} – 0x{de_audio_end:08X} ({de_audio_end - de_audio_start:,} Bytes)")
    print(f"  FR Audio: 0x{fr_audio_start:08X} – 0x{fr_audio_end:08X} ({fr_audio_end - fr_audio_start:,} Bytes)")
    print(f"  Audio-Delta: {(fr_audio_end - fr_audio_start) - (de_audio_end - de_audio_start):+,} Bytes")
    print(f"  Post-Audio DE: 0x{de_audio_end:08X} – 0x{len(de_data)-4:08X} ({len(de_data)-4 - de_audio_end:,} Bytes)")
    print(f"  Post-Audio FR: 0x{fr_audio_end:08X} – 0x{len(fr_data)-4:08X} ({len(fr_data)-4 - fr_audio_end:,} Bytes)")

    # Pre-Audio diff (Header + Script + Spieltabellen)
    diff_region(de_data, fr_data, 0, min(de_audio_start, fr_audio_start),
                "PRE-AUDIO (Header+Scripts+Tabellen)", max_diffs=30)

    # Post-Audio diff
    analyse_post_audio(de_data, fr_data, de_audio_end, fr_audio_end)

    # Zusammenfassung: welche Header-Offsets passen zusammen?
    print(f"\n=== OFFSET-DELTA ANALYSE ===")
    audio_delta = fr_audio_start - de_audio_start
    print(f"  Audio-Start-Delta (FR - DE): {audio_delta:+d} Bytes")
    print(f"  (Positiv = FR Audio startet später als DE)")
    print()

    # Alle Header-Felder die sich ändern: sind das Pointer?
    for off, name in [
        (0x0000, "script_table_offset"),
        (0x000C, "additional_script_table_offset"),
        (0x0010, "game_table_offset"),
        (0x0018, "register_init_offset"),
        (0x0060, "additional_media_table_offset"),
        (0x0071, "power_on_sound_offset"),
        (0x008C, "media_flag_table_offset"),
        (0x0090, "game_binaries_table_offset"),
        (0x0094, "special_oid_list_offset"),
        (0x0098, "additional_game_binaries_offset"),
        (0x00A0, "single_game_binary_offset"),
        (0x00A8, "single_game_binary_2_offset"),
        (0x00C8, "single_game_binary_3_offset"),
        (0x00CC, "additional_game_binaries_3_offset"),
    ]:
        de_val = read_u32(de_data, off)
        fr_val = read_u32(fr_data, off)
        if de_val == 0 and fr_val == 0:
            continue
        if de_val != fr_val:
            delta = fr_val - de_val
            # Ist der Delta gleich dem Audio-Delta?
            match = "= audio_delta ✓" if delta == audio_delta else f"≠ audio_delta (erwartet {audio_delta:+d})"
            print(f"  0x{off:04X}  {name:45s}  delta={delta:+d}  {match}")


if __name__ == "__main__":
    main()
