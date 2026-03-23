#!/usr/bin/env python3
"""Sprecher-Analyse mit pyannote.audio (ECAPA-TDNN Embeddings).
Genauer als Pitch-Analyse: erkennt echte Sprecher statt Geräusch-Cluster.

Verwendung:
  python analyze_speakers_pyannote.py "01_input/LSW_Uhr_und_Zeit (1).gme"
  python analyze_speakers_pyannote.py "01_input/buch.gme" --save   # speakers.json speichern

Voraussetzung:
  HF_TOKEN=hf_xxxx in .env (https://huggingface.co/settings/tokens)
  Model-Zugang akzeptiert: https://huggingface.co/pyannote/embedding
"""
import sys
import time
import subprocess
import tempfile
import argparse
from pathlib import Path

import numpy as np
from dotenv import load_dotenv
import os

load_dotenv()

TTTOOL   = str(Path.home() / ".local/bin/tttool")
HF_TOKEN = os.getenv("HF_TOKEN")


def load_embedding_model():
    """Lädt pyannote ECAPA-TDNN Embedding-Modell."""
    from pyannote.audio import Inference
    from pyannote.audio import Model

    if not HF_TOKEN:
        print("FEHLER: HF_TOKEN fehlt in .env")
        print("  1. https://huggingface.co/pyannote/embedding → 'Agree and access'")
        print("  2. https://huggingface.co/settings/tokens → neues Read-Token")
        print("  3. HF_TOKEN=hf_xxx in .env eintragen")
        sys.exit(1)

    print("Lade pyannote ECAPA-TDNN Modell (ggf. Download ~500 MB)...", flush=True)
    t0 = time.time()
    model = Model.from_pretrained("pyannote/embedding", use_auth_token=HF_TOKEN)
    inference = Inference(model, window="whole")
    print(f"  Modell geladen in {time.time()-t0:.1f}s\n")
    return inference


def get_embedding(inference, ogg_path: Path):
    """Gibt Speaker-Embedding für eine OGG-Datei zurück, oder None bei Fehler."""
    try:
        emb = inference(str(ogg_path))
        return np.array(emb).flatten()
    except Exception:
        return None


def cluster_embeddings(embeddings: dict[str, np.ndarray], max_k: int = 4):
    """Clustert Embeddings mit K-Means + Silhouette-Score."""
    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_score
    from sklearn.preprocessing import normalize

    stems  = list(embeddings.keys())
    X      = normalize(np.stack(list(embeddings.values())))

    print("Clustering-Ergebnisse:")
    print("-" * 45)
    best_result = None
    best_score  = -1.0

    for k in range(1, min(max_k + 1, len(stems))):
        if k == 1:
            print(f"\n  K=1  (kein Clustering möglich)")
            print(f"    Stimme 0: alle {len(stems)} Dateien")
            continue

        km    = KMeans(n_clusters=k, random_state=0, n_init="auto").fit(X)
        score = silhouette_score(X, km.labels_)
        counts = [int((km.labels_ == i).sum()) for i in range(k)]

        marker = " ← BEST" if score > best_score else ""
        if score > best_score:
            best_score  = score
            best_result = (k, km.labels_, stems, score)

        print(f"\n  K={k}  (Sil={score:.2f}){marker}")
        for i in range(k):
            print(f"    Gruppe {i}: {counts[i]:4d} Dateien")

    return best_result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("gme", help="Pfad zur Original-GME-Datei")
    parser.add_argument("--max-k", type=int, default=4)
    parser.add_argument("--save", action="store_true",
                        help="speakers.json in 03_transcripts/{buch}/ speichern")
    parser.add_argument("--limit", type=int, default=0,
                        help="Nur N Dateien verarbeiten (0=alle, für Timing-Test)")
    args = parser.parse_args()

    gme  = Path(args.gme)
    base = Path(__file__).parent
    book = gme.stem

    if not gme.exists():
        print(f"Fehler: {gme} nicht gefunden"); sys.exit(1)

    inference = load_embedding_model()

    print(f"Extrahiere Original-OGGs aus: {gme.name}")
    t_start = time.time()

    with tempfile.TemporaryDirectory() as tmpdir:
        subprocess.run([TTTOOL, "media", "-d", tmpdir, str(gme)],
                       check=True, capture_output=True)

        ogg_files = sorted(Path(tmpdir).glob("*.ogg"))
        total = len(ogg_files)
        if args.limit:
            ogg_files = ogg_files[:args.limit]
            print(f"Timing-Test: {args.limit} von {total} Dateien\n")
        else:
            print(f"{total} OGG-Dateien gefunden.\n")

        print("Embedding-Extraktion läuft...")
        embeddings: dict[str, np.ndarray] = {}
        t_emb = time.time()
        for i, ogg in enumerate(ogg_files, 1):
            emb = get_embedding(inference, ogg)
            if emb is not None:
                embeddings[ogg.stem] = emb
            if i % 50 == 0 or i == len(ogg_files):
                elapsed = time.time() - t_emb
                rate    = i / elapsed
                eta     = (len(ogg_files) - i) / rate if rate > 0 else 0
                print(f"  {i}/{len(ogg_files)}  "
                      f"({rate:.1f} Dateien/s, ETA {eta/60:.1f} min)", flush=True)

        t_emb_total = time.time() - t_emb
        print(f"\n{len(embeddings)} Embeddings extrahiert "
              f"({total - len(embeddings)} übersprungen) in {t_emb_total:.0f}s")

        if args.limit:
            extrapol = t_emb_total / len(ogg_files) * total
            print(f"  → Hochrechnung auf alle {total} Dateien: "
                  f"~{extrapol/60:.1f} Minuten")
            return

        print()
        best = cluster_embeddings(embeddings, max_k=args.max_k)

        if best and args.save:
            import json
            k, labels, stems, score = best
            voice_map = {stem: int(lbl) for stem, lbl in zip(stems, labels)}
            out = base / "03_transcripts" / book / "speakers.json"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps({
                "num_speakers": k,
                "silhouette":   round(score, 3),
                "voice_map":    voice_map,
            }, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"\n  speakers.json gespeichert: {out}")

    total_time = time.time() - t_start
    print(f"\nGesamtzeit: {total_time/60:.1f} Minuten")
    print("=" * 55)


if __name__ == "__main__":
    main()
