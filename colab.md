# Colab – Copy-Paste Zellen

## Versionsübersicht

| pipeline.py | colab_pipeline | PIPELINE_VERSION | Besonderheit |
|-------------|---------------|-----------------|--------------|
| v3.8        | v8            | v29             | Timestamps (_ts.json) für Mixed-Audio |

---

## Schritt 2: Whisper (2a + 2b kombiniert)

```python
# ── Schritt 2a: Whisper laden ────────────────────────────────────
from faster_whisper import WhisperModel
import zipfile, shutil

LOCAL_TMP = '/tmp/transcripts'
os.makedirs(LOCAL_TMP, exist_ok=True)

print(f'Lade Whisper {WHISPER_MODEL}...')
whisper = WhisperModel(WHISPER_MODEL, device='cuda', compute_type='float16')
print('Whisper geladen ✓')

# ── Schritt 2b: Transkription + Timestamps + ZIP → Drive ─────────
ogg_files = sorted(Path(OGG_DIR).glob("*.ogg"))
print(f"{len(ogg_files)} OGGs gefunden")

skipped = done = errors = 0

for i, ogg in enumerate(ogg_files):
    txt_path = Path(LOCAL_TMP) / f"{ogg.stem}_{VERSION}.txt"

    if txt_path.exists():
        skipped += 1
        continue

    try:
        segs, info = whisper.transcribe(
            str(ogg), language=WHISPER_LANG, beam_size=5,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=300)
        )
        segs = list(segs)
        text = " ".join(s.text.strip() for s in segs).strip()
        txt_path.write_text(text, encoding="utf-8")

        if segs:
            import soundfile as sf_ts
            dur = sf_ts.info(str(ogg)).duration
            ts = {"start": round(segs[0].start, 3),
                  "end":   round(segs[-1].end, 3),
                  "duration": round(dur, 3)}
            ts_path = Path(LOCAL_TMP) / f"{ogg.stem}_{VERSION}_ts.json"
            ts_path.write_text(json.dumps(ts), encoding="utf-8")
        done += 1
    except Exception as e:
        txt_path.write_text("", encoding="utf-8")
        errors += 1

    if (i + 1) % 200 == 0 or (i + 1) == len(ogg_files):
        print(f"[{i+1}/{len(ogg_files)}] done={done} skip={skipped} err={errors}")

print(f"Fertig! {done} transkribiert · {skipped} übersprungen · {errors} Fehler")

print("Erstelle ZIP...")
ZIP_PATH = f"/tmp/{BOOK}_transcripts.zip"
with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED) as zf:
    for f in Path(LOCAL_TMP).glob("*.txt"):
        zf.write(f, f.name)
    for f in Path(LOCAL_TMP).glob("*.json"):
        zf.write(f, f.name)

zip_mb = os.path.getsize(ZIP_PATH) / 1024 / 1024
print(f"ZIP-Größe: {zip_mb:.1f} MB")

shutil.copy(ZIP_PATH, f"{DRIVE_BASE}/{BOOK}_transcripts.zip")
print(f"ZIP hochgeladen → {DRIVE_BASE}/{BOOK}_transcripts.zip ✓")
```
