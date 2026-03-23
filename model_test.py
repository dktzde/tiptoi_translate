"""
Whisper Modell-Vergleich
========================
Testet base, small, medium, large-v3-turbo parallel auf N OGG-Dateien
und erzeugt einen Vergleichs-Report (Konsole + model_test/vergleich.md).

Verwendung:
  python model_test.py
  python model_test.py --book WWW_Unser_Wald --n 20
"""

import time
import argparse
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed

from faster_whisper import WhisperModel

# ─── Konfiguration ────────────────────────────────────────────────────────────

BASE_DIR  = Path(__file__).parent
MODELS    = ["base", "small", "medium", "large-v3-turbo"]
N_FILES   = 20
BOOK      = "WWW_Unser_Wald"


# ─── Transkription (läuft in eigenem Prozess) ─────────────────────────────────

def transcribe_model(args: tuple) -> dict:
    """Wird als separater Prozess gestartet – ein Modell, alle Dateien."""
    model_name, ogg_paths = args
    t0 = time.time()

    model = WhisperModel(model_name, device="cpu", compute_type="int8")
    results = {}
    for path_str in ogg_paths:
        p = Path(path_str)
        segments, _ = model.transcribe(str(p), language="de")
        results[p.stem] = " ".join(s.text for s in segments).strip()

    return {
        "model":   model_name,
        "results": results,
        "elapsed": time.time() - t0,
    }


# ─── Hauptprogramm ────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Whisper Modell-Vergleich")
    parser.add_argument("--book", default=BOOK, help="Buchname (Unterordner in unpacked/)")
    parser.add_argument("--n",    default=N_FILES, type=int, help="Anzahl Testdateien")
    args = parser.parse_args()

    media_dir = BASE_DIR / "02_unpacked" / args.book / "media"
    if not media_dir.exists():
        print(f"Fehler: {media_dir} nicht gefunden – erst GME entpacken.")
        return

    ogg_files = sorted(media_dir.rglob("*.ogg"))[: args.n]
    if not ogg_files:
        print("Keine OGG-Dateien gefunden.")
        return

    out_dir = BASE_DIR / "model_test" / args.book
    out_dir.mkdir(parents=True, exist_ok=True)

    ogg_strs = [str(f) for f in ogg_files]

    print(f"\n{'='*60}")
    print(f"  Whisper Modell-Vergleich – {args.book}")
    print(f"  {len(ogg_files)} Dateien  |  {len(MODELS)} Modelle parallel")
    print(f"{'='*60}\n")

    all_results: dict[str, dict[str, str]] = {}
    timings:     dict[str, float]          = {}

    # Alle 4 Modelle gleichzeitig starten
    with ProcessPoolExecutor(max_workers=len(MODELS)) as executor:
        futures = {
            executor.submit(transcribe_model, (m, ogg_strs)): m
            for m in MODELS
        }
        for future in as_completed(futures):
            data = future.result()
            m    = data["model"]
            all_results[m] = data["results"]
            timings[m]     = data["elapsed"]
            print(f"  [{m}] fertig in {data['elapsed']:.0f}s")

            # Einzelne Transkript-Dateien speichern
            model_dir = out_dir / m
            model_dir.mkdir(exist_ok=True)
            for stem, text in data["results"].items():
                (model_dir / f"{stem}.txt").write_text(text, encoding="utf-8")

    # ─── Konsolen-Report ──────────────────────────────────────────────────────

    print(f"\n{'='*60}")
    print("  ZEITEN")
    print(f"{'='*60}")
    for m in MODELS:
        bar = "█" * int(timings[m] / 10)
        print(f"  {m:20s}  {timings[m]:5.0f}s  {bar}")

    print(f"\n{'='*60}")
    print("  TRANSKRIPT-VERGLEICH")
    print(f"{'='*60}")
    for ogg in ogg_files:
        stem = ogg.stem
        texts = {m: all_results[m].get(stem, "") for m in MODELS}

        # Datei überspringen wenn alle Modelle leer → Geräusch
        if not any(texts.values()):
            continue

        print(f"\n── {stem} ──")
        for m in MODELS:
            t = texts[m]
            label = t[:90] + "…" if len(t) > 90 else (t or "*(Geräusch/Stille)*")
            print(f"  {m:20s}: {label}")

    # ─── Markdown-Report ──────────────────────────────────────────────────────

    report = out_dir / "vergleich.md"
    with report.open("w", encoding="utf-8") as f:
        f.write(f"# Whisper Modell-Vergleich – {args.book}\n\n")
        f.write(f"Modelle: {', '.join(MODELS)} | {len(ogg_files)} Dateien\n\n")

        f.write("## Zeiten\n\n")
        f.write("| Modell | Sekunden |\n|--------|----------|\n")
        for m in MODELS:
            f.write(f"| `{m}` | {timings[m]:.0f}s |\n")
        f.write("\n")

        f.write("## Transkripte\n\n")
        for ogg in ogg_files:
            stem  = ogg.stem
            texts = {m: all_results[m].get(stem, "") for m in MODELS}
            f.write(f"### {stem}\n\n")
            f.write("| Modell | Transkription |\n|--------|---------------|\n")
            for m in MODELS:
                t = texts[m] or "*(Geräusch/Stille)*"
                f.write(f"| `{m}` | {t} |\n")
            f.write("\n")

    print(f"\n  Markdown-Report: {report}\n")


if __name__ == "__main__":
    main()
