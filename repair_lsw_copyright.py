#!/usr/bin/env python3
"""Repariert LSW_Uhr_und_Zeit GME: ersetzt copyright-TTS durch Original-OGGs."""
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

BASE  = Path("/home/dom/tiptoi-translate")
BOOK  = "LSW_Uhr_und_Zeit (1)"
GME   = BASE / "01_input" / f"{BOOK}.gme"
MEDIA = BASE / "02_unpacked" / BOOK / "media"
TRANSCRIPTS = BASE / "03_transcripts" / BOOK
TRANSLATED  = BASE / "04_translated"  / BOOK / "fr"
TTS_DIR     = BASE / "05_tts_output"  / BOOK / "fr"
YAML        = BASE / "02_unpacked"    / BOOK / f"{BOOK}.yaml"
OUTPUT      = BASE / "06_output"      / f"{BOOK}_fr_v26.gme"
TTTOOL      = str(Path.home() / ".local/bin/tttool")

NOISE_RE = re.compile(
    r"\b(WDR|SWR|NDR|MDR|BR\b|HR\b|RBB|SR\b|copyright|©|Rundfunk)\b",
    re.IGNORECASE,
)
NOISE_MAX_LEN = 60

def is_noise(text: str) -> bool:
    t = text.strip()
    return bool(t and len(t) <= NOISE_MAX_LEN and NOISE_RE.search(t))

def glob_escape(s: str) -> str:
    return s.replace("[", "[[]").replace("(", "[(]").replace(")", "[)]")

# 1. Betroffene Stems ermitteln
print("1. Betroffene Dateien ermitteln...")
affected: set[str] = set()
for f in TRANSCRIPTS.glob("*.txt"):
    text = f.read_text(encoding="utf-8")
    if is_noise(text):
        stem = re.sub(r"_v\d+$", "", f.stem)
        affected.add(stem)
print(f"   {len(affected)} betroffene Stems")

# 2. Original-OGGs aus GME extrahieren + wiederherstellen
print("2. Original-OGGs aus GME extrahieren...")
with tempfile.TemporaryDirectory() as tmpdir:
    subprocess.run([TTTOOL, "media", "-d", tmpdir, str(GME)], check=True)

    print("3. OGGs wiederherstellen + Übersetzungen leeren...")
    restored = 0
    missing  = []
    for stem in sorted(affected):
        orig_ogg = Path(tmpdir) / f"{stem}.ogg"
        dest_ogg = MEDIA / f"{stem}.ogg"

        if orig_ogg.exists():
            shutil.copy2(str(orig_ogg), str(dest_ogg))
            restored += 1
        else:
            missing.append(stem)
            print(f"   WARNUNG: Original nicht gefunden: {stem}.ogg")

        # Leere Übersetzungen schreiben (verhindert TTS beim nächsten Lauf)
        (TRANSLATED / f"{stem}_v26.txt").write_text("", encoding="utf-8")
        legacy = TRANSLATED / f"{stem}.txt"
        if legacy.exists():
            legacy.write_text("", encoding="utf-8")

    print(f"   {restored}/{len(affected)} OGGs wiederhergestellt")
    if missing:
        print(f"   Fehlend: {missing}")

# 4. MP3s löschen
print("4. MP3s löschen...")
deleted_mp3 = 0
for stem in affected:
    for mp3 in TTS_DIR.glob(f"{glob_escape(stem)}*.mp3"):
        mp3.unlink()
        deleted_mp3 += 1
print(f"   {deleted_mp3} MP3-Dateien gelöscht")

# 5. GME neu bauen
print("5. GME neu bauen...")
subprocess.run([TTTOOL, "assemble", str(YAML), str(OUTPUT)], check=True)
print(f"   Fertig: {OUTPUT}")

# 6. Sprache setzen
print("6. Sprache auf GERMAN setzen...")
subprocess.run([TTTOOL, "set-language", "GERMAN", str(OUTPUT)], check=True)
print("   GERMAN gesetzt")

print("\n=== Reparatur abgeschlossen ===")
