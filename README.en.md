# Tiptoi DE → FR / CH / VO / BY / ND Translator

A personal hobby project: automatically translating Tiptoi books (Ravensburger)
from German into another language. Takes a GME file, replaces the audio files,
and produces a new playable GME file.

Supported target languages: French, Swiss German, Vogtlandish, Bavarian, Low German.

> **Note:** This is not an official tool and not a polished product.
> It works for my use case — but there will certainly be books where it breaks.
> Feedback and improvements are welcome.

---

## Built on tttool and tip-toi-reveng

This project depends entirely on the work of the
[tip-toi-reveng](https://github.com/entropia/tip-toi-reveng) community.
Without `tttool` (GME unpacking, YAML, assemble) and the format documentation
maintained there, this project would not be possible.

---

## Why Google Colab for transcription?

My PC has no GPU, so no CUDA. Whisper runs on CPU only.

A typical Tiptoi book has **1,000–2,000 OGG files**. With the `small` model on CPU
that takes several hours; the more accurate `large-v3-turbo` model would be
practically unusable locally.

**Solution: offload step 2 (transcription) to Google Colab.**
Colab provides a free NVIDIA T4 GPU — `large-v3-turbo` runs ~1–2 seconds per file
there instead of minutes. The finished TXT transcripts are placed back into
`03_transcripts/`; all other steps run locally.

```
Local PC:  unpack GME → zip OGGs → upload
Colab:     unzip OGGs → Whisper large-v3-turbo → zip TXTs → download
Local PC:  unzip TXTs → translate → TTS → pack GME
```

---

## Workflow (6 steps)

| Step | Description | Tool |
|------|-------------|------|
| 1 | Unpack GME (YAML + OGG) | `tttool export` / `tttool media` |
| 2 | Transcribe DE | faster-whisper (`small` local / `large-v3-turbo` Colab) |
| 3 | Translate DE → target language | Mistral API (`magistral-medium-latest`) |
| 4 | TTS | edge-tts |
| 5 | OGG conversion | ffmpeg (mono, 22050 Hz) |
| 6 | Repack GME | `tttool assemble` or `gme_patch.py` (binary patch) |

---

## Requirements

- Python 3.13+
- ffmpeg 7.1+ (`sudo apt install ffmpeg`)
- tttool 1.11 at `~/.local/bin/tttool`
  → Download: https://github.com/entropia/tip-toi-reveng/releases
- Mistral API key (https://console.mistral.ai/)

---

## Setup

```bash
# install tttool
mkdir -p ~/.local/bin
cp tttool ~/.local/bin/tttool
chmod +x ~/.local/bin/tttool

# Python environment
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# API key
cp .env.example .env
nano .env   # MISTRAL_API_KEY=your_key_here
```

---

## Usage

```bash
# place GME in 01_input/, then:
./tiptoi.sh 01_input/book.gme

# Swiss German
./tiptoi.sh 01_input/book.gme --language ch

# Bavarian
./tiptoi.sh 01_input/book.gme --language by

# Vogtlandish
./tiptoi.sh 01_input/book.gme --language vo

# Low German
./tiptoi.sh 01_input/book.gme --language nd

# binary patch (preserves game logic, experimental):
./tiptoi.sh 01_input/book.gme --use-patcher

# first 10 files only (test run)
./tiptoi.sh 01_input/book.gme --limit 10

# larger Whisper model
./tiptoi.sh 01_input/book.gme --whisper-model medium
```

The finished file ends up in `06_output/book_fr.gme` (or `_ch`, `_vo`, `_by`, `_nd`).
Resume works automatically — just run the same command again.

### All options

```bash
python pipeline.py 01_input/book.gme [OPTIONS]

  --language LANG         Target language: fr, ch, vo, by, nd  (default: fr)
  --voice VOICE           edge-tts voice (overrides language default)
  --whisper-model MODEL   Whisper model: tiny, base, small, medium, large-v3-turbo
                          (default: small)
  --limit N               Process only the first N audio files (0 = all)
  --use-patcher           [experimental] step 6 via gme_patch.py instead of tttool assemble
  --skip-assemble         Skip step 6 (OGGs remain for manual patching)
  --offline               Run everything locally (no Colab pause)
  --min-k N               Minimum number of speaker clusters (default: 2)
```

---

## A note on dialects

**Swiss German** works reasonably well — the CH voices in edge-tts sound convincing
and Mistral translates into Swiss German solidly.

**Vogtlandish, Bavarian, and Low German** unfortunately tend to sound like standard
German. There are no proper dialect TTS voices available; the DE/AT/CH voices
don't convey much dialectal character. Mistral's translation quality for these
dialects is also limited. These language options are therefore more experimental
than practical.

---

## Voices (8 per language)

Each language has 8 edge-tts voices (4m/4f). Speakers are automatically detected
via **resemblyzer** (GE2E embeddings) and assigned to voices. The result is saved
as `speakers.json` per book.

**French (`--language fr`)**

| # | Voice | Type |
|---|-------|------|
| 0 | `fr-FR-HenriNeural` | m, deep narrator |
| 1 | `fr-FR-EloiseNeural` | f, child voice |
| 2 | `fr-BE-CharlineNeural` | f, Belgian (child 2) |
| 3 | `fr-FR-RemyMultilingualNeural` | m, natural |
| 4 | `fr-FR-VivienneMultilingualNeural` | f, narrator |
| 5 | `fr-FR-DeniseNeural` | f, warm/mature |
| 6 | `fr-BE-GerardNeural` | m, Belgian |
| 7 | `fr-CH-FabriceNeural` | m, Swiss FR |

**Swiss German (`--language ch`)**

| # | Voice | Type |
|---|-------|------|
| 0 | `de-CH-JanNeural` | m, Swiss German |
| 1 | `de-CH-LeniNeural` | f, Swiss German |
| 2 | `de-AT-JonasNeural` | m, Austrian |
| 3 | `de-AT-IngridNeural` | f, Austrian |
| 4 | `de-DE-FlorianMultilingualNeural` | m, multilingual |
| 5 | `de-DE-SeraphinaMultilingualNeural` | f, multilingual |
| 6 | `de-DE-ConradNeural` | m, standard German |
| 7 | `de-DE-KatjaNeural` | f, standard German |

**Vogtlandish (`--language vo`)**

| # | Voice | Type |
|---|-------|------|
| 0 | `de-DE-FlorianMultilingualNeural` | m, multilingual |
| 1 | `de-DE-SeraphinaMultilingualNeural` | f, multilingual |
| 2 | `de-DE-ConradNeural` | m |
| 3 | `de-DE-KatjaNeural` | f |
| 4 | `de-DE-KillianNeural` | m |
| 5 | `de-DE-AmalaNeural` | f |
| 6 | `de-CH-JanNeural` | m |
| 7 | `de-AT-IngridNeural` | f |

**Bavarian (`--language by`)**

| # | Voice | Type |
|---|-------|------|
| 0 | `de-AT-JonasNeural` | m, Austrian |
| 1 | `de-AT-IngridNeural` | f, Austrian |
| 2 | `de-DE-FlorianMultilingualNeural` | m, multilingual |
| 3 | `de-DE-SeraphinaMultilingualNeural` | f, multilingual |
| 4 | `de-CH-JanNeural` | m |
| 5 | `de-CH-LeniNeural` | f |
| 6 | `de-DE-ConradNeural` | m |
| 7 | `de-DE-KatjaNeural` | f |

**Low German (`--language nd`)**

| # | Voice | Type |
|---|-------|------|
| 0 | `de-DE-FlorianMultilingualNeural` | m, multilingual |
| 1 | `de-DE-SeraphinaMultilingualNeural` | f, multilingual |
| 2 | `de-DE-KillianNeural` | m |
| 3 | `de-DE-KatjaNeural` | f |
| 4 | `de-DE-ConradNeural` | m |
| 5 | `de-DE-AmalaNeural` | f |
| 6 | `de-AT-JonasNeural` | m |
| 7 | `de-CH-LeniNeural` | f |

---

## Folder structure

```
01_input/       input GME files
02_unpacked/    tttool output (YAML + OGG)
03_transcripts/ Whisper transcripts (DE)
04_translated/  Mistral translations
05_tts_output/  edge-tts MP3 files
06_output/      finished *_fr / *_ch / *_vo / *_by / *_nd .gme
backup/         versioned script backups
```

---

## Stack

- Python 3.13, faster-whisper, mistralai (Magistral), edge-tts, resemblyzer, python-dotenv
- tttool 1.11 (Haskell binary, by the tip-toi-reveng community)
- gme_patch.py / gme_patch_same_lenght.py (binary patch, experimental)
- ffmpeg 7.1

---

## Acknowledgements

This project would not exist without the groundwork laid by the
[tip-toi-reveng](https://github.com/entropia/tip-toi-reveng) community —
in particular the complete GME format documentation, `tttool`, and
`libtiptoi.c` by Michael Wolf. Thank you for years of reverse-engineering work.

---

## License

MIT License — see [LICENSE](LICENSE)
