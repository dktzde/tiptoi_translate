#!/usr/bin/env python3
"""Sprecher-Analyse mit resemblyzer (GE2E Speaker Embeddings).
Kein HuggingFace-Token nötig. Ersetzt Pitch-Analyse in pipeline.py.

Verwendung:
  python analyze_speakers_resemblyzer.py "01_input/buch.gme"
  python analyze_speakers_resemblyzer.py "01_input/buch.gme" --save
  python analyze_speakers_resemblyzer.py "01_input/buch.gme" --limit 50   # Timing-Test
"""
import sys
import time
import json
import subprocess
import tempfile
import argparse
from pathlib import Path

import numpy as np
from resemblyzer import VoiceEncoder, preprocess_wav
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import normalize

TTTOOL = str(Path.home() / ".local/bin/tttool")
BASE   = Path(__file__).parent


def get_embedding(encoder: VoiceEncoder, ogg_path: Path):
    """Gibt Speaker-Embedding zurück, oder None bei Stille/Fehler."""
    try:
        wav = preprocess_wav(str(ogg_path))
        if len(wav) < 1600:   # kürzer als 100ms → überspringen
            return None
        return encoder.embed_utterance(wav)
    except Exception:
        return None


def cluster_embeddings(embeddings: dict[str, np.ndarray], max_k: int) -> tuple:
    """Clustert Embeddings, gibt (best_k, labels, stems, score) zurück."""
    stems = list(embeddings.keys())
    X     = normalize(np.stack(list(embeddings.values())))

    if len(stems) < 2:
        return 1, np.zeros(len(stems), dtype=int), stems, 0.0

    print("\nClustering-Ergebnisse:")
    print("-" * 45)

    best_k, best_score, best_labels = 1, -1.0, np.zeros(len(stems), dtype=int)

    for k in range(2, min(max_k + 1, len(stems))):
        km    = KMeans(n_clusters=k, random_state=0, n_init="auto").fit(X)
        score = silhouette_score(X, km.labels_)
        counts = [int((km.labels_ == i).sum()) for i in range(k)]
        marker = " ← BEST" if score > best_score else ""
        if score > best_score:
            best_k, best_score, best_labels = k, score, km.labels_.copy()
        print(f"  K={k}  Sil={score:.3f}{marker}")
        for i, n in enumerate(counts):
            print(f"    Gruppe {i}: {n:4d} Dateien")

    print(f"\n→ Bestes Ergebnis: {best_k} Sprecher (Silhouette {best_score:.3f})")
    return best_k, best_labels, stems, best_score


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("gme",      help="Pfad zur Original-GME-Datei")
    parser.add_argument("--max-k",  type=int, default=4)
    parser.add_argument("--save",   action="store_true",
                        help="speakers.json in 03_transcripts/{buch}/ speichern")
    parser.add_argument("--limit",  type=int, default=0,
                        help="Nur N Dateien verarbeiten (0=alle, für Timing-Test)")
    args = parser.parse_args()

    gme  = Path(args.gme)
    book = gme.stem

    if not gme.exists():
        print(f"Fehler: {gme} nicht gefunden"); sys.exit(1)

    print(f"\nSprecher-Analyse: {gme.name}")
    print("=" * 55)

    print("Lade resemblyzer Modell (ggf. Download ~17 MB)...", flush=True)
    t0      = time.time()
    encoder = VoiceEncoder(device="cpu")
    print(f"  Modell geladen in {time.time()-t0:.1f}s\n")

    print(f"Extrahiere Original-OGGs aus GME...")
    t_start = time.time()

    with tempfile.TemporaryDirectory() as tmpdir:
        subprocess.run([TTTOOL, "media", "-d", tmpdir, str(gme)],
                       check=True, capture_output=True)

        ogg_files = sorted(Path(tmpdir).glob("*.ogg"))
        total     = len(ogg_files)
        sample    = ogg_files[:args.limit] if args.limit else ogg_files
        print(f"{total} OGG-Dateien gesamt"
              + (f" – Timing-Test mit {args.limit}" if args.limit else "") + "\n")

        print("Embedding-Extraktion läuft...")
        embeddings: dict[str, np.ndarray] = {}
        t_emb = time.time()

        for i, ogg in enumerate(sample, 1):
            emb = get_embedding(encoder, ogg)
            if emb is not None:
                embeddings[ogg.stem] = emb
            if i % 50 == 0 or i == len(sample):
                elapsed = time.time() - t_emb
                rate    = i / elapsed
                eta     = (len(sample) - i) / rate if rate > 0 else 0
                print(f"  {i}/{len(sample)}  "
                      f"({rate:.1f} Dateien/s, ETA {eta/60:.1f} min)", flush=True)

        t_emb_done = time.time() - t_emb
        print(f"\n{len(embeddings)} Embeddings in {t_emb_done:.0f}s "
              f"({len(sample)-len(embeddings)} übersprungen/Stille)")

        if args.limit:
            extrapol = t_emb_done / len(sample) * total
            print(f"\n→ Hochrechnung auf alle {total} Dateien: "
                  f"~{extrapol/60:.1f} Minuten")
            return

        best_k, labels, stems, score = cluster_embeddings(embeddings, args.max_k)

        if args.save:
            voice_map = {stem: int(lbl) for stem, lbl in zip(stems, labels)}
            out = BASE / "03_transcripts" / book / "speakers.json"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps({
                "num_speakers": best_k,
                "silhouette":   round(score, 3),
                "voice_map":    voice_map,
            }, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"\n  speakers.json gespeichert → {out.relative_to(BASE)}")
            print(f"  Nächster Pipeline-Lauf nutzt diese Sprecher-Zuordnung automatisch.")

    print(f"\nGesamtzeit: {(time.time()-t_start)/60:.1f} Minuten")
    print("=" * 55)


if __name__ == "__main__":
    main()
