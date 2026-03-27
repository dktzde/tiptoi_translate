#!/usr/bin/env python3
"""
retranslate_oversized.py – Interaktive Nachbesserung zu langer Audio-Dateien
=============================================================================
Wird von gme_patch.py aufgerufen, wenn ein übersetztes OGG mehr als
--max-diff (default 20%) größer ist als das Original.

Optionen im interaktiven Menü:
  [1] Beide Dateien anhören + kürzeren deutschen Text eingeben
      → Mistral → Edge-TTS → neues Audio
  [2] Dauer-Reduktion (ffmpeg -t, Audio wird am Ende abgeschnitten)
  [3] Automatische Kürzung (STT → Mistral kürzt Text → Edge-TTS)
      ← wird nach 3 Minuten automatisch gewählt

Verwendung als Modul:
  from retranslate_oversized import retranslate
  new_ogg = retranslate(orig_bytes, new_bytes, max_bytes, voice, lang)

Verwendung als CLI:
  python retranslate_oversized.py original.ogg new_fr.ogg --max-bytes 12345 \\
         --voice fr-FR-HenriNeural --lang fr

Voraussetzungen:
  pip install mistralai edge-tts emoji python-dotenv
  pip install faster-whisper          (für Option 3: Auto-Kürzung)
  ffmpeg + ffplay + ffprobe im PATH
  MISTRAL_API_KEY in .env oder Umgebungsvariable
"""

import os
import re
import sys
import time
import asyncio
import subprocess
import tempfile
import threading
from pathlib import Path

try:
    import emoji
    from mistralai import Mistral
    import edge_tts
    from dotenv import load_dotenv
    load_dotenv()
    _DEPS_OK = True
except ImportError as e:
    _DEPS_OK = False
    _DEPS_ERR = str(e)
    # Nicht sofort exit → --help soll auch ohne deps funktionieren


# ─── Konfiguration (aus pipeline.py LANG_CONFIG) ─────────────────────────────

LANG_CONFIG = {
    "fr": {
        "voices": [
            "fr-FR-HenriNeural",
            "fr-FR-EloiseNeural",
            "fr-BE-CharlineNeural",
            "fr-FR-RemyMultilingualNeural",
            "fr-FR-VivienneMultilingualNeural",
        ],
        "model": "mistral-medium-latest",
        "temperature": 0.8,
        "stt_lang": "fr",
        "system_prompt": (
            "Tu es un traducteur pour livres enfants. "
            "Traduis le texte allemand suivant en français naturel et adapté aux enfants. "
            "Réponds uniquement avec la traduction, sans explications."
        ),
        "shorten_prompt": (
            "Le texte suivant est trop long pour une piste audio de livre enfant. "
            "Raccourcis-le à environ {max_chars} caractères maximum, "
            "en gardant le sens essentiel et un ton adapté aux enfants. "
            "Réponds uniquement avec le texte raccourci, sans explication."
        ),
    },
    "ch": {
        "voices": [
            "de-CH-JanNeural",
            "de-CH-LeniNeural",
            "de-AT-JonasNeural",
        ],
        "model": "mistral-medium-latest",
        "temperature": 0.3,
        "stt_lang": "de",
        "system_prompt": (
            "Übersetze die folgenden Tiptoi-Sätze in natürliches Schweizerdeutsch "
            "(Berner Dialekt), verwende einfache Wörter für Kinder und schreibe es so, "
            "wie man es spricht (phonetisch für TTS). "
            "Antworte nur mit der Übersetzung, ohne Erklärungen."
        ),
        "shorten_prompt": (
            "Der folgende Text ist zu lang für eine Audio-Spur in einem Kinderbuch. "
            "Kürze ihn auf maximal {max_chars} Zeichen, behalte den wesentlichen "
            "Inhalt und den kindgerechten Ton bei. Schreibe im gleichen Dialekt. "
            "Antworte nur mit dem gekürzten Text, ohne Erklärung."
        ),
    },
}

OGG_CHANNELS = "1"
OGG_SAMPLERATE = "22050"
TIMEOUT_SECONDS = 180  # 3 Minuten, dann automatisch Option 3


# ─── Hilfsfunktionen ─────────────────────────────────────────────────────────

_MD_RE = re.compile(
    r'\*{1,3}|_{1,3}|`{1,3}|~~|^\s*#{1,6}\s*'
    r'|[^\x00-\x7F\u00C0-\u024F\u1E00-\u1EFF]',
    re.MULTILINE,
)


def _clean_translation(text: str) -> str:
    cleaned = emoji.replace_emoji(text, replace='')
    cleaned = _MD_RE.sub('', cleaned)
    cleaned = re.sub(r':[a-z_]+:', '', cleaned)
    cleaned = re.sub(r'\s*[–—]\s*', ', ', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned


def _play_audio(filepath: str, label: str = ""):
    if label:
        print(f"  ▶ {label}")
    try:
        subprocess.run(
            ['ffplay', '-nodisp', '-autoexit', '-loglevel', 'quiet', filepath],
            timeout=120,
        )
    except FileNotFoundError:
        print("  (ffplay nicht installiert – kann nicht abspielen)")
    except subprocess.TimeoutExpired:
        pass


def _input_with_timeout(prompt: str, timeout: int = TIMEOUT_SECONDS) -> str | None:
    result = [None]

    def _read():
        try:
            result[0] = input(prompt)
        except EOFError:
            pass

    t = threading.Thread(target=_read, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        print(f"\n  ⏰ Timeout ({timeout}s) – wähle automatisch Option 3")
        return None
    return result[0]


# ─── Mistral API ─────────────────────────────────────────────────────────────

def _mistral_call(text: str, system_prompt: str, lang: str = "fr") -> str | None:
    api_key = os.getenv("MISTRAL_API_KEY")
    if not api_key:
        print("  ⚠ MISTRAL_API_KEY fehlt")
        return None

    cfg = LANG_CONFIG.get(lang, LANG_CONFIG["fr"])
    client = Mistral(api_key=api_key)
    kwargs = dict(
        model=cfg["model"],
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text},
        ],
    )
    if cfg.get("temperature") is not None:
        kwargs["temperature"] = cfg["temperature"]

    waits = [60, 90, 180]
    for attempt in range(len(waits) + 1):
        try:
            resp = client.chat.complete(**kwargs)
            return resp.choices[0].message.content.strip()
        except Exception as e:
            if ("429" in str(e) or "rate" in str(e).lower()) and attempt < len(waits):
                print(f"    ⚠ Rate Limit #{attempt+1} – warte {waits[attempt]}s", flush=True)
                time.sleep(waits[attempt])
            else:
                print(f"  ⚠ Mistral-Fehler: {e}")
                return None
    return None


def _translate_mistral(text_de: str, lang: str = "fr") -> str | None:
    cfg = LANG_CONFIG.get(lang, LANG_CONFIG["fr"])
    result = _mistral_call(text_de, cfg["system_prompt"], lang)
    return _clean_translation(result) if result else None


def _shorten_mistral(text: str, max_chars: int, lang: str = "fr") -> str | None:
    cfg = LANG_CONFIG.get(lang, LANG_CONFIG["fr"])
    prompt = cfg["shorten_prompt"].format(max_chars=max_chars)
    result = _mistral_call(text, prompt, lang)
    return _clean_translation(result) if result else None


# ─── STT ─────────────────────────────────────────────────────────────────────

def _stt_from_ogg(ogg_bytes: bytes, lang: str = "fr") -> str | None:
    cfg = LANG_CONFIG.get(lang, LANG_CONFIG["fr"])
    stt_lang = cfg.get("stt_lang", "fr")

    try:
        from faster_whisper import WhisperModel
    except ImportError:
        print("    ⚠ faster-whisper nicht installiert – Auto-Kürzung nicht möglich")
        return None

    with tempfile.NamedTemporaryFile(suffix='.ogg', delete=False) as f:
        f.write(ogg_bytes)
        f.flush()
        try:
            model = WhisperModel("base", device="cpu", compute_type="int8",
                                 cpu_threads=2, num_workers=1)
            segments, _ = model.transcribe(f.name, language=stt_lang)
            text = " ".join(s.text for s in segments).strip()
            del model
            return text if text else None
        except Exception as e:
            print(f"    ⚠ STT Fehler: {e}")
            return None
        finally:
            os.unlink(f.name)


# ─── Edge-TTS + ffmpeg ───────────────────────────────────────────────────────

async def _tts_to_mp3(text: str, mp3_path: str, voice: str) -> bool:
    try:
        communicator = edge_tts.Communicate(text, voice=voice)
        await communicator.save(mp3_path)
        return True
    except Exception as e:
        print(f"    ⚠ TTS Fehler: {e}")
        return False


def _mp3_to_ogg(mp3_path: str, ogg_path: str) -> bool:
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", mp3_path, "-c:a", "libvorbis",
             "-ac", OGG_CHANNELS, "-ar", OGG_SAMPLERATE, "-q:a", "4", ogg_path],
            check=True, capture_output=True,
        )
        return True
    except subprocess.CalledProcessError as e:
        print(f"    ⚠ ffmpeg Fehler: {e}")
        return False


def _text_to_ogg_bytes(text: str, voice: str) -> bytes | None:
    with tempfile.TemporaryDirectory() as tmp:
        mp3_path = os.path.join(tmp, "tts.mp3")
        ogg_path = os.path.join(tmp, "tts.ogg")

        try:
            asyncio.get_running_loop()
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                ok = pool.submit(asyncio.run, _tts_to_mp3(text, mp3_path, voice)).result()
            if not ok:
                return None
        except RuntimeError:
            if not asyncio.run(_tts_to_mp3(text, mp3_path, voice)):
                return None

        if not os.path.exists(mp3_path) or os.path.getsize(mp3_path) == 0:
            return None
        if not _mp3_to_ogg(mp3_path, ogg_path):
            return None
        if not os.path.exists(ogg_path) or os.path.getsize(ogg_path) == 0:
            return None
        return Path(ogg_path).read_bytes()


# ─── Sichere OGG-Kürzung ────────────────────────────────────────────────────

def _truncate_ogg_safe(raw: bytes, max_bytes: int) -> bytes:
    with tempfile.TemporaryDirectory() as tmp:
        in_p = os.path.join(tmp, "in.ogg")
        out_p = os.path.join(tmp, "out.ogg")
        Path(in_p).write_bytes(raw)
        try:
            probe = subprocess.run(
                ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", in_p],
                capture_output=True, text=True, timeout=10)
            duration = float(probe.stdout.strip())
        except Exception:
            return raw[:max_bytes]

        for _ in range(5):
            scale = (max_bytes / len(raw)) * 0.92
            target_dur = duration * scale
            if target_dur < 0.1:
                break
            subprocess.run(
                ["ffmpeg", "-y", "-i", in_p, "-t", f"{target_dur:.3f}",
                 "-c:a", "libvorbis", "-ac", "1", "-ar", "22050", "-q:a", "4", out_p],
                capture_output=True, timeout=30)
            result = Path(out_p).read_bytes()
            if len(result) <= max_bytes:
                return result + b'\x00' * (max_bytes - len(result))
            raw = result
            Path(in_p).write_bytes(raw)
            duration = target_dur
        return raw[:max_bytes]


def _compress_with_atempo(raw: bytes, target_len: int) -> bytes | None:
    base_ratio = len(raw) / target_len
    if base_ratio > 2.0:
        return None
    for extra in [0.0, 0.15, 0.3, 0.5]:
        ratio = base_ratio + extra
        if ratio > 2.0:
            break
        with tempfile.TemporaryDirectory() as tmp:
            in_path = os.path.join(tmp, "in.ogg")
            out_path = os.path.join(tmp, "out.ogg")
            Path(in_path).write_bytes(raw)
            try:
                subprocess.run(
                    ["ffmpeg", "-y", "-i", in_path,
                     "-filter:a", f"atempo={ratio:.4f}",
                     "-c:a", "libvorbis", "-ac", OGG_CHANNELS, "-ar", OGG_SAMPLERATE,
                     "-q:a", "4", out_path],
                    capture_output=True, timeout=30)
                result = Path(out_path).read_bytes()
                if len(result) <= target_len:
                    return result + b'\x00' * (target_len - len(result))
            except Exception:
                continue
    return None


# ─── Option 3: Auto-Kürzung (STT → Mistral → TTS) ──────────────────────────

def _auto_shorten(new_ogg_bytes: bytes, max_bytes: int,
                  voice: str, lang: str = "fr") -> bytes | None:
    print(f"  → Option 3: Automatische Kürzung...")

    print(f"    STT (faster-whisper base)...", flush=True)
    text = _stt_from_ogg(new_ogg_bytes, lang)
    if not text:
        print(f"    ⚠ Kein Text erkannt – Fallback: Dauer-Reduktion")
        return None

    print(f"    Erkannter Text: {text[:80]}{'...' if len(text) > 80 else ''}")

    ratio = max_bytes / len(new_ogg_bytes)
    max_chars = max(int(len(text) * ratio * 0.80), 10)
    print(f"    Ziel: ~{max_chars} Zeichen (Original: {len(text)} Zeichen)")

    print(f"    Mistral kürzt Text...", flush=True)
    shortened = _shorten_mistral(text, max_chars, lang)
    if not shortened:
        return None

    print(f"    Gekürzter Text: {shortened[:80]}{'...' if len(shortened) > 80 else ''}")

    print(f"    Edge-TTS ({voice})...", flush=True)
    new_raw = _text_to_ogg_bytes(shortened, voice)
    if not new_raw:
        return None

    if len(new_raw) <= max_bytes:
        print(f"    ✓ {len(new_raw):,} Bytes (passt!)")
        return new_raw + b'\x00' * (max_bytes - len(new_raw))

    compressed = _compress_with_atempo(new_raw, max_bytes)
    if compressed:
        return compressed
    return _truncate_ogg_safe(new_raw, max_bytes)


# ─── Hauptfunktion ───────────────────────────────────────────────────────────

def retranslate(
    orig_ogg_bytes: bytes, new_ogg_bytes: bytes, max_bytes: int,
    voice: str, lang: str = "fr", index: int = -1,
) -> bytes:
    """Interaktive Nachbesserung. Gibt OGG-Bytes mit exakt max_bytes zurück."""
    if not _DEPS_OK:
        print(f"  ⚠ Fehlende Abhängigkeit: {_DEPS_ERR}")
        print(f"    pip install mistralai edge-tts emoji python-dotenv")
        print(f"  → Fallback: Dauer-Reduktion")
        return _truncate_ogg_safe(new_ogg_bytes, max_bytes)

    ratio = len(new_ogg_bytes) / max_bytes
    idx_str = f" idx={index}" if index >= 0 else ""

    print(f"\n{'='*60}")
    print(f"  ⚠ Audio{idx_str}: {ratio:.1f}x zu groß!")
    print(f"    Neu: {len(new_ogg_bytes):,} B  /  Max: {max_bytes:,} B")
    print(f"    Stimme: {voice}")
    print(f"")
    print(f"  [1] Beide anhören + kürzeren Text eingeben")
    print(f"  [2] Dauer-Reduktion (ffmpeg)")
    print(f"  [3] Auto-Kürzung (STT → Mistral kürzt → Edge-TTS)")
    print(f"")
    print(f"  Auto → Option 3 nach {TIMEOUT_SECONDS // 60} Min")
    print(f"{'='*60}")

    choice = _input_with_timeout("  Auswahl [1/2/3]: ")

    # Timeout / ENTER / 3 → Option 3
    if choice is None or choice.strip() in ('', '3'):
        result = _auto_shorten(new_ogg_bytes, max_bytes, voice, lang)
        if result:
            return result
        return _truncate_ogg_safe(new_ogg_bytes, max_bytes)

    elif choice.strip() == '1':
        with tempfile.NamedTemporaryFile(suffix='.ogg', delete=False) as f:
            f.write(orig_ogg_bytes)
            f.flush()
            _play_audio(f.name, "Original (DE):")
            os.unlink(f.name)

        with tempfile.NamedTemporaryFile(suffix='.ogg', delete=False) as f:
            f.write(new_ogg_bytes)
            f.flush()
            _play_audio(f.name, f"Aktuell ({lang.upper()}, zu lang):")
            os.unlink(f.name)

        print()
        new_text_de = _input_with_timeout("  Neuer deutscher Text (kürzer): ")
        if new_text_de and new_text_de.strip():
            translated = _translate_mistral(new_text_de.strip(), lang)
            if translated:
                print(f"  Übersetzung: {translated}")
                new_raw = _text_to_ogg_bytes(translated, voice)
                if new_raw and len(new_raw) <= max_bytes:
                    print(f"  ✓ {len(new_raw):,} Bytes (passt!)")
                    return new_raw + b'\x00' * (max_bytes - len(new_raw))
                elif new_raw:
                    compressed = _compress_with_atempo(new_raw, max_bytes)
                    if compressed:
                        return compressed
                    return _truncate_ogg_safe(new_raw, max_bytes)

        # Fallback → Option 3
        result = _auto_shorten(new_ogg_bytes, max_bytes, voice, lang)
        if result:
            return result
        return _truncate_ogg_safe(new_ogg_bytes, max_bytes)

    elif choice.strip() == '2':
        return _truncate_ogg_safe(new_ogg_bytes, max_bytes)

    else:
        result = _auto_shorten(new_ogg_bytes, max_bytes, voice, lang)
        if result:
            return result
        return _truncate_ogg_safe(new_ogg_bytes, max_bytes)


# ─── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Interaktive Nachbesserung zu langer Tiptoi-Audio-Dateien",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Optionen im interaktiven Menü:\n"
            "  [1] Beide anhören + kürzeren Text eingeben\n"
            "  [2] Dauer-Reduktion (ffmpeg)\n"
            "  [3] Auto-Kürzung: STT → Mistral kürzt → Edge-TTS\n"
            "      (automatisch nach 3 Minuten)"
        ),
    )
    parser.add_argument("original_ogg", help="Original-OGG (DE)")
    parser.add_argument("new_ogg", help="Neue OGG (FR/CH, zu lang)")
    parser.add_argument("--max-bytes", type=int, required=True,
                        help="Max erlaubte Dateigröße in Bytes")
    parser.add_argument("--voice", default="fr-FR-HenriNeural",
                        help="Edge-TTS Stimme (default: %(default)s)")
    parser.add_argument("--lang", default="fr", choices=["fr", "ch"],
                        help="Zielsprache (default: %(default)s)")
    parser.add_argument("-o", "--output",
                        help="Ausgabe-OGG (default: überschreibt new_ogg)")
    args = parser.parse_args()

    if not _DEPS_OK:
        print(f"Fehlende Abhängigkeit: {_DEPS_ERR}")
        print("  pip install mistralai edge-tts emoji python-dotenv")
        sys.exit(1)

    orig_bytes = Path(args.original_ogg).read_bytes()
    new_bytes = Path(args.new_ogg).read_bytes()
    result = retranslate(orig_bytes, new_bytes, args.max_bytes, args.voice, args.lang)

    out_path = args.output or args.new_ogg
    Path(out_path).write_bytes(result)
    print(f"\n  Gespeichert: {out_path} ({len(result):,} Bytes)")
