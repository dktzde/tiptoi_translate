#!/usr/bin/env python3
"""Analysiert Sprecher-Clustering für ein Buch (nur Pitch + Clustering, kein Schreiben).
Nutzt Original-OGGs direkt aus der GME-Eingabedatei.

Verwendung:
  python analyze_speakers.py "01_input/LSW_Uhr_und_Zeit (1).gme"
"""
import sys
import subprocess
import tempfile
import warnings
import argparse
from pathlib import Path

import numpy as np
import librosa
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score

TTTOOL = str(Path.home() / ".local/bin/tttool")

def mean_pitch(ogg_path: Path) -> float | None:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        y, sr = librosa.load(str(ogg_path), sr=None, mono=True)
    if len(y) < sr * 0.2:
        return None
    fmin = librosa.note_to_hz("C2")
    fmax = librosa.note_to_hz("C7")
    f0 = librosa.yin(y, fmin=fmin, fmax=fmax, sr=sr)
    voiced = f0[f0 > fmin * 1.1]
    if len(voiced) < 5:
        return None
    return float(np.median(voiced))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("gme", help="Pfad zur Original-GME-Datei")
    parser.add_argument("--max-k", type=int, default=4, help="Maximale Sprecher-Anzahl (Standard: 4)")
    args = parser.parse_args()

    gme = Path(args.gme)
    if not gme.exists():
        print(f"Fehler: {gme} nicht gefunden")
        sys.exit(1)

    print(f"\nSprecher-Analyse: {gme.name}")
    print("=" * 55)

    with tempfile.TemporaryDirectory() as tmpdir:
        print(f"Extrahiere Original-OGGs aus GME...")
        subprocess.run([TTTOOL, "media", "-d", tmpdir, str(gme)],
                       check=True, capture_output=True)

        ogg_files = sorted(Path(tmpdir).glob("*.ogg"))
        total = len(ogg_files)
        print(f"{total} OGG-Dateien gefunden.\n")

        print(f"Pitch-Analyse läuft...")
        pitches: dict[str, float] = {}
        for i, ogg in enumerate(ogg_files, 1):
            if i % 100 == 0 or i == total:
                print(f"  {i}/{total}", flush=True)
            p = mean_pitch(ogg)
            if p is not None:
                pitches[ogg.stem] = p

        print(f"\n{len(pitches)} Dateien mit erkennbarem Pitch (von {total})")
        print(f"{total - len(pitches)} Dateien: Stille / Geräusche / zu kurz\n")

        if len(pitches) < 2:
            print("Zu wenige Sprach-Dateien – kein Clustering möglich.")
            return

        X = np.array(list(pitches.values())).reshape(-1, 1)

        print("Clustering-Ergebnisse:")
        print("-" * 45)
        for k in range(1, args.max_k + 1):
            if k == 1:
                km = KMeans(n_clusters=1, random_state=0, n_init="auto").fit(X)
                centers = km.cluster_centers_.flatten()
                counts = [len(pitches)]
                score_str = "   –   "
            else:
                km = KMeans(n_clusters=k, random_state=0, n_init="auto").fit(X)
                score = silhouette_score(X, km.labels_)
                centers = np.sort(km.cluster_centers_.flatten())
                counts = [0] * k
                for lbl in km.labels_:
                    counts[lbl] += 1
                # Zähle nach sortierter Reihenfolge neu
                order = np.argsort(km.cluster_centers_.flatten())
                sorted_counts = [counts[order[i]] for i in range(k)]
                score_str = f"Sil={score:.2f}"
                counts = sorted_counts

            print(f"\n  K={k}  ({score_str})")
            for i, (c, n) in enumerate(zip(np.sort(km.cluster_centers_.flatten()) if k > 1 else centers, counts)):
                bar = "★" if (k > 1 and score > 0.5) else " "
                print(f"    Stimme {i}: ~{c:5.0f} Hz  ({n:4d} Dateien) {bar if i==0 else ''}")

        print("\n" + "=" * 55)
        print("Empfehlung: K mit höchstem Silhouette-Score wählen.")
        print("Stimmen-Zuordnung: aufsteigend nach Hz (tief→hoch)")
        print("  fr: Henri(0,tief) → Vivienne(1,mittel) → Remy(2,hoch)")
        print("  ch: Jan(0,tief)   → Leni(1,hoch)")


if __name__ == "__main__":
    main()
