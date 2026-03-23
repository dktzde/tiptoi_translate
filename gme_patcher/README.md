# gme_patch.py – Tiptoi GME Audio Patcher

Replaces audio files in Tiptoi `.gme` files using a direct binary patch –
**without tttool's export/assemble round-trip**, which destroys interactive games.

## The Problem

`tttool export` + `tttool assemble` loses 8 unknown segments (~4526 bytes)
containing game logic and firmware data. After reassembly, interactive games
(quizzes, puzzles) no longer work.

**Confirmed by tttool author Joachim Breitner**: in-place audio replacement is
the correct approach.

## The Solution

`gme_patch.py` patches the binary directly:

```
Original GME     New OGGs         Output GME
┌──────────┐                     ┌──────────┐
│ Header   │ ──────────────────► │ Header   │  (unchanged, bit-for-bit)
│ Scripts  │ ──────────────────► │ Scripts  │  (unchanged, bit-for-bit)
│ Games    │ ──────────────────► │ Games    │  (unchanged, bit-for-bit)
│ Audio ①  │    Feuerwehr_0.ogg  │ Audio ①' │  (replaced + re-encrypted)
│ Audio ②  │    Feuerwehr_1.ogg  │ Audio ②' │  (replaced + re-encrypted)
│ ...      │    ...              │ ...      │
│ Checksum │                     │ Checksum │  (recalculated)
└──────────┘                     └──────────┘
```

## Usage

```bash
# Patch audio:
python gme_patch.py original.gme media_dir/ output.gme

# Show file info:
python gme_patch.py -i original.gme
```

### media_dir naming

Files in `media_dir/` are matched to audio table indices by the **last number**
in the filename:

```
media_dir/
  Feuerwehr_0.ogg    → index 0
  Feuerwehr_1.ogg    → index 1
  Feuerwehr_42.ogg   → index 42
  0000.ogg           → index 0    (libtiptoi-style)
```

Files without a replacement are kept from the original GME.

## GME Format (brief)

- Header at `0x0004`: 32-bit offset to audio file table
- Audio table: N × `(offset: u32, length: u32)` pairs, immediately before audio data
- Entry count: `(first_audio_offset − table_offset) / 8`
- Audio XOR encryption: find key `x` such that `first_bytes XOR x == "OggS"`
- XOR rules: `0x00`, `0xFF`, `x`, `x^0xFF` → unchanged; all others XOR'd with `x`
- Checksum: sum of all bytes, stored as last 4 bytes (little-endian)
- Additional audio table at `0x0060` (same content, both updated)

## Requirements

- Python 3.13+ (stdlib only, no dependencies)
- For the test workflow: ffmpeg (MP3 → OGG conversion)

## Files

```
gme_patcher/
  gme_patch.py          – The patcher (no external dependencies)
  CHANGELOG.md          – Version history
  NOTES.md              – Background & motivation
  tip-toi-reveng/       – Reference implementation & format docs (offline copy)
    GME-Format.md       – Complete format documentation
    libtiptoi.c         – C reference (Michael Wolf, MIT License)
    src/GMEParser.hs    – Haskell parser (tttool)
    src/GMEWriter.hs    – Haskell writer (tttool)
```

## Credits

GME format reverse-engineered by the
[tip-toi-reveng](https://github.com/entropia/tip-toi-reveng) community.
libtiptoi.c by Michael Wolf (MIT License).
