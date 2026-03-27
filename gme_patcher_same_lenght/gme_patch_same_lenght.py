"""
gme_patch_same_lenght.py v9 – GME Audio-Patcher (Binary-Patch, shift=0)
=========================================================================
Ersetzt Audio in GME direkt im Binary. Jedes Ersatz-Audio wird auf exakt
die Originalgröße gebracht (Padding oder Kompression). shift ist immer 0,
alle Zeiger (Spiele, Binaries) bleiben unverändert.

Längenanpassung pro Datei:
  - Kürzer als Original → Null-Padding
  - Bis --max-diff (default 20%) zu groß → atempo oder Qualitätsreduktion (lautlos)
  - Über --max-diff → interaktives Menü (3 Min Timeout → Auto)
      Option 1: Beide anhören + neuen Text manuell eingeben
      Option 2: Dauer-Reduktion (ffmpeg -t)
      Option 3: DE-Transkript → Mistral kürzt+übersetzt → Edge-TTS

Stimmen pro Datei via --speakers-json (Format: pipeline.py speakers.json).
Protokoll-Datei wird neben der Ausgabe-GME geschrieben (*.log).

Verwendung:
  python gme_patch_same_lenght.py original.gme media_dir/ output.gme
  python gme_patch_same_lenght.py original.gme media_dir/ output.gme \\
         --lang fr --speakers-json 03_transcripts/buch/speakers.json \\
         --transcripts-dir 03_transcripts/buch/
  python gme_patch_same_lenght.py -i original.gme
"""

import asyncio
import json
import os
import re
import struct
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path


# ─── Sprachkonfiguration ─────────────────────────────────────────────────────

LANG_CONFIG: dict[str, dict] = {
    "fr": {
        "voices": [
            "fr-FR-HenriNeural",
            "fr-FR-EloiseNeural",
            "fr-BE-CharlineNeural",
            "fr-FR-RemyMultilingualNeural",
            "fr-FR-VivienneMultilingualNeural",
            "fr-FR-DeniseNeural",
            "fr-BE-GerardNeural",
            "fr-CH-FabriceNeural",
        ],
        "model": "magistral-medium-latest",
        "temperature": 0.8,
        "shorten_prompt": (
            "Tu es un traducteur pour livres enfants. Traduis le texte allemand suivant "
            "en français ET raccourcis-le à environ {target_chars} caractères. "
            "Garde les mots les plus importants, utilise un langage simple pour enfants. "
            "Réponds uniquement avec la traduction, sans explications."
        ),
        "batch_prompt": (
            "Tu es un traducteur pour livres enfants (Tiptoi). "
            "Tu reçois des textes allemands numérotés avec un objectif de caractères entre parenthèses. "
            "Traduis et raccourcis chaque texte EN FRANÇAIS selon l'objectif indiqué. "
            "Utilise un langage simple et naturel pour enfants. "
            "RÉPONDS UNIQUEMENT avec les traductions numérotées, format exact:\n"
            "[1] traduction\n[2] traduction\n"
            "Aucune explication, aucun commentaire."
        ),
    },
    "ch": {
        "voices": [
            "de-CH-JanNeural",
            "de-CH-LeniNeural",
            "de-AT-JonasNeural",
            "de-AT-IngridNeural",
            "de-DE-FlorianMultilingualNeural",
            "de-DE-SeraphinaMultilingualNeural",
            "de-DE-ConradNeural",
            "de-DE-KatjaNeural",
        ],
        "model": "magistral-medium-latest",
        "temperature": 0.3,
        "shorten_prompt": (
            "Übersetze den folgenden deutschen Text ins Schweizerdeutsch (Berner Dialekt) "
            "UND kürze ihn auf ungefähr {target_chars} Zeichen. "
            "Verwende einfache, kindgerechte Wörter. "
            "Antworte nur mit der Übersetzung, ohne Erklärungen."
        ),
        "batch_prompt": (
            "Du bist ein Übersetzer für Kinderbücher (Tiptoi). "
            "Du erhältst nummerierte deutsche Texte mit Zeichenziel-Vorgaben in Klammern. "
            "Übersetze und kürze jeden Text INS SCHWEIZERDEUTSCHE (Berner Dialekt) gemäß dem Zeichenziel. "
            "Verwende einfache, kindgerechte Sprache. "
            "ANTWORTE NUR mit den nummerierten Übersetzungen, exaktes Format:\n"
            "[1] Übersetzung\n[2] Übersetzung\n"
            "Keine Erklärungen, keine Kommentare."
        ),
    },
    "vo": {
        "voices": [
            "de-DE-FlorianMultilingualNeural",
            "de-DE-SeraphinaMultilingualNeural",
            "de-DE-ConradNeural",
            "de-DE-KatjaNeural",
            "de-DE-KillianNeural",
            "de-DE-AmalaNeural",
            "de-CH-JanNeural",
            "de-AT-IngridNeural",
        ],
        "model": "magistral-medium-latest",
        "temperature": 0.3,
        "shorten_prompt": (
            "Übersetze den folgenden deutschen Text ins Vogtländische UND kürze ihn "
            "auf ungefähr {target_chars} Zeichen. Verwende einfache, kindgerechte Sprache. "
            "Antworte NUR mit der Übersetzung, ohne Erklärungen."
        ),
        "batch_prompt": (
            "Du bist ein Übersetzer für Kinderbücher (Tiptoi). "
            "Du erhältst nummerierte deutsche Texte mit Zeichenziel-Vorgaben in Klammern. "
            "Übersetze und kürze jeden Text INS VOGTLÄNDISCHE gemäß dem Zeichenziel. "
            "Verwende einfache, kindgerechte Sprache. "
            "ANTWORTE NUR mit den nummerierten Übersetzungen, exaktes Format:\n"
            "[1] Übersetzung\n[2] Übersetzung\n"
            "Keine Erklärungen, keine Kommentare."
        ),
    },
    "by": {
        "voices": [
            "de-AT-JonasNeural",
            "de-AT-IngridNeural",
            "de-DE-FlorianMultilingualNeural",
            "de-DE-SeraphinaMultilingualNeural",
            "de-CH-JanNeural",
            "de-CH-LeniNeural",
            "de-DE-ConradNeural",
            "de-DE-KatjaNeural",
        ],
        "model": "magistral-medium-latest",
        "temperature": 0.3,
        "shorten_prompt": (
            "Übersetze den folgenden deutschen Text ins Bairische (Oberbairisch) UND kürze "
            "ihn auf ungefähr {target_chars} Zeichen. Verwende einfache, kindgerechte Sprache. "
            "Antworte NUR mit der Übersetzung, ohne Erklärungen."
        ),
        "batch_prompt": (
            "Du bist ein Übersetzer für Kinderbücher (Tiptoi). "
            "Du erhältst nummerierte deutsche Texte mit Zeichenziel-Vorgaben in Klammern. "
            "Übersetze und kürze jeden Text INS BAIRISCHE (Oberbairisch) gemäß dem Zeichenziel. "
            "Verwende einfache, kindgerechte Sprache. "
            "ANTWORTE NUR mit den nummerierten Übersetzungen, exaktes Format:\n"
            "[1] Übersetzung\n[2] Übersetzung\n"
            "Keine Erklärungen, keine Kommentare."
        ),
    },
    "nd": {
        "voices": [
            "de-DE-FlorianMultilingualNeural",
            "de-DE-SeraphinaMultilingualNeural",
            "de-DE-KillianNeural",
            "de-DE-KatjaNeural",
            "de-DE-ConradNeural",
            "de-DE-AmalaNeural",
            "de-AT-JonasNeural",
            "de-CH-LeniNeural",
        ],
        "model": "magistral-medium-latest",
        "temperature": 0.3,
        "shorten_prompt": (
            "Übersetze den folgenden deutschen Text ins Plattdeutsche (Niederdeutsch) UND "
            "kürze ihn auf ungefähr {target_chars} Zeichen. Verwende einfache, kindgerechte Sprache. "
            "Antworte NUR mit der Übersetzung, ohne Erklärungen."
        ),
        "batch_prompt": (
            "Du bist ein Übersetzer für Kinderbücher (Tiptoi). "
            "Du erhältst nummerierte deutsche Texte mit Zeichenziel-Vorgaben in Klammern. "
            "Übersetze und kürze jeden Text INS PLATTDEUTSCHE (Niederdeutsch) gemäß dem Zeichenziel. "
            "Verwende einfache, kindgerechte Sprache. "
            "ANTWORTE NUR mit den nummerierten Übersetzungen, exaktes Format:\n"
            "[1] Übersetzung\n[2] Übersetzung\n"
            "Keine Erklärungen, keine Kommentare."
        ),
    },
}


# ─── Low-level Helpers ────────────────────────────────────────────────────────

def r32(data: bytes, off: int) -> int:
    return struct.unpack_from('<I', data, off)[0]


def w32(buf: bytearray, off: int, val: int) -> None:
    struct.pack_into('<I', buf, off, val)


def find_xor(data: bytes, first_audio_offset: int) -> int:
    for magic in [b'OggS', b'RIFF']:
        x = data[first_audio_offset] ^ magic[0]
        if (data[first_audio_offset + 1] ^ x == magic[1] and
                data[first_audio_offset + 2] ^ x == magic[2] and
                data[first_audio_offset + 3] ^ x == magic[3]):
            return x
    return 0


def xor_codec(audio: bytes, xor: int) -> bytes:
    if xor == 0:
        return audio
    xorff = xor ^ 0xFF
    out = bytearray(len(audio))
    for i, b in enumerate(audio):
        out[i] = b if b in (0, 0xFF, xor, xorff) else b ^ xor
    return bytes(out)


# ─── Audio-Längenanpassung ────────────────────────────────────────────────────

def _shrink_ogg(raw: bytes, max_bytes: int) -> bytes | None:
    """atempo-Kompression (iterativ). Gibt None zurück wenn >2x nötig."""
    base_ratio = len(raw) / max_bytes
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
                     "-c:a", "libvorbis", "-ac", "1", "-ar", "22050",
                     "-q:a", "4", out_path],
                    capture_output=True, timeout=30)
                result = Path(out_path).read_bytes()
                if len(result) <= max_bytes:
                    return result + b'\x00' * (max_bytes - len(result))
            except Exception:
                continue
    return None


def _reencode_lower_quality(raw: bytes, max_bytes: int) -> tuple[bytes | None, bytes | None]:
    """Recodiert OGG mit schrittweise sinkender Qualität (q=3 → -1).

    Gleiche Dauer, kein Inhaltsverlust – nur geringere Bitrate.

    Returns:
        (fitted, min_quality)
        - fitted:      erstes Ergebnis ≤ max_bytes (mit Padding), oder None
        - min_quality: kleinstes erreichtes Ergebnis (q=-1, ohne Padding), oder None
                       Kann größer als max_bytes sein → als Basis für atempo nutzbar.
    """
    fitted = None
    min_quality = None
    with tempfile.TemporaryDirectory() as tmp:
        in_path = os.path.join(tmp, "in.ogg")
        out_path = os.path.join(tmp, "out.ogg")
        Path(in_path).write_bytes(raw)

        # Phase 1: Vorbis-Qualitätsstufen q=3 → -1 (~45 kbps minimum)
        for q in [3, 2, 1, 0, -1]:
            try:
                subprocess.run(
                    ["ffmpeg", "-y", "-i", in_path,
                     "-c:a", "libvorbis", "-ac", "1", "-ar", "22050",
                     "-q:a", str(q), out_path],
                    capture_output=True, timeout=30)
                result = Path(out_path).read_bytes()
                if q == -1:
                    min_quality = result
                if fitted is None and len(result) <= max_bytes:
                    fitted = result + b'\x00' * (max_bytes - len(result))
            except Exception:
                continue

        # Phase 2: Explizite niedrige Bitraten (unter q=-1, bis ~8 kbps)
        # Vorbis bei 8k: ~5× kleiner als q=-1, Sprachverständlichkeit bleibt gut
        for bitrate in ["24k", "16k", "12k", "8k"]:
            try:
                subprocess.run(
                    ["ffmpeg", "-y", "-i", in_path,
                     "-c:a", "libvorbis", "-ac", "1", "-ar", "22050",
                     "-b:a", bitrate, out_path],
                    capture_output=True, timeout=30)
                result = Path(out_path).read_bytes()
                min_quality = result  # letzte Stufe ist kleinste
                if fitted is None and len(result) <= max_bytes:
                    fitted = result + b'\x00' * (max_bytes - len(result))
            except Exception:
                continue

    return fitted, min_quality


def _truncate_ogg_inline(raw: bytes, max_bytes: int) -> bytes:
    """Dauer-Reduktion via ffmpeg -t. Fallback wenn Retranslation nicht möglich."""
    with tempfile.TemporaryDirectory() as tmp:
        in_p = os.path.join(tmp, "in.ogg")
        out_p = os.path.join(tmp, "out.ogg")
        Path(in_p).write_bytes(raw)
        try:
            probe = subprocess.run(
                ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", in_p],
                capture_output=True, text=True, timeout=10)
            dur = float(probe.stdout.strip())
            target_dur = dur * (max_bytes / len(raw)) * 0.90
            subprocess.run(
                ["ffmpeg", "-y", "-i", in_p, "-t", f"{target_dur:.3f}",
                 "-c:a", "libvorbis", "-ac", "1", "-ar", "22050",
                 "-q:a", "4", out_p],
                capture_output=True, timeout=30)
            result = Path(out_p).read_bytes()
            if len(result) <= max_bytes:
                return result + b'\x00' * (max_bytes - len(result))
        except Exception as e:
            print(f"    ⚠ ffmpeg Fallback fehlgeschlagen: {e}")
    return raw[:max_bytes]


# ─── Transkript-Suche ─────────────────────────────────────────────────────────

def _find_transcript(stem: str, transcripts_dir: Path) -> str | None:
    """Sucht DE-Transkript für einen OGG-Stem. Gibt Text zurück oder None."""
    # Stem kann sein: Buch_44 oder Buch_44_v32
    base = re.sub(r'_v\d+$', '', stem)
    # Erst versioniertes, dann ohne Version
    candidates = sorted(transcripts_dir.glob(f"{base}_v*.txt"))
    if not candidates:
        candidates = list(transcripts_dir.glob(f"{base}.txt"))
    if candidates:
        return candidates[-1].read_text(encoding="utf-8").strip()
    return None


# ─── Mistral Response Parsing ────────────────────────────────────────────────

def _extract_text(content) -> str:
    """Extrahiert Text aus Mistral-Antwort.
    magistral-medium-latest (Reasoning) gibt content als Liste von Blöcken zurück,
    Standard-Modelle als String.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            btype = getattr(block, "type", None) or (block.get("type") if isinstance(block, dict) else None)
            if btype == "thinking":
                continue
            text = getattr(block, "text", None) or (block.get("text", "") if isinstance(block, dict) else "")
            if text:
                parts.append(text)
        return "".join(parts)
    return str(content)


# ─── Mistral Kürzen+Übersetzen ────────────────────────────────────────────────

def _shorten_translate_mistral(de_text: str, target_chars: int,
                                lang: str) -> str | None:
    """Ruft Mistral auf: deutschen Text kürzen + in Zielsprache übersetzen."""
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    api_key = os.environ.get("MISTRAL_API_KEY")
    if not api_key:
        return None

    try:
        from mistralai import Mistral
        cfg = LANG_CONFIG.get(lang, LANG_CONFIG["fr"])
        prompt_tpl = cfg["shorten_prompt"]
        system_msg = prompt_tpl.format(target_chars=target_chars)

        client = Mistral(api_key=api_key)
        kwargs = dict(
            model=cfg["model"],
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user",   "content": de_text},
            ],
            temperature=cfg.get("temperature", 0.5),
            max_tokens=256,
        )
        waits = [60, 90, 180]
        for attempt in range(len(waits) + 1):
            try:
                resp = client.chat.complete(**kwargs)
                time.sleep(0.5)  # Rate-Limit schonen
                return _extract_text(resp.choices[0].message.content).strip()
            except Exception as e:
                if ("429" in str(e) or "rate" in str(e).lower()) and attempt < len(waits):
                    print(f"    ⚠ Rate Limit – warte {waits[attempt]}s...", flush=True)
                    time.sleep(waits[attempt])
                else:
                    print(f"    ⚠ Mistral Fehler: {e}")
                    return None
        return None
    except Exception as e:
        print(f"    ⚠ Mistral Fehler: {e}")
        return None


# ─── Edge-TTS ─────────────────────────────────────────────────────────────────

def _tts_to_ogg(text: str, voice: str, max_bytes: int) -> bytes | None:
    """Erzeugt OGG via Edge-TTS + ffmpeg. Gibt None zurück bei Fehler."""
    try:
        import edge_tts

        async def _run() -> bytes:
            with tempfile.TemporaryDirectory() as tmp:
                mp3_path = os.path.join(tmp, "tts.mp3")
                ogg_path = os.path.join(tmp, "tts.ogg")
                comm = edge_tts.Communicate(text, voice)
                await comm.save(mp3_path)
                subprocess.run(
                    ["ffmpeg", "-y", "-i", mp3_path,
                     "-c:a", "libvorbis", "-ac", "1", "-ar", "22050",
                     "-q:a", "4", ogg_path],
                    capture_output=True, timeout=30)
                return Path(ogg_path).read_bytes()

        # asyncio.run() schlägt fehl wenn bereits eine Event Loop läuft (z.B. pipeline.py).
        # In diesem Fall: ThreadPoolExecutor → neuer Thread mit eigener Event Loop.
        try:
            asyncio.get_running_loop()
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                raw = pool.submit(asyncio.run, _run()).result()
        except RuntimeError:
            raw = asyncio.run(_run())

        if len(raw) <= max_bytes:
            return raw + b'\x00' * (max_bytes - len(raw))
        return raw  # caller handles oversized
    except Exception as e:
        print(f"    ⚠ Edge-TTS Fehler: {e}")
        return None


# ─── Option 3: Roundtrip ──────────────────────────────────────────────────────

def _retranslate(de_text: str, new_len: int, max_bytes: int,
                 voice: str, lang: str) -> bytes | None:
    """DE-Text → Mistral kürzt+übersetzt → Edge-TTS → OGG.

    target_chars = grob geschätzter Zielwert basierend auf Größenverhältnis.
    Gibt None zurück wenn Mistral oder TTS nicht verfügbar.
    """
    target_chars = max(10, int(len(de_text) * (max_bytes / new_len) * 0.85))
    print(f"    Ziel: ~{target_chars} Zeichen (DE-Text: {len(de_text)} Zeichen)")

    print(f"    Mistral kürzt+übersetzt ({lang.upper()})...")
    short_text = _shorten_translate_mistral(de_text, target_chars, lang)
    if not short_text:
        return None
    print(f"    Ergebnis: \"{short_text[:60]}{'...' if len(short_text) > 60 else ''}\"")

    print(f"    Edge-TTS ({voice})...")
    result = _tts_to_ogg(short_text, voice, max_bytes)
    return result


# ─── Batch-Retranslation ─────────────────────────────────────────────────────

def _batch_retranslate_mistral(
    entries: list[dict],
    lang: str,
    batch_size: int = 20,
    max_chars_per_batch: int = 1000,
) -> dict[int, str | None]:
    """Batch-Übersetzung via Mistral: max 20 Einträge ODER 1000 Zeichen pro Aufruf.

    entries: [{'idx': int, 'de_text': str, 'orig_len': int, 'new_len': int}, ...]
    Returns: {idx: fr_text | None}
    """
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    api_key = os.environ.get("MISTRAL_API_KEY")
    if not api_key:
        print("  ⚠ Kein MISTRAL_API_KEY – Batch-Retranslation übersprungen")
        return {}

    cfg = LANG_CONFIG.get(lang, LANG_CONFIG["fr"])
    system_msg = cfg.get("batch_prompt", cfg["shorten_prompt"].replace(" {target_chars} Zeichen", ""))

    results: dict[int, str | None] = {}

    # Batches bilden: max batch_size Einträge ODER max_chars_per_batch Zeichen
    batches: list[list[dict]] = []
    cur: list[dict] = []
    cur_chars = 0
    for entry in entries:
        if not entry.get("de_text"):
            results[entry["idx"]] = None
            continue
        tlen = len(entry["de_text"])
        if cur and (len(cur) >= batch_size or cur_chars + tlen > max_chars_per_batch):
            batches.append(cur)
            cur, cur_chars = [], 0
        cur.append(entry)
        cur_chars += tlen
    if cur:
        batches.append(cur)

    if not batches:
        return results

    try:
        from mistralai import Mistral
        client = Mistral(api_key=api_key)
    except Exception as e:
        print(f"  ⚠ Mistral Import-Fehler: {e}")
        return results

    for batch_num, batch in enumerate(batches, 1):
        total_chars = sum(len(e["de_text"]) for e in batch)
        print(f"\n  ═══ Batch {batch_num}/{len(batches)}: {len(batch)} Einträge, ~{total_chars} Zeichen ═══",
              flush=True)

        # User-Nachricht mit nummerierten Einträgen + Zeichenziel
        lines = []
        for n, entry in enumerate(batch, 1):
            target_pct = min(0.90, max(0.65, (entry["orig_len"] / entry["new_len"]) * 4.0))
            target_chars = max(10, int(len(entry["de_text"]) * target_pct))
            lines.append(f"[{n}] (Ziel: ~{target_chars} Zeichen) {entry['de_text']}")
        user_msg = "\n".join(lines)

        print(f"\n--- Mistral System ---\n{system_msg}")
        print(f"\n--- Mistral User ---\n{user_msg}", flush=True)

        kwargs = dict(
            model=cfg["model"],
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user",   "content": user_msg},
            ],
            temperature=cfg.get("temperature", 0.5),
            max_tokens=min(1024, total_chars * 3),
        )

        response_text = None
        waits = [60, 90, 180]
        for attempt in range(len(waits) + 1):
            try:
                resp = client.chat.complete(**kwargs)
                time.sleep(0.5)
                response_text = _extract_text(resp.choices[0].message.content).strip()
                break
            except Exception as e:
                if ("429" in str(e) or "rate" in str(e).lower()) and attempt < len(waits):
                    print(f"  ⚠ Rate Limit – warte {waits[attempt]}s...", flush=True)
                    time.sleep(waits[attempt])
                else:
                    print(f"  ⚠ Mistral Fehler (Batch {batch_num}): {e}")
                    break

        if response_text:
            print(f"\n--- Mistral Response ---\n{response_text}", flush=True)
            for line in response_text.split("\n"):
                m = re.match(r'^\[(\d+)\]\s*(.+)$', line.strip())
                if m:
                    n = int(m.group(1))
                    text = m.group(2).strip()
                    if 1 <= n <= len(batch):
                        results[batch[n - 1]["idx"]] = text
        else:
            print(f"  ⚠ Batch {batch_num}: kein Ergebnis")
            for entry in batch:
                results[entry["idx"]] = None

    return results


# ─── Interaktives Menü ────────────────────────────────────────────────────────

def _interactive_menu(idx: int, raw: bytes, orig_audio: bytes, max_bytes: int,
                      voice: str, lang: str,
                      de_text: str | None,
                      log_entries: list[dict]) -> tuple[bytes, str]:
    """Zeigt Menü für zu große Audio-Dateien. Gibt (raw, method) zurück."""
    import signal

    ratio = len(raw) / max_bytes
    print(f"\n{'='*60}")
    print(f"  ⚠ Audio idx={idx}: {ratio:.1f}x zu groß!")
    print(f"    Neu: {len(raw):,} B  /  Max: {max_bytes:,} B")
    print(f"    Stimme: {voice}")
    if de_text:
        print(f"    DE-Text: \"{de_text[:80]}{'...' if len(de_text) > 80 else ''}\"")
    print()
    print(f"  [1] Text manuell eingeben + Edge-TTS")
    print(f"  [2] Dauer-Reduktion (ffmpeg)")
    if de_text:
        print(f"  [3] Auto-Kürzung (DE-Text → Mistral → Edge-TTS)")
    print()
    print(f"  Auto → Option {'3' if de_text else '2'} nach 3 Min")
    print(f"{'='*60}")

    chosen: list[str] = []

    def _timeout_handler(signum, frame):
        print(f"\n  → Timeout: Option {'3' if de_text else '2'} automatisch")
        chosen.append('auto')
        raise TimeoutError

    signal.signal(signal.SIGALRM, _timeout_handler)
    signal.alarm(180)

    try:
        choice = input("  Auswahl [1/2/3]: ").strip()
        signal.alarm(0)
    except (TimeoutError, EOFError):
        signal.alarm(0)
        choice = '3' if de_text else '2'

    if choice == '1':
        signal.alarm(0)
        new_text = input("  Neuer Text: ").strip()
        if new_text:
            result = _tts_to_ogg(new_text, voice, max_bytes)
            if result and len(result) <= max_bytes:
                print(f"    ✓ Manuell → {len(result):,} B")
                return result, "manual"
        print(f"    → Fallback: Dauer-Reduktion")
        result = _truncate_ogg_inline(raw, max_bytes)
        return result, "truncated"

    elif choice == '3' and de_text:
        print(f"  → Option 3: DE-Text → Mistral → Edge-TTS...")
        result = _retranslate(de_text, len(raw), max_bytes, voice, lang)
        if result and len(result) <= max_bytes:
            print(f"    ✓ Retranslated → {len(result):,} B")
            return result, "retranslated"
        elif result:
            # Ergebnis noch zu groß → atempo
            shrunk = _shrink_ogg(result, max_bytes)
            if shrunk:
                print(f"    ✓ Retranslated + atempo → {len(shrunk):,} B")
                return shrunk, "retranslated+atempo"
            result = _truncate_ogg_inline(result, max_bytes)
            return result, "retranslated+truncated"
        print(f"    ⚠ Retranslation fehlgeschlagen → Dauer-Reduktion")
        result = _truncate_ogg_inline(raw, max_bytes)
        return result, "truncated"

    else:
        print(f"  → Option 2: Dauer-Reduktion...")
        result = _truncate_ogg_inline(raw, max_bytes)
        return result, "truncated"


# ─── Stimmen-Zuordnung ────────────────────────────────────────────────────────

def load_speakers_json(path: Path) -> dict[str, int]:
    """Lädt speakers.json → voice_map {stem: speaker_idx}."""
    data = json.loads(path.read_text(encoding="utf-8"))
    vm = data.get("voice_map", {})
    n = data.get("num_speakers", "?")
    sil = data.get("silhouette", 0)
    print(f"Sprecher-Profil: {n} Sprecher (Silhouette {sil:.4f}) – {len(vm)} Dateien")
    return {k: int(v) for k, v in vm.items()}


def get_voice(stem: str, voice_map: dict[str, int],
              voices: list[str], default_voice: str) -> str:
    """Bestimmt Edge-TTS Stimme für einen Datei-Stem."""
    clean = re.sub(r'_v\d+$', '', stem)
    if clean in voice_map:
        idx = voice_map[clean]
        return voices[min(idx, len(voices) - 1)]
    return default_voice


# ─── GME-Format Parsing ──────────────────────────────────────────────────────

def parse_media_table(data: bytes) -> tuple[int, int, list[tuple[int, int]]]:
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
    index_map: dict[int, Path] = {}
    pattern = re.compile(r'_(\d+)(?:_v\d+)?\.ogg$', re.IGNORECASE)
    fallback = re.compile(r'^(\d+)(?:_v\d+)?\.ogg$', re.IGNORECASE)
    for f in sorted(media_dir.glob('*.ogg')):
        m = pattern.search(f.name) or fallback.match(f.name)
        if m:
            idx = int(m.group(1))
            if idx not in index_map:
                index_map[idx] = f
    return index_map


# ─── Hauptfunktion ───────────────────────────────────────────────────────────

def patch_gme(original_gme: Path, media_dir: Path, output_gme: Path,
              voice: str = "fr-FR-HenriNeural", lang: str = "fr",
              max_diff: float = 0.20,
              speakers_json: Path | None = None,
              transcripts_dir: Path | None = None) -> None:
    """Ersetzt Audio in GME. shift=0 garantiert.

    Args:
        max_diff:        Schwelle für interaktives Menü (default 0.20 = 20%).
                         float('inf') = niemals interaktiv (Pipeline-Modus).
        speakers_json:   Pfad zu speakers.json für Stimmen-Zuordnung pro Datei.
        transcripts_dir: Pfad zu 03_transcripts/{buch}/ für Option 3 Retranslation.
                         Wenn None, ist Option 3 nicht verfügbar.
    """
    data = original_gme.read_bytes()
    print(f"Eingabe:     {original_gme} ({len(data):,} Bytes)")

    table_offset, xor, entries = parse_media_table(data)
    first_audio_offset = entries[0][0]
    print(f"Audio-Tab:   0x{table_offset:08X} | {len(entries)} Einträge | XOR=0x{xor:02X}")

    last_audio_end = max(off + length for off, length in entries if off > 0 and length > 0)
    orig_file_size = len(data)

    post_audio = data[last_audio_end:orig_file_size - 4]
    if post_audio:
        print(f"Post-Audio:  {len(post_audio):,} Bytes (shift=0, unverändert)")

    cfg = LANG_CONFIG.get(lang, LANG_CONFIG["fr"])
    voices = cfg["voices"]
    voice_map: dict[str, int] = {}
    if speakers_json and speakers_json.exists():
        voice_map = load_speakers_json(speakers_json)
    elif speakers_json:
        print(f"⚠ speakers.json nicht gefunden: {speakers_json}")

    if transcripts_dir and transcripts_dir.exists():
        print(f"Transkripte: {transcripts_dir}")
    elif transcripts_dir:
        print(f"⚠ Transkript-Ordner nicht gefunden: {transcripts_dir}")
        transcripts_dir = None

    diff_display = f"{max_diff:.0%}" if max_diff < float('inf') else "nie"
    mode_hint = "Pipeline: Retranslation → Truncate" if max_diff == float('inf') else "darüber → interaktives Menü"
    print(f"Max-Diff:    {diff_display} ({mode_hint})")

    offset_to_canonical: dict[int, int] = {}
    for i, (off, _) in enumerate(entries):
        if off not in offset_to_canonical:
            offset_to_canonical[off] = i

    file_index = build_file_index(media_dir)
    replaced = 0
    kept = 0
    resized = 0
    log_entries: list[dict] = []
    pending_retranslate: list[dict] = []  # Einträge für Batch-Retranslation

    canonical_audio: dict[int, bytes] = {}

    for i, (orig_off, orig_len) in enumerate(entries):
        canonical = offset_to_canonical[orig_off]
        if canonical in canonical_audio:
            continue

        if i in file_index:
            raw = file_index[i].read_bytes()
            file_stem = file_index[i].stem
            file_voice = get_voice(file_stem, voice_map, voices, voice)
            method = "ok"

            if len(raw) > orig_len:
                over = len(raw) - orig_len
                over_pct = over / orig_len
                print(f"  idx={i}: {over:+,} B ({over_pct:.0%}) [{file_voice.split('-')[2]}]",
                      flush=True)

                # Schritt 1: Qualitätsreduktion (gleiche Dauer, kein Speedup)
                quality_fitted, quality_min = _reencode_lower_quality(raw, orig_len)
                if quality_fitted:
                    raw = quality_fitted
                    method = "quality"
                    print(f"    ✓ quality → {len(raw):,} B", flush=True)
                else:
                    # Schritt 2: atempo – auf minimaler Qualitätsbasis wenn möglich
                    # (kleinere Eingabe → atempo bewältigt auch >2x-Fälle)
                    atempo_input = (quality_min
                                    if quality_min and len(quality_min) < len(raw)
                                    else raw)
                    shrunk = _shrink_ogg(atempo_input, orig_len)
                    if shrunk:
                        raw = shrunk
                        method = "quality+atempo" if atempo_input is quality_min else "atempo"
                        print(f"    ✓ {method} → {len(raw):,} B", flush=True)

                if method not in ("atempo", "quality", "quality+atempo"):
                    # quality, quality+atempo und atempo haben alle nicht geholfen
                    if max_diff == float('inf'):
                        # Pipeline-Modus: für Batch-Retranslation vormerken
                        de_text = None
                        if transcripts_dir:
                            de_text = _find_transcript(file_stem, transcripts_dir)

                        if de_text:
                            log_idx = len(log_entries)  # Index des noch anzuhängenden Eintrags
                            pending_retranslate.append({
                                "idx": i, "canonical": canonical,
                                "de_text": de_text, "orig_len": orig_len,
                                "voice": file_voice, "new_len": len(raw),
                                "log_idx": log_idx,
                            })
                            print(f"    → vorgemerkt für Batch (#{len(pending_retranslate)})", flush=True)
                        else:
                            print(f"    → kein Transkript → Dauer-Reduktion", flush=True)
                        raw = _truncate_ogg_inline(raw, orig_len)
                        method = "truncated"  # Platzhalter, wird nach Batch ggf. ersetzt
                    elif over_pct > max_diff:
                        # Über Schwelle → interaktives Menü
                        de_text = None
                        if transcripts_dir:
                            de_text = _find_transcript(file_stem, transcripts_dir)

                        orig_audio_bytes = xor_codec(data[orig_off:orig_off + orig_len], xor)
                        raw, method = _interactive_menu(
                            idx=i, raw=raw, orig_audio=orig_audio_bytes,
                            max_bytes=orig_len, voice=file_voice, lang=lang,
                            de_text=de_text, log_entries=log_entries,
                        )
                    else:
                        # Unter Schwelle → ffmpeg Kürzung
                        print(f"    → Dauer-Reduktion (unter {diff_display})", flush=True)
                        raw = _truncate_ogg_inline(raw, orig_len)
                        method = "truncated"

                resized += 1

            if len(raw) < orig_len:
                raw = raw + b'\x00' * (orig_len - len(raw))
            if len(raw) > orig_len:
                raw = raw[:orig_len]

            canonical_audio[canonical] = raw
            replaced += 1
            log_entries.append({
                "idx": i, "stem": file_stem, "voice": file_voice,
                "orig_bytes": orig_len, "new_bytes": len(raw), "method": method,
            })
        else:
            enc = data[orig_off:orig_off + orig_len]
            canonical_audio[canonical] = xor_codec(enc, xor)
            kept += 1
            log_entries.append({
                "idx": i, "stem": f"entry_{i}", "voice": "-",
                "orig_bytes": orig_len, "new_bytes": orig_len, "method": "kept",
            })

    print(f"Ersetzt: {replaced} | Behalten: {kept} | Größenanpassung: {resized}")

    # ── Batch-Retranslation (Pipeline-Modus) ──────────────────────────────────
    if pending_retranslate:
        print(f"\n  Batch-Retranslation: {len(pending_retranslate)} Einträge...", flush=True)
        translations = _batch_retranslate_mistral(pending_retranslate, lang)

        retranslated_ok = 0
        for item in pending_retranslate:
            fr_text = translations.get(item["idx"])
            if not fr_text:
                log_entries[item["log_idx"]]["mistral_response"] = None
                continue

            log_entries[item["log_idx"]]["mistral_response"] = fr_text
            print(f"\n  idx={item['idx']}: TTS \"{fr_text[:50]}{'...' if len(fr_text) > 50 else ''}\"",
                  flush=True)
            new_raw = _tts_to_ogg(fr_text, item["voice"], item["orig_len"])
            if not new_raw:
                print(f"  ⚠ TTS fehlgeschlagen → bleibt truncated")
                continue

            # quality → quality+atempo → truncated
            quality_fitted, quality_min = _reencode_lower_quality(new_raw, item["orig_len"])
            if quality_fitted:
                new_bytes = quality_fitted
                new_method = "retranslated+quality"
            else:
                atempo_input = (quality_min if quality_min and len(quality_min) < len(new_raw)
                                else new_raw)
                shrunk = _shrink_ogg(atempo_input, item["orig_len"])
                if shrunk:
                    new_bytes = shrunk
                    new_method = "retranslated+quality+atempo"
                else:
                    new_bytes = _truncate_ogg_inline(new_raw, item["orig_len"])
                    new_method = "retranslated+truncated"

            if len(new_bytes) < item["orig_len"]:
                new_bytes = new_bytes + b'\x00' * (item["orig_len"] - len(new_bytes))
            if len(new_bytes) > item["orig_len"]:
                new_bytes = new_bytes[:item["orig_len"]]

            canonical_audio[item["canonical"]] = new_bytes
            log_entries[item["log_idx"]]["method"] = new_method
            retranslated_ok += 1
            print(f"  ✓ {new_method} → {len(new_bytes):,} B", flush=True)

        print(f"\n  Batch fertig: {retranslated_ok}/{len(pending_retranslate)} erfolgreich", flush=True)

    # ── Neue GME zusammenbauen ──
    result = bytearray(data[:first_audio_offset])

    new_offset_map: dict[int, int] = {}
    for i, (orig_off, _) in enumerate(entries):
        canonical = offset_to_canonical[orig_off]
        if canonical not in new_offset_map:
            new_offset_map[canonical] = len(result)
            result.extend(xor_codec(canonical_audio[canonical], xor))

    new_audio_end = len(result)
    shift = new_audio_end - last_audio_end

    if shift != 0:
        print(f"WARNUNG: shift={shift:+,} B (erwartet: 0)")

    if post_audio:
        result.extend(post_audio)

    # Audio-Tabellen aktualisieren
    for i, (orig_off, _) in enumerate(entries):
        canonical = offset_to_canonical[orig_off]
        new_off = new_offset_map[canonical]
        new_len = len(canonical_audio[canonical])
        pos = table_offset + i * 8
        w32(result, pos, new_off)
        w32(result, pos + 4, new_len)

    add_table_off = r32(bytes(result), 0x0060)
    if 0 < add_table_off < first_audio_offset and add_table_off != table_offset:
        add_first_val = r32(bytes(result), add_table_off)
        if add_first_val == first_audio_offset:
            add_count = (add_first_val - add_table_off) // 8
            if add_count == len(entries):
                for i, (orig_off, _) in enumerate(entries):
                    canonical = offset_to_canonical[orig_off]
                    pos = add_table_off + i * 8
                    w32(result, pos, new_offset_map[canonical])
                    w32(result, pos + 4, len(canonical_audio[canonical]))
                print(f"Zusatz-Tabelle: 0x{add_table_off:08X} aktualisiert")

    if post_audio and shift != 0:
        ptr_lo, ptr_hi = last_audio_end, orig_file_size - 4
        updated = 0
        for rs, re_ in [(0, first_audio_offset), (new_audio_end, len(result))]:
            for off in range(rs, re_ - 3, 4):
                val = r32(bytes(result), off)
                if ptr_lo <= val <= ptr_hi:
                    w32(result, off, val + shift)
                    updated += 1
        print(f"Zeiger verschoben: {updated} (shift={shift:+,} B)")

    checksum = sum(result) & 0xFFFFFFFF
    result.extend(struct.pack('<I', checksum))

    orig_audio = last_audio_end - first_audio_offset
    new_audio = new_audio_end - first_audio_offset
    print(f"Audio:   {orig_audio:,} → {new_audio:,} B ({new_audio - orig_audio:+,})")
    print(f"Gesamt:  {len(data):,} → {len(result):,} B")
    if shift == 0:
        print(f"shift=0 ✓ (Spieldaten unverändert)")

    output_gme.write_bytes(bytes(result))
    print(f"Ausgabe: {output_gme}")

    # ── Log schreiben ──
    _write_log(output_gme, original_gme, lang, voice, log_entries,
               replaced, kept, resized, shift)


# ─── Log-Datei ────────────────────────────────────────────────────────────────

def _write_log(output_gme: Path, input_gme: Path, lang: str, default_voice: str,
               entries: list[dict], replaced: int, kept: int, resized: int,
               shift: int) -> None:
    log_path = output_gme.with_suffix(".log")
    lines = [
        f"gme_patch_same_lenght.py – Log",
        f"Datum:    {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"Eingabe:  {input_gme.name}",
        f"Ausgabe:  {output_gme.name}",
        f"Sprache:  {lang.upper()}  Stimme (Standard): {default_voice}",
        f"Ersetzt:  {replaced}  Behalten: {kept}  Größenanpassung: {resized}",
        f"shift:    {shift:+,} B {'(OK)' if shift == 0 else '(WARNUNG)'}",
        "",
        f"{'idx':>5}  {'Methode':<22}  {'Orig':>8}  {'Neu':>8}  {'Stimme':<35}  Stem",
        "-" * 110,
    ]
    method_counts: dict[str, int] = {}
    for e in entries:
        if e["method"] == "kept":
            continue
        method_counts[e["method"]] = method_counts.get(e["method"], 0) + 1
        lines.append(
            f"{e['idx']:>5}  {e['method']:<22}  {e['orig_bytes']:>8,}  "
            f"{e['new_bytes']:>8,}  {e['voice']:<35}  {e['stem']}"
        )
        if e.get("mistral_response"):
            lines.append(f"       → Mistral: \"{e['mistral_response'][:100]}\"")
        elif "mistral_response" in e and e["mistral_response"] is None:
            lines.append(f"       → Mistral: (fehlgeschlagen)")
    lines += [
        "",
        "Methoden-Zusammenfassung:",
    ]
    for method, count in sorted(method_counts.items()):
        lines.append(f"  {method:<22} {count:>4}×")

    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Log:     {log_path}")


# ─── Info-Modus ──────────────────────────────────────────────────────────────

def info_gme(gme_path: Path) -> None:
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

    unique = len({off for off, _ in entries})
    if unique < len(entries):
        print(f"Duplikate:      {len(entries) - unique}")

    stored_cs = r32(data, len(data) - 4)
    calc_cs = sum(data[:-4]) & 0xFFFFFFFF
    cs_ok = "OK" if stored_cs == calc_cs else f"FEHLER (erwartet 0x{calc_cs:08X})"
    print(f"Prüfsumme:      0x{calc_cs:08X} [{cs_ok}]")


# ─── CLI ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    if len(sys.argv) >= 2 and sys.argv[1] in ('-i', '--info'):
        if len(sys.argv) < 3:
            print("Verwendung: python gme_patch_same_lenght.py -i <datei.gme>")
            sys.exit(1)
        info_gme(Path(sys.argv[2]))
        sys.exit(0)

    parser = argparse.ArgumentParser(
        description="GME Audio-Patcher v9 – Binary-Patch, shift=0",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Beispiele:\n"
            "  python gme_patch_same_lenght.py Buch.gme media/ Buch_fr.gme\n"
            "  python gme_patch_same_lenght.py Buch.gme media/ Buch_fr.gme \\\n"
            "         --lang fr --speakers-json 03_transcripts/Buch/speakers.json \\\n"
            "         --transcripts-dir 03_transcripts/Buch/\n"
            "\n"
            "Audio-Anpassung:\n"
            "  Kürzer als Original    → Null-Padding\n"
            "  Bis --max-diff zu groß → atempo (kein Input)\n"
            "  Über --max-diff        → Menü: [1] manuell [2] ffmpeg [3] Mistral\n"
            "                          (3 Min Timeout → automatisch)\n"
            "\n"
            "Sprachen: fr ch vo by nd\n"
            "Stimmen:  aus --speakers-json, sonst --voice als Standard"
        ),
    )
    parser.add_argument("original_gme", type=Path)
    parser.add_argument("media_dir", type=Path)
    parser.add_argument("output_gme", type=Path)
    parser.add_argument(
        "--voice", default="fr-FR-HenriNeural",
        help="Standard-Stimme (Fallback ohne speakers.json, default: %(default)s)",
    )
    parser.add_argument(
        "--lang", default="fr", choices=list(LANG_CONFIG.keys()),
        help="Zielsprache (default: %(default)s)",
    )
    parser.add_argument(
        "--max-diff", type=float, default=0.20, metavar="RATIO",
        help="Schwelle für interaktives Menü (default: %(default)s = 20%%)",
    )
    parser.add_argument(
        "--speakers-json", type=Path, default=None, metavar="PATH",
        help="speakers.json für Stimmen-Zuordnung pro Datei",
    )
    parser.add_argument(
        "--transcripts-dir", type=Path, default=None, metavar="PATH",
        help="03_transcripts/{buch}/ – DE-Transkripte für Option 3 (Retranslation)",
    )
    args = parser.parse_args()
    patch_gme(
        args.original_gme, args.media_dir, args.output_gme,
        voice=args.voice, lang=args.lang,
        max_diff=args.max_diff,
        speakers_json=args.speakers_json,
        transcripts_dir=args.transcripts_dir,
    )
