"""
pipeline.py – Minimale Änderung für gme_patch.py v4
=====================================================
Nur der --use-patcher Block in Schritt 6 ändert sich.

VORHER (v3):
─────────────────────────────────────────────────────
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

NACHHER (v4):
─────────────────────────────────────────────────────
    elif use_patcher:
        print(f"\n── Schritt 6: GME neu packen via gme_patch.py ──")
        sys.path.insert(0, str(BASE_DIR / "gme_patcher"))
        from gme_patch import patch_gme as _patch_gme
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        out_gme = OUTPUT_DIR / f"{book}{cfg['suffix']}_p_{PIPELINE_VERSION}.gme"
        result = _patch_gme(gme_path, tts_dir, out_gme, force=True)
        if result["mode"] == "aborted":
            print("  Abgebrochen – keine GME erzeugt.")
        else:
            out_gme = result["output"]
            label = " (experimentell)" if result["mode"] == "experimental" else ""
            print(f"\n{'='*55}")
            print(f"  Fertig! Neue GME-Datei{label}:")
            print(f"  {out_gme}")
            print(f"{'='*55}\n")
"""
