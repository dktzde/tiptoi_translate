"""
Tiptoi DE → FR / CH Pipeline
==============================
Workflow pro Audiodatei:
  1. GME entpacken      (tttool)
  2. Pro OGG-Datei:
     a) Transkribieren  (faster-whisper, DE) → txt
     b) Übersetzen      (Mistral API, DE→Zielsprache) → txt
     c) TTS generieren  (edge-tts)          → mp3
     d) OGG konvertieren (ffmpeg)           → ogg
  3. GME neu packen     (tttool)

Verwendung:
  python pipeline.py 01_input/buch.gme
  python pipeline.py 01_input/buch.gme --language ch
  python pipeline.py 01_input/buch.gme --voice fr-FR-VivienneMultilingualNeural
  python pipeline.py 01_input/buch.gme --whisper-model base
  python pipeline.py 01_input/buch.gme --limit 10
  python pipeline.py 01_input/buch.gme --use-patcher   [ALPHA] Schritt 6 via gme_patch.py statt tttool
"""

import os
import gc
import re
import sys
import json
import time
import asyncio
import subprocess
import argparse
import zipfile
from pathlib import Path

import numpy as np
from resemblyzer import VoiceEncoder, preprocess_wav
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import normalize
from dotenv import load_dotenv
import emoji
import edge_tts
from faster_whisper import WhisperModel
from mistralai import Mistral

load_dotenv()

# ─── Konfiguration ────────────────────────────────────────────────────────────

BASE_DIR        = Path(__file__).parent
INPUT_DIR       = BASE_DIR / "01_input"
UNPACKED_DIR    = BASE_DIR / "02_unpacked"
OUTPUT_DIR      = BASE_DIR / "06_output"
COLAB_DIR       = BASE_DIR / "07_colab_upload"

TTTOOL          = "tttool"
DEFAULT_LANGUAGE = "fr"
DEFAULT_WHISPER  = "small"
PIPELINE_VERSION     = "v32"  # wird an alle erzeugten Dateinamen angehängt
NOISE_MIX_MIN_SEC    = 0.5    # Geräuschanteil < dieser Wert → kein Mix, nur TTS
MIN_RESUME_VERSION   = 29     # v29-Transkripte weiterhin gültig (kein Whisper-Neulauf)
                               # Dateien älter als v{MIN_RESUME_VERSION} werden ignoriert
                               # v30: --skip-assemble Flag (für gme_patch.py Workflow)
                               # v32: --use-patcher Flag (ALPHA): Schritt 6 via gme_patch.py

# Tiptoi-kompatibles OGG-Format (Mono, 22050 Hz)
OGG_CHANNELS   = "1"
OGG_SAMPLERATE = "22050"

# ─── Sprach-Konfiguration ─────────────────────────────────────────────────────

LANG_CONFIG = {
    "fr": {
        "voices": [
            "fr-FR-HenriNeural",                  # 0 – tief (männl. Erzähler)
            "fr-FR-EloiseNeural",                  # 1 – weibl. Kinderstimme
            "fr-BE-CharlineNeural",                # 2 – weibl. jünger (Kind 2)
            "fr-FR-RemyMultilingualNeural",        # 3 – männl. natürlich (Mann 2)
            "fr-FR-VivienneMultilingualNeural",    # 4 – weibl. natürlich (Erzählerin)
        ],
        "model": "mistral-medium-latest",
        "temperature": 0.8,
        "suffix": "_fr",
        "label": "FR",
        "system_prompt": (
            "Tu es un traducteur pour livres enfants. "
            "Traduis le texte allemand suivant en français naturel et adapté aux enfants. "
            "Réponds uniquement avec la traduction, sans explications."
        ),
    },
    "ch": {
        "voices": [
            "de-CH-JanNeural",    # 0 – männl. (Schweizerdeutsch)
            "de-CH-LeniNeural",   # 1 – weibl. (Schweizerdeutsch)
            "de-AT-JonasNeural",  # 2 – männl. (Österreichisch, näher an CH als Hochdeutsch)
        ],
        "model": "mistral-medium-latest",
        "temperature": 0.3,
        "suffix": "_ch",
        "label": "CH",
        "system_prompt": (
            "Übersetze die folgenden Tiptoi-Sätze in natürliches Schweizerdeutsch "
            "(Berner Dialekt), verwende einfache Wörter für Kinder und schreibe es so, "
            "wie man es spricht (phonetisch für TTS). "
            "Antworte nur mit der Übersetzung, ohne Erklärungen."
        ),
    },
}


# ─── Geräusch-/Copyright-Erkennung ───────────────────────────────────────────

_NOISE_RE = re.compile(
    r"\b(WDR|SWR|NDR|MDR|BR\b|HR\b|RBB|SR\b|copyright|©|Rundfunk)\b",
    re.IGNORECASE,
)
_NOISE_MAX_LEN = 60  # Zeichen – längere Texte sind echter Inhalt

def _is_noise_transcript(text: str) -> bool:
    """True wenn der Text eine Urheberrechts-Einblendung oder Rundfunk-Attribution ist.
    Solche OGGs enthalten Geräusche/Jingles, kein übersetzbarer Sprachinhalt."""
    t = text.strip()
    return bool(t and len(t) <= _NOISE_MAX_LEN and _NOISE_RE.search(t))


# Markdown-Bereinigung vor TTS
_MD_RE = re.compile(
    r'\*{1,3}|_{1,3}|`{1,3}|~~|^\s*#{1,6}\s*'   # **, *, __, _, ```, ##
    r'|[^\x00-\x7F\u00C0-\u024F\u1E00-\u1EFF]',   # Emojis und non-latin Unicode
    re.MULTILINE
)

def _clean_translation(text: str) -> str:
    """Entfernt Markdown-Formatierung und Emojis aus Übersetzungstext vor TTS."""
    cleaned = emoji.replace_emoji(text, replace='')  # Unicode-Emojis entfernen
    cleaned = _MD_RE.sub('', cleaned)
    cleaned = re.sub(r':[a-z_]+:', '', cleaned)       # :emoji_name: Kurzform entfernen
    cleaned = re.sub(r'\s*[–—]\s*', ', ', cleaned)   # Gedankenstrich → Sprechpause
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned


# ─── Resume-Hilfsfunktion ─────────────────────────────────────────────────────

def _find_resume(directory: Path, stem: str, ext: str) -> Path | None:
    """Sucht die neueste kompatible Version einer Datei für Resume.
    Akzeptiert Versionen von MIN_RESUME_VERSION bis PIPELINE_VERSION.
    Fallback: unverstionierte Datei (erstellt vor v2.6, gilt als kompatibel).
    Gibt None zurück wenn keine kompatible Datei gefunden wurde."""
    current = int(PIPELINE_VERSION[1:])
    for num in range(current, MIN_RESUME_VERSION - 1, -1):
        f = directory / f"{stem}_v{num}{ext}"
        if f.exists():
            return f
    # Legacy-Fallback: Dateien ohne Versionssuffix (vor v2.6 erstellt)
    legacy = directory / f"{stem}{ext}"
    if legacy.exists():
        return legacy
    return None


# ─── Sprecher-Erkennung (resemblyzer GE2E Embeddings) ────────────────────────

def cluster_speakers(ogg_files: list[Path], num_voices: int) -> tuple[dict[str, int], int, float]:
    """Speaker-Clustering via resemblyzer GE2E Embeddings + KMeans.
    Gibt (voice_map, best_k, best_score) zurück."""
    print(f"  Lade resemblyzer Modell...", flush=True)
    encoder = VoiceEncoder(device="cpu")

    embeddings: dict[str, np.ndarray] = {}
    for i, ogg in enumerate(ogg_files, 1):
        if i % 100 == 0 or i == len(ogg_files):
            print(f"  Embeddings: {i}/{len(ogg_files)}", flush=True)
        try:
            wav = preprocess_wav(str(ogg))
            if len(wav) < 1600:   # kürzer als 100ms → überspringen
                continue
            embeddings[ogg.stem] = encoder.embed_utterance(wav)
        except Exception:
            continue

    del encoder
    gc.collect()

    if len(embeddings) < 2:
        print("  Zu wenige Sprach-Dateien – verwende eine Stimme.")
        return {}, 1, 0.0

    stems = list(embeddings.keys())
    X     = normalize(np.stack(list(embeddings.values())))

    max_k = min(7, len(stems) - 1)
    best_k, best_score = 1, -1.0
    for k in range(2, max_k + 1):
        km    = KMeans(n_clusters=k, random_state=0, n_init="auto").fit(X)
        score = silhouette_score(X, km.labels_)
        if score > best_score:
            best_k, best_score = k, score

    km = KMeans(n_clusters=best_k, random_state=0, n_init="auto").fit(X)
    voice_map = {stem: int(lbl) for stem, lbl in zip(stems, km.labels_)}

    counts = [int((km.labels_ == i).sum()) for i in range(best_k)]
    print(f"  {best_k} Sprecher erkannt (Silhouette {best_score:.2f}):")
    for i, n in enumerate(counts):
        print(f"    Gruppe {i}: {n} Dateien")

    return voice_map, best_k, best_score


def save_speakers(voice_map: dict[str, int], speakers_file: Path,
                  num_speakers: int, silhouette: float) -> None:
    """Speichert Sprecher-Zuordnung sprach-unabhängig als JSON."""
    data = {
        "num_speakers": num_speakers,
        "silhouette":   round(silhouette, 3),
        "voice_map":    voice_map,
    }
    speakers_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  Sprecher-Profil gespeichert: {speakers_file.name}")


def load_speakers(speakers_file: Path) -> dict[str, int] | None:
    """Lädt gespeicherte Sprecher-Zuordnung. Gibt None zurück wenn nicht vorhanden."""
    if not speakers_file.exists():
        return None
    data = json.loads(speakers_file.read_text(encoding="utf-8"))
    vm = data.get("voice_map", {})
    print(f"  Sprecher-Profil geladen: {data['num_speakers']} Sprecher "
          f"(Silhouette {data['silhouette']}) – {len(vm)} Dateien")
    return {k: int(v) for k, v in vm.items()}


# ─── GME entpacken ────────────────────────────────────────────────────────────

def unpack_gme(gme_file: Path) -> Path:
    book_name = gme_file.stem
    out_dir = UNPACKED_DIR / book_name
    out_dir.mkdir(parents=True, exist_ok=True)
    gme_abs = str(gme_file.resolve())

    yaml_out = out_dir / f"{book_name}.yaml"
    if yaml_out.exists():
        yaml_out.unlink()
    print(f"  tttool export → {yaml_out.name}")
    subprocess.run([TTTOOL, "export", gme_abs, str(yaml_out)], check=True)

    media_dir = out_dir / "media"
    media_dir.mkdir(exist_ok=True)
    print(f"  tttool media  → {media_dir}/")
    subprocess.run([TTTOOL, "media", "-d", str(media_dir), gme_abs], check=True)

    return out_dir


# ─── GME neu packen ───────────────────────────────────────────────────────────

def repack_gme(book_dir: Path, output_dir: Path, suffix: str, tts_dir: Path | None = None) -> Path:
    yaml_files = list(book_dir.glob("*.yaml"))
    if not yaml_files:
        raise FileNotFoundError(f"Keine YAML-Datei in {book_dir} gefunden")

    # Bevorzuge Haupt-YAML (ohne .codes.) gegenüber codes.yaml
    main_yamls = [f for f in yaml_files if ".codes." not in f.name]
    yaml_file = main_yamls[0] if main_yamls else yaml_files[0]
    output_dir.mkdir(parents=True, exist_ok=True)
    out_gme = output_dir / f"{book_dir.name}{suffix}_{PIPELINE_VERSION}.gme"

    print(f"  tttool assemble → {out_gme.name}")

    if tts_dir and tts_dir.exists():
        # Temp-Dir: Original-OGGs + übersetzte OGGs als Overlay – 02_unpacked bleibt unberührt
        import tempfile, shutil
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path  = Path(tmp)
            tmp_media = tmp_path / "media"
            tmp_media.mkdir()
            # Originals verlinken (kein Kopieren → schnell), alle Audioformate
            for audio in (book_dir / "media").iterdir():
                if audio.suffix.lower() in (".ogg", ".wav", ".mp3", ".flac"):
                    (tmp_media / audio.name).symlink_to(audio.resolve())
            # Übersetzte OGGs ersetzen die Symlinks
            for ogg in tts_dir.glob("*.ogg"):
                dest = tmp_media / ogg.name
                if dest.exists() or dest.is_symlink():
                    dest.unlink()
                shutil.copy2(ogg, dest)
            # YAML in Temp-Dir kopieren (tttool liest media/ relativ zur YAML)
            tmp_yaml = tmp_path / yaml_file.name
            shutil.copy2(yaml_file, tmp_yaml)
            subprocess.run(
                [TTTOOL, "assemble", str(tmp_yaml), str(out_gme)],
                check=True,
            )
    else:
        subprocess.run(
            [TTTOOL, "assemble", str(yaml_file), str(out_gme)],
            check=True,
        )
    return out_gme


# ─── Pro-Datei: Transkription ─────────────────────────────────────────────────

def transcribe_one(ogg_file: Path, model: WhisperModel, transcript_file: Path) -> str:
    if transcript_file.exists():
        return transcript_file.read_text(encoding="utf-8")

    segments, _ = model.transcribe(str(ogg_file), language="de")
    text = " ".join(s.text for s in segments).strip()
    transcript_file.write_text(text, encoding="utf-8")
    return text


# ─── Pro-Datei: Übersetzung ───────────────────────────────────────────────────

def translate_one(text: str, client: Mistral, translation_file: Path, system_prompt: str, model: str, temperature: float | None = None) -> str:
    if translation_file.exists():
        return translation_file.read_text(encoding="utf-8")

    if not text.strip():
        translation_file.write_text("", encoding="utf-8")
        return ""

    kwargs = dict(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text},
        ],
    )
    if temperature is not None:
        kwargs["temperature"] = temperature

    waits = [60, 90, 180]
    for attempt in range(len(waits) + 1):
        try:
            resp = client.chat.complete(**kwargs)
            translated = resp.choices[0].message.content.strip()
            translation_file.write_text(translated, encoding="utf-8")
            return translated
        except Exception as e:
            if ("429" in str(e) or "rate" in str(e).lower()) and attempt < len(waits):
                wait = waits[attempt]
                print(f"    ⚠ RATE LIMIT #{attempt+1} – warte {wait}s ({translation_file.stem})", flush=True)
                time.sleep(wait)
            else:
                raise

    raise RuntimeError("Mistral Rate Limit: alle Versuche ausgeschöpft")


# ─── Batch-Übersetzung ────────────────────────────────────────────────────────

BATCH_SIZE    = 10
BATCH_SEP     = "<<<{i}>>>"   # Trennmarker im Prompt

def translate_batch(
    pending: list[tuple[str, Path]],   # (text, translation_file)
    client: Mistral,
    system_prompt: str,
    model: str,
    temperature: float | None = None,
) -> None:
    """Übersetzt pending-Texte in Batches. Bereits vorhandene Dateien werden übersprungen."""
    todo = [(t, f) for t, f in pending if not f.exists() and t.strip()]
    if not todo:
        return

    total_batches = (len(todo) + BATCH_SIZE - 1) // BATCH_SIZE
    print(f"  Batch-Übersetzung: {len(todo)} Texte in {total_batches} Batches (à {BATCH_SIZE})", flush=True)

    for b_idx in range(0, len(todo), BATCH_SIZE):
        batch = todo[b_idx: b_idx + BATCH_SIZE]
        b_num = b_idx // BATCH_SIZE + 1

        numbered = "\n\n".join(
            f"<<<{i+1}>>>\n{text}" for i, (text, _) in enumerate(batch)
        )
        user_msg = (
            f"Übersetze jeden der folgenden {len(batch)} Texte einzeln. "
            f"Antworte exakt in diesem Format – behalte die Marker <<<N>>> bei:\n\n{numbered}"
        )

        kwargs: dict = dict(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_msg},
            ],
        )
        if temperature is not None:
            kwargs["temperature"] = temperature

        waits = [60, 90, 180]
        result = ""
        for attempt in range(len(waits) + 1):
            try:
                resp   = client.chat.complete(**kwargs)
                result = resp.choices[0].message.content
                break
            except Exception as e:
                if ("429" in str(e) or "rate" in str(e).lower()) and attempt < len(waits):
                    wait = waits[attempt]
                    print(f"  ⚠ RATE LIMIT #{attempt+1} – warte {wait}s (Batch {b_num})", flush=True)
                    time.sleep(wait)
                else:
                    raise

        # ─── Antwort parsen ───────────────────────────────────────────────────
        parsed_ok = 0
        for i, (text, translation_file) in enumerate(batch):
            marker      = f"<<<{i+1}>>>"
            next_marker = f"<<<{i+2}>>>"
            start = result.find(marker)
            if start == -1:
                # Fallback: Einzelaufruf
                print(f"  ⚠ Marker fehlt für {translation_file.stem} – Einzelaufruf", flush=True)
                translate_one(text, client, translation_file, system_prompt, model, temperature)
                continue
            start += len(marker)
            end = result.find(next_marker, start) if i + 1 < len(batch) else len(result)
            translated = result[start:end].strip()
            translation_file.write_text(translated, encoding="utf-8")
            parsed_ok += 1

        print(f"  Batch {b_num}/{total_batches}: {parsed_ok}/{len(batch)} OK", flush=True)
        time.sleep(0.5)


# ─── Pro-Datei: TTS ───────────────────────────────────────────────────────────

async def tts_one(fr_text: str, mp3_file: Path, voice: str) -> bool:
    """Gibt True zurück bei Erfolg, False bei Fehler (überspringen)."""
    if mp3_file.exists():
        return True
    try:
        communicator = edge_tts.Communicate(fr_text, voice=voice)
        await communicator.save(str(mp3_file))
        return True
    except Exception as e:
        print(f"    ⚠ TTS Fehler – überspringe: {mp3_file.name} ({e})", flush=True)
        if mp3_file.exists():
            mp3_file.unlink()
        return False


# ─── Speech-Timestamps laden (aus Colab _ts.json) ────────────────────────────

def _get_speech_timing(stem: str, transcripts_dir: Path) -> tuple[float, float, float] | None:
    """Lädt Speech-Timestamps aus Colab-generierter JSON.
    Gibt (speech_start, speech_end, total_duration) oder None zurück."""
    ts_file = transcripts_dir / f"{stem}_{PIPELINE_VERSION}_ts.json"
    if not ts_file.exists():
        return None
    data = json.loads(ts_file.read_text(encoding="utf-8"))
    return data.get("start", 0.0), data.get("end", 0.0), data.get("duration", 0.0)


# ─── Pro-Datei: OGG konvertieren ──────────────────────────────────────────────

def convert_to_ogg(mp3_file: Path, ogg_file: Path):
    subprocess.run(
        [
            "ffmpeg", "-y", "-i", str(mp3_file),
            "-c:a", "libvorbis",
            "-ac", OGG_CHANNELS,
            "-ar", OGG_SAMPLERATE,
            "-q:a", "4",
            str(ogg_file),
        ],
        check=True,
        capture_output=True,
    )


# ─── Gemischtes OGG: Original-Geräusch + TTS-Stimme ─────────────────────────

def mix_with_original(original_ogg: Path, mp3_file: Path, ogg_out: Path,
                      start: float, end: float, duration: float) -> bool:
    """Mischt Original-Geräusch mit TTS-Stimme via ffmpeg concat.
    Gibt True zurück wenn Mix sinnvoll, False wenn einfaches convert_to_ogg besser."""
    has_noise_start = start > NOISE_MIX_MIN_SEC
    has_noise_end   = end < duration - NOISE_MIX_MIN_SEC

    if not has_noise_start and not has_noise_end:
        return False  # kein nennenswertes Geräusch → normaler TTS-Pfad

    if has_noise_start and not has_noise_end:
        # Geräusch vorne: original[0:start] + TTS
        filt = (f"[0:a]atrim=0:{start},asetpts=PTS-STARTPTS[noise];"
                f"[noise][1:a]concat=n=2:v=0:a=1[out]")
        inputs = [str(original_ogg), str(mp3_file)]
    elif has_noise_end and not has_noise_start:
        # Geräusch hinten: TTS + original[end:]
        filt = (f"[1:a]atrim={end},asetpts=PTS-STARTPTS[noise];"
                f"[0:a][noise]concat=n=2:v=0:a=1[out]")
        inputs = [str(mp3_file), str(original_ogg)]
    else:
        # Geräusch vorne UND hinten: original[0:start] + TTS + original[end:]
        filt = (f"[0:a]atrim=0:{start},asetpts=PTS-STARTPTS[n1];"
                f"[0:a]atrim={end},asetpts=PTS-STARTPTS[n2];"
                f"[n1][2:a][n2]concat=n=3:v=0:a=1[out]")
        inputs = [str(original_ogg), str(mp3_file), str(original_ogg)]

    cmd = ["ffmpeg", "-y"]
    for inp in inputs:
        cmd += ["-i", inp]
    cmd += ["-filter_complex", filt, "-map", "[out]",
            "-c:a", "libvorbis", "-ar", OGG_SAMPLERATE, "-ac", OGG_CHANNELS, "-q:a", "4",
            str(ogg_out)]
    subprocess.run(cmd, check=True, capture_output=True)
    return True


# ─── Hauptprogramm ────────────────────────────────────────────────────────────

async def run(gme_path: Path, language: str, voice_override: str | None,
              whisper_model: str, limit: int = 0, skip_assemble: bool = False,
              offline: bool = False, use_patcher: bool = False):
    if not gme_path.exists():
        print(f"Fehler: Datei nicht gefunden: {gme_path}")
        sys.exit(1)

    # GME-Datei umbenennen: Umlaute + Leerzeichen entfernen
    def _sanitize(name: str) -> str:
        for a, b in [("ä","ae"),("ö","oe"),("ü","ue"),("Ä","Ae"),("Ö","Oe"),("Ü","Ue"),("ß","ss")]:
            name = name.replace(a, b)
        return name.replace(" ", "_")

    safe_stem = _sanitize(gme_path.stem)
    if safe_stem != gme_path.stem:
        new_gme_path = gme_path.with_name(safe_stem + gme_path.suffix)
        gme_path.rename(new_gme_path)
        gme_path = new_gme_path
        print(f"  Datei umbenannt → {gme_path.name}")

    cfg        = LANG_CONFIG[language]
    label_lang = cfg["label"]
    voices     = cfg["voices"]

    book = gme_path.stem

    # Pro-Buch und pro-Sprache Unterordner
    transcripts_dir = BASE_DIR / "03_transcripts" / book
    translated_dir  = BASE_DIR / "04_translated"  / book / language
    tts_dir         = BASE_DIR / "05_tts_output"  / book / language

    transcripts_dir.mkdir(parents=True, exist_ok=True)
    translated_dir.mkdir(parents=True, exist_ok=True)
    tts_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*55}")
    print(f"  Tiptoi DE→{label_lang}: {gme_path.name}")
    print(f"  Whisper: {whisper_model}")
    if limit:
        print(f"  Testmodus: nur {limit} Dateien")
    print(f"{'='*55}\n")

    # Schritt 1: GME entpacken
    print("── Schritt 1: GME entpacken ──")
    book_dir  = unpack_gme(gme_path)
    media_dir = book_dir / "media"
    ogg_files = sorted(media_dir.rglob("*.ogg"))
    if limit:
        ogg_files = ogg_files[:limit]
    total = len(ogg_files)
    print(f"  {total} OGG-Dateien werden verarbeitet.\n")

    if not ogg_files:
        print("Keine OGG-Dateien gefunden – abgebrochen.")
        sys.exit(1)

    # Colab-Pause: prüfen ob Transkripte + Übersetzungen bereits vorhanden
    if not offline:
        missing_transcripts  = sum(1 for f in ogg_files if not _find_resume(transcripts_dir, f.stem, ".txt"))
        if missing_transcripts > 0:
            print(f"── Schritt 2+3: Colab-Upload vorbereiten ──")

            # ZIP erstellen (book ist bereits sanitiert)
            upload_dir = COLAB_DIR / book
            upload_dir.mkdir(parents=True, exist_ok=True)
            zip_path = upload_dir / f"{book}_ogg.zip"
            print(f"  Erstelle ZIP: {zip_path.name} ...", flush=True)
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for ogg in ogg_files:
                    zf.write(ogg, ogg.name)
            print(f"  ✓ {len(ogg_files)} OGGs gezippt ({zip_path.stat().st_size // 1024 // 1024} MB)")

            # colab_config.py schreiben
            config_path = upload_dir / "colab_config.py"
            config_path.write_text(
                f'BOOK    = "{book}"\n'
                f'VERSION = "{PIPELINE_VERSION}"\n'
                f'LANG    = "{language}"\n',
                encoding="utf-8",
            )
            print(f"  ✓ Konfig:     {config_path.name}")
            print()
            print(f"  Fehlende Transkripte: {missing_transcripts}/{total}")
            print()
            print(f"  Upload-Ordner: 07_colab_upload/{book}/")
            print(f"  → {zip_path.name}  hochladen nach:  Google Drive / tiptoi /")
            print(f"  → colab_pipeline_v20.ipynb öffnen")
            print(f"  → Strg+F9 – alle Zellen ausführen (Config wird automatisch geladen)")
            print()
            print(f"  Colab liefert: {book}_transcripts.zip → Google Drive / tiptoi /")
            print(f"  ZIP enthält:")
            print(f"    {{stem}}_{PIPELINE_VERSION}.txt      → Transkripte")
            print(f"    {{stem}}_{PIPELINE_VERSION}_ts.json  → Sprach-Timestamps (für Geräusch-Mix)")
            print(f"    speakers.json              → Sprecher-Zuordnung (für TTS-Stimmen)")
            print()
            print(f"  ZIP entpacken nach:")
            print(f"    03_transcripts/{book}/")
            print(f"  (Übersetzung Schritt 4 läuft danach automatisch lokal via Mistral)")
            print()
            print(f"  Danach erneut starten:")
            print(f"    python pipeline.py \"{gme_path}\" --language {language}")
            print()
            print(f"  Für lokalen Offline-Lauf (kein Colab):")
            print(f"    python pipeline.py \"{gme_path}\" --language {language} --offline")
            sys.exit(0)

    # Schritt 2: Pass 1 – Sprecher-Erkennung
    # Colab-Lauf: speakers.json kommt von Pyannote (Colab) → nur laden, kein lokales Clustering
    # Offline-Lauf: lokales Clustering mit resemblyzer
    speakers_file = transcripts_dir / "speakers.json"
    if voice_override:
        voice_map: dict[str, int] = {}
        print(f"── Schritt 2: Stimme manuell: {voice_override} ──\n")
    else:
        existing = load_speakers(speakers_file)
        if existing is not None:
            print(f"── Schritt 2: Sprecher-Profil geladen (speakers.json) ──\n")
            voice_map = existing
        elif offline:
            print(f"── Schritt 2: Sprecher-Analyse lokal ({total} Dateien, resemblyzer) ──")
            voice_map, n_spk, sil = cluster_speakers(ogg_files, num_voices=len(voices))
            save_speakers(voice_map, speakers_file, n_spk, sil)
            print()
        else:
            print(f"── Schritt 2: Kein speakers.json – alle Dateien erhalten Stimme 0 ──\n")
            voice_map = {}

    def voice_for(stem: str) -> str:
        if voice_override:
            return voice_override
        idx = voice_map.get(stem, 0)
        return voices[min(idx, len(voices) - 1)]

    # Schritt 3: Whisper laden + Pass 2 – Transkription aller Dateien
    print(f"── Schritt 3: Whisper-Modell laden ({whisper_model}) ──")
    whisper = WhisperModel(whisper_model, device="cpu", compute_type="int8", cpu_threads=2, num_workers=1)

    print(f"\n── Schritt 3: Pass 2 – Transkription ({total} Dateien) ──")
    pending_translation: list[tuple[str, Path]] = []   # (text, translation_file)

    for i, ogg_file in enumerate(ogg_files, 1):
        key          = ogg_file.stem
        new_transcript_f  = transcripts_dir / f"{key}_{PIPELINE_VERSION}.txt"
        new_translation_f = translated_dir  / f"{key}_{PIPELINE_VERSION}.txt"
        transcript_f  = _find_resume(transcripts_dir, key, ".txt") or new_transcript_f
        translation_f = _find_resume(translated_dir,  key, ".txt") or new_translation_f

        if i % 100 == 0 or i == total:
            print(f"  Whisper: {i}/{total}", flush=True)

        text = transcribe_one(ogg_file, whisper, transcript_f)
        if not text.strip() or _is_noise_transcript(text):
            if _is_noise_transcript(text):
                print(f"  ⚠ Geräusch/Copyright übersprungen: {ogg_file.name} ({text.strip()!r})", flush=True)
            if not translation_f.exists():
                new_translation_f.write_text("", encoding="utf-8")
            continue

        pending_translation.append((text, translation_f))

    # Whisper-Modell aus RAM freigeben bevor Mistral startet
    del whisper
    gc.collect()
    print("  Whisper-Modell aus RAM entladen.", flush=True)

    # Schritt 4: Pass 3 – Batch-Übersetzung (Mistral)
    api_key = os.getenv("MISTRAL_API_KEY")
    if not api_key:
        raise EnvironmentError("MISTRAL_API_KEY fehlt – bitte .env ausfüllen")
    mistral = Mistral(api_key=api_key)

    print(f"\n── Schritt 4: Pass 3 – Batch-Übersetzung (Mistral) ──")
    translate_batch(
        pending_translation, mistral,
        cfg["system_prompt"], cfg["model"], cfg.get("temperature"),
    )

    # Schritt 5: Pass 4 – TTS + OGG pro Datei
    print(f"\n── Schritt 5: Pass 4 – TTS / OGG-Konvertierung ──")

    for i, ogg_file in enumerate(ogg_files, 1):
        key           = ogg_file.stem
        translation_f = _find_resume(translated_dir, key, ".txt") or (translated_dir / f"{key}_{PIPELINE_VERSION}.txt")
        mp3_file      = _find_resume(tts_dir, key, ".mp3")         or (tts_dir / f"{key}_{PIPELINE_VERSION}.mp3")
        ogg_out       = tts_dir / ogg_file.name   # nie in media_dir schreiben → Originals bleiben erhalten
        voice         = voice_for(key)

        if not translation_f.exists():
            continue
        translated = _clean_translation(translation_f.read_text(encoding="utf-8"))
        if not translated:
            continue

        print(f"  [{i}/{total}] {ogg_file.name}  [{voice.split('-')[2]}]", flush=True)
        if not await tts_one(translated, mp3_file, voice):
            continue
        if mp3_file.exists() and mp3_file.stat().st_size == 0:
            print(f"    ⚠ Leere MP3 – lösche und überspringe: {mp3_file.name}", flush=True)
            mp3_file.unlink()
            continue
        if mp3_file.exists():
            try:
                timing = _get_speech_timing(key, transcripts_dir)
                if timing:
                    mixed = mix_with_original(ogg_file, mp3_file, ogg_out, *timing)
                    if mixed:
                        print(f"    ✓ Mix: Geräusch+Stimme ({timing[0]:.1f}s–{timing[1]:.1f}s / {timing[2]:.1f}s)", flush=True)
                    else:
                        convert_to_ogg(mp3_file, ogg_out)
                else:
                    convert_to_ogg(mp3_file, ogg_out)
            except subprocess.CalledProcessError as e:
                print(f"    ⚠ ffmpeg Fehler ({e.returncode}) – überspringe: {ogg_file.name}", flush=True)
                if mp3_file.exists():
                    mp3_file.unlink()

    # Schritt 6: GME neu packen
    if skip_assemble:
        print(f"\n── Schritt 6: GME neu packen – ÜBERSPRUNGEN (--skip-assemble) ──")
        print(f"  OGGs liegen in: {book_dir / 'media'}")
        print(f"  Weiter mit: python gme_patcher/gme_patch.py 01_input/{gme_path.name} {book_dir}/media/ 06_output/...")
    elif use_patcher:
        print(f"\n── Schritt 6: GME neu packen via gme_patch.py [ALPHA] ──")
        sys.path.insert(0, str(BASE_DIR / "gme_patcher"))
        from gme_patch import patch_gme as _patch_gme
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        out_gme = OUTPUT_DIR / f"{book}{cfg['suffix']}_p_{PIPELINE_VERSION}.gme"
        _patch_gme(gme_path, tts_dir, out_gme)
        print(f"\n{'='*55}")
        print(f"  Fertig! Neue GME-Datei (Patcher):")
        print(f"  {out_gme}")
        print(f"{'='*55}\n")
    else:
        print(f"\n── Schritt 6: GME neu packen ──")
        out_gme = repack_gme(book_dir, OUTPUT_DIR, cfg["suffix"], tts_dir=tts_dir)
        print(f"\n{'='*55}")
        print(f"  Fertig! Neue GME-Datei:")
        print(f"  {out_gme}")
        print(f"{'='*55}\n")


def main():
    parser = argparse.ArgumentParser(description="Tiptoi GME DE→FR/CH Übersetzer")
    parser.add_argument("gme", help="Pfad zur GME-Datei (z.B. 01_input/buch.gme)")
    parser.add_argument(
        "-l", "--language",
        default=DEFAULT_LANGUAGE,
        choices=list(LANG_CONFIG.keys()),
        help=f"Zielsprache (Standard: {DEFAULT_LANGUAGE})",
    )
    parser.add_argument(
        "--voice",
        default=None,
        help="edge-tts Stimme (überschreibt Sprachstandard)",
    )
    parser.add_argument(
        "--whisper-model",
        default=DEFAULT_WHISPER,
        choices=["tiny", "base", "small", "medium", "large-v3-turbo"],
        help=f"Whisper-Modell (Standard: {DEFAULT_WHISPER})",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        metavar="N",
        help="Nur die ersten N Audiodateien verarbeiten (0 = alle)",
    )
    parser.add_argument(
        "--skip-assemble",
        action="store_true",
        help="Schritt 6 (tttool assemble) überspringen – OGGs bleiben in 02_unpacked/.../media/ für gme_patch.py",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Alles lokal ausführen (Whisper + Mistral), kein Colab-Pause",
    )
    parser.add_argument(
        "--use-patcher",
        action="store_true",
        help="[ALPHA] Schritt 6: gme_patch.py statt tttool assemble – erhält Spiele (Binary-Patch)",
    )
    args = parser.parse_args()
    asyncio.run(run(Path(args.gme), args.language, args.voice, args.whisper_model, args.limit, args.skip_assemble, args.offline, args.use_patcher))


if __name__ == "__main__":
    main()
