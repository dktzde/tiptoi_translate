"""
transcribe.py – Tiptoi Whisper Transkription (Windows, Intel GPU / CPU)
=======================================================================
Liest einen OGG-ZIP, transkribiert mit faster-whisper (OpenVINO oder CPU),
schreibt Transcripts + Timestamps als ZIP.

Verwendung:
  python transcribe.py BOOK_ogg.zip
  python transcribe.py BOOK_ogg.zip --model large-v3-turbo
  python transcribe.py BOOK_ogg.zip --model small

Ausgabe: BOOK_transcripts.zip (im gleichen Ordner wie die Eingabe)
"""

import argparse
import json
import os
import sys
import zipfile
from pathlib import Path

VERSION = "v30"   # muss mit PIPELINE_VERSION in pipeline.py übereinstimmen
LANG    = "de"


# ─── Device-Erkennung ────────────────────────────────────────────────────────

def pick_device(model_name: str):
    """Versucht OpenVINO (Intel GPU/CPU), fällt auf CPU int8 zurück."""
    from faster_whisper import WhisperModel

    for device, compute in [("openvino", "int8"), ("cpu", "int8")]:
        try:
            print(f"  Versuche device={device} compute={compute}...")
            m = WhisperModel(model_name, device=device, compute_type=compute,
                             cpu_threads=4, num_workers=1)
            print(f"  ✓ {device}/{compute}")
            return m, device
        except Exception as e:
            print(f"  ✗ {device}: {e}")

    raise RuntimeError("Kein funktionsfähiges Device gefunden (OpenVINO + CPU fehlgeschlagen).")


# ─── Transkription ────────────────────────────────────────────────────────────

def transcribe_zip(ogg_zip: Path, model_name: str) -> Path:
    book = ogg_zip.stem.replace("_ogg", "")
    out_dir   = ogg_zip.parent
    tmp_ogg   = ogg_zip.parent / f"_tmp_{book}_ogg"
    tmp_txt   = ogg_zip.parent / f"_tmp_{book}_txt"
    out_zip   = out_dir / f"{book}_transcripts.zip"

    tmp_ogg.mkdir(exist_ok=True)
    tmp_txt.mkdir(exist_ok=True)

    # OGGs entpacken
    print(f"\nEntpacke {ogg_zip.name}...")
    with zipfile.ZipFile(ogg_zip) as zf:
        zf.extractall(tmp_ogg)
    ogg_files = sorted(tmp_ogg.glob("*.ogg"))
    print(f"{len(ogg_files)} OGGs gefunden.")

    if not ogg_files:
        raise FileNotFoundError(f"Keine OGGs in {ogg_zip}")

    # Whisper laden
    print(f"\nLade Whisper {model_name}...")
    model, device = pick_device(model_name)

    # Transkription
    print(f"\nTranskribiere ({len(ogg_files)} Dateien, {device})...\n")
    done = skipped = errors = 0

    for i, ogg in enumerate(ogg_files):
        txt_path = tmp_txt / f"{ogg.stem}_{VERSION}.txt"
        ts_path  = tmp_txt / f"{ogg.stem}_{VERSION}_ts.json"

        if txt_path.exists():
            skipped += 1
            continue

        try:
            segs, _ = model.transcribe(
                str(ogg), language=LANG, beam_size=5,
                vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=300),
            )
            segs = list(segs)
            text = " ".join(s.text.strip() for s in segs).strip()
            txt_path.write_text(text, encoding="utf-8")

            if segs:
                import soundfile as sf
                dur = sf.info(str(ogg)).duration
                ts  = {"start":    round(segs[0].start, 3),
                       "end":      round(segs[-1].end,  3),
                       "duration": round(dur, 3)}
                ts_path.write_text(json.dumps(ts), encoding="utf-8")

            done += 1
        except Exception as e:
            txt_path.write_text("", encoding="utf-8")
            errors += 1
            print(f"  ⚠ Fehler bei {ogg.name}: {e}")

        if (i + 1) % 50 == 0 or (i + 1) == len(ogg_files):
            print(f"  [{i+1:4d}/{len(ogg_files)}]  fertig={done}  übersprungen={skipped}  fehler={errors}")

    print(f"\nFertig: {done} transkribiert · {skipped} übersprungen · {errors} Fehler")

    # ZIP packen
    print(f"\nErstelle {out_zip.name}...")
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(tmp_txt.iterdir()):
            zf.write(f, f.name)
    size_mb = out_zip.stat().st_size / 1024 / 1024
    print(f"ZIP: {size_mb:.1f} MB → {out_zip}")

    # Temp-Ordner aufräumen
    import shutil
    shutil.rmtree(tmp_ogg)
    shutil.rmtree(tmp_txt)

    return out_zip


# ─── CLI ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Tiptoi Whisper Transkription (Windows Intel GPU)")
    parser.add_argument("ogg_zip", help="Pfad zur OGG-ZIP-Datei (z.B. Pocketwissen_Feuerwehr_ogg.zip)")
    parser.add_argument("--model", default="large-v3-turbo",
                        choices=["tiny", "base", "small", "medium", "large-v3-turbo"],
                        help="Whisper-Modell (Standard: large-v3-turbo)")
    args = parser.parse_args()

    ogg_zip = Path(args.ogg_zip)
    if not ogg_zip.exists():
        print(f"Fehler: Datei nicht gefunden: {ogg_zip}")
        sys.exit(1)

    result = transcribe_zip(ogg_zip, args.model)
    print(f"\n✓ Fertig! Transcripts-ZIP: {result}")
    print("  → Auf Linux-Maschine kopieren und entpacken nach 03_transcripts/BUCHNAME/")
