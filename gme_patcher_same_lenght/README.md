# gme_patch_same_lenght

Binary audio patcher for Tiptoi GME files — **shift=0 guaranteed**.

Every replacement audio is adjusted to exactly match the original entry's byte length.
Since the audio section never changes in size, all post-audio pointers (game binaries,
play scripts) remain valid without any pointer shifting.

## Why shift=0 matters

Tiptoi GME files contain game binaries after the audio section. When the audio
section changes size, every pointer to that post-audio region must be updated.
This is complex and error-prone. By keeping every audio entry at its original size,
the post-audio section stays at the same file offset — no pointer updates needed,
games work correctly.

## Usage

```bash
python gme_patch_same_lenght.py original.gme media_dir/ output.gme
python gme_patch_same_lenght.py original.gme media_dir/ output.gme \
       --lang fr \
       --speakers-json 03_transcripts/Book/speakers.json \
       --transcripts-dir 03_transcripts/Book/
python gme_patch_same_lenght.py -i original.gme   # info only
```

## Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `original_gme` | — | Input GME file |
| `media_dir/` | — | Folder with replacement OGG files |
| `output_gme` | — | Output GME file |
| `--lang` | `fr` | Target language: `fr` `ch` `vo` `by` `nd` |
| `--voice` | `fr-FR-HenriNeural` | Default Edge-TTS voice (fallback) |
| `--max-diff` | `0.20` | Threshold for interactive menu (0.20 = 20%) |
| `--speakers-json` | None | speakers.json for per-file voice assignment |
| `--transcripts-dir` | None | `03_transcripts/{book}/` for Option 3 retranslation |

## How size adjustment works

| Situation | Method |
|-----------|--------|
| New audio shorter than original | Zero-padding appended |
| Up to `--max-diff` too large | `atempo` speedup via ffmpeg |
| Over `--max-diff`, interactive mode | Menu: manual / ffmpeg / Mistral roundtrip |
| `max_diff=inf` (pipeline mode) | Always ffmpeg truncation, never interactive |

### Interactive menu (Option 3 — Mistral roundtrip)

Requires `--transcripts-dir`. No Whisper run needed — the German text is read
from the existing transcript files created by the pipeline.

```
[1] Enter new text manually → Edge-TTS
[2] Duration reduction (ffmpeg -t)
[3] DE transcript → Mistral shorten+translate → Edge-TTS  ← auto after 3 min
```

**Flow for Option 3:**
1. Load German transcript from `03_transcripts/{book}/{stem}_v*.txt`
2. Calculate target character count: `len(de_text) × (orig_bytes / new_bytes) × 0.85`
3. Call Mistral with language-specific shorten+translate prompt
4. Generate new TTS with Edge-TTS using the correct voice from `speakers.json`
5. If still too large: apply `atempo` or `ffmpeg -t` as fallback

## Output files

| File | Description |
|------|-------------|
| `output.gme` | Patched GME, shift=0, games intact |
| `output.log` | Per-entry log: index, method, sizes, voice |

## Log format

```
idx   method                  orig     new    voice                              stem
----  ----------------------  -------  -----  ---------------------------------  ----
   0  ok                        8,041  8,041  fr-FR-HenriNeural                  Book_0
   2  atempo                    6,880  6,880  fr-FR-HenriNeural                  Book_2
  11  retranslated             29,211  29,011  fr-FR-EloiseNeural                Book_11
  44  truncated                13,024  13,024  fr-BE-CharlineNeural              Book_44
```

**Methods:**
- `ok` — no resizing needed
- `atempo` — sped up via ffmpeg atempo filter
- `retranslated` — German text → Mistral → Edge-TTS
- `retranslated+atempo` — retranslated, then additionally sped up
- `retranslated+truncated` — retranslated, then additionally truncated
- `truncated` — duration reduced via ffmpeg -t
- `manual` — text entered manually
- `kept` — original audio kept (no replacement OGG available)

## Supported languages

| Code | Language | Example voices |
|------|----------|----------------|
| `fr` | French | `fr-FR-HenriNeural`, `fr-FR-EloiseNeural` |
| `ch` | Swiss German | `de-CH-JanNeural`, `de-CH-LeniNeural` |
| `vo` | Vogtlandish | `de-DE-FlorianMultilingualNeural` |
| `by` | Bavarian | `de-AT-JonasNeural`, `de-AT-IngridNeural` |
| `nd` | Low German | `de-DE-FlorianMultilingualNeural` |

## Pipeline integration

```bash
python pipeline.py 01_input/book.gme --language fr --use-patcher-sl
```

The pipeline passes `speakers_json`, `transcripts_dir`, and `max_diff=inf` automatically.

## Requirements

- Python 3.10+
- `ffmpeg` / `ffprobe`
- `edge-tts` (`pip install edge-tts`)
- `mistralai` + `MISTRAL_API_KEY` in `.env` (for Option 3 only)
- `python-dotenv` (for `.env` loading)
