# Changelog – pipeline.py / Skripte / Notebooks

## colab_pipeline v23 – 2026-03-28
### GPU-Typ automatische Erkennung
- `GPU_TYPE = 'T4'` (hartkodiert) ersetzt durch `_detect_gpu_type()` Funktion
- Erkennt GPU via `torch.cuda.get_device_name(0)`: T4, L4, A100-40, A100-80, G4, H100
- A100-Unterscheidung per VRAM-Größe (>60 GB → A100_80, sonst A100_40)
- Ausgabe: `GPU-Typ erkannt: A100_40  (NVIDIA A100-SXM4-40GB)` statt immer T4 in CSV
- Fallback auf `T4` bei unbekannter GPU oder CPU-Modus
- `colab_pipeline_example.ipynb` ebenfalls aktualisiert
- Backup: `backup/colab_pipeline_v23.ipynb`

## pipeline.py v38 – 2026-03-28
### Retry bei Mistral 503 / unreachable_backend
- Retry-Logik in `translate_one()` und `translate_batch()` erkennt nun auch 503-Fehler
- Bedingung erweitert: `"503"`, `"unreachable"`, `"backend"`, `"server error"` lösen Retry aus
- Ausgabe zeigt `SERVER ERROR 503` statt `RATE LIMIT` bei Server-Fehlern
- Gleiche Wartezeiten wie bei Rate Limit: 60s / 90s / 180s
- Backup: `backup/pipeline_v37_503_retry.py`

## pipeline.py v37 – 2026-03-28
### Zeichenbasierte Übersetzungs-Batches
- `BATCH_SIZE = 10` (feste Anzahl) ersetzt durch `BATCH_MAX_CHARS = 1300` (max. Zeichen/Batch)
- `BATCH_MAX_CHARS` steht im Hauptkonfig-Block oben (neben `PIPELINE_VERSION`) – einfach änderbar
- Neue Batch-Logik: Items werden akkumuliert bis `sum(len(text)) > BATCH_MAX_CHARS` → neuer Batch
- Print-Ausgabe: `"in N Batches (max. 1300 Zeichen)"` statt `"(à 10)"`
- Backup: `backup/pipeline_v36_pre_char_batching.py`

## gme_patch_same_lenght.py v7 + pipeline.py v36 – 2026-03-27
### Retranslation im Pipeline-Modus (max_diff=inf)
- **Bug:** Bei `max_diff=float('inf')` wurde der `_interactive_menu`-Branch (inkl. Option 3: Retranslation)
  niemals erreicht – `over_pct > inf` ist immer False → direkt truncated
- **Fix:** Neue Verzweigung `if max_diff == float('inf'):` vor dem interaktiven Branch:
  - Sucht DE-Transkript via `_find_transcript()`
  - Ruft `_retranslate()` auf: DE-Text → Mistral kürzt+übersetzt → Edge-TTS
  - Fallback-Kette: `retranslated` → `retranslated+atempo` → `retranslated+truncated` → `truncated`
  - Kein Transkript vorhanden → direkt `truncated`
- **Neue Log-Methoden:** `retranslated`, `retranslated+atempo`, `retranslated+truncated`
- **pipeline.py v36:** `sl_lang` unterstützt alle 5 Sprachen (`fr/ch/vo/by/nd`) statt nur `fr/ch`
- Backup: `backup/gme_patch_same_lenght_v6.py`, `backup/pipeline_v35_pre_retranslation.py`

## pipeline.py v35 – 2026-03-27
### Kompaktere Ausgaben (Schritt 1–5)
- **Schritt 1:** tttool-Output unterdrückt (`capture_output=True`); zeigt nur Anzahl entpackter OGGs
- **Schritt 2:** Header zeigt explizit "übersprungen" wenn speakers.json bereits vorhanden
- **Schritt 3:** Zählt neue / Resume / Geräusch-Transkripte; zeigt Summary statt Einzel-Noise-Warnungen; Whisper-Progress nur wenn wirklich transkribiert wird
- **Schritt 4:** `translate_batch` zeigt vor dem Start: "Alle N übersprungen" oder "N übersprungen, M werden übersetzt"
- **Schritt 5:** Keine Einzeldatei-Logs mehr; zeigt Modus (ohne/mit Pausen), Stimmen-Verteilung am Anfang; Progress alle 100 Dateien inkl. Stimmen-Info; finaler Summary (erzeugt / übersprungen / fehlgeschlagen)
- Backup: `backup/pipeline_v34_pre_compact_output.py`

## pipeline.py v34 – 2026-03-27
### --fast-tts Flag (Standard: an)
- Zufällige Pausen zwischen TTS-Anfragen werden standardmäßig übersprungen
- Hauptschleife: `asyncio.sleep(random.uniform(1.5, 3.0))` entfällt bei fast_tts=True
- Retry-Schleife: `asyncio.sleep(random.uniform(5.0, 10.0))` entfällt bei fast_tts=True
- `--no-fast-tts` reaktiviert die alten Pausen (für rate-limit-schonendes Verhalten)
- Backup: `backup/pipeline_v33_pre_fast_tts.py`

## gme_uebertragen.sh (backup v1→v2) – 2026-03-27
### CH-Stift: vo/by/nd als Synonyme
- `SEARCH_VARIANTS`-Array: bei `PEN_VARIANT=CH` werden zusätzlich `*_vo_*.gme`, `*_by_*.gme`, `*_nd_*.gme` gefunden
- Suchschleife über alle Varianten, Kandidaten dedupliziert (sort -u)
- Dialekt-GMEs (Vogtländisch, Bayrisch, Plattdeutsch) landen im selben CH-Unterordner

## pipeline.py (backup v3.24) – 2026-03-26
### Drei neue Dialekt-Sprachen + 8 Stimmen pro Sprache
- **Vogtländisch** (`--language vo`): magistral-medium-latest, Prompt mit Lautregeln (aa, isch, -la, weiche Konsonanten)
- **Bayrisch** (`--language by`): magistral-medium-latest, Prompt Oberbairisch/München (oa, i, ned, -erl)
- **Plattdeutsch** (`--language nd`): magistral-medium-latest, Prompt Hamburger Platt (maken, dat/wat, Steen/Huus)
- Alle 5 Sprachen auf **8 Stimmen** erweitert (FR: +DeniseNeural, GerardNeural, FabriceNeural; CH/BY/VO/ND: voller deutscher Stimmen-Pool)
- Stimmen-Reihenfolge nach Dialekt-Nähe: BY → AT-Stimmen zuerst, VO/ND → Multilingual-Stimmen zuerst, CH → CH-Stimmen zuerst
- Neue Dialekte nutzen `magistral-medium-latest` (Reasoning-Modell) für bessere Dialekt-Qualität

## colab_pipeline_v22 + pipeline.py (backup v3.23) – 2026-03-26
### Copyright/Noise-Erkennung in Colab + Pipeline integriert
- **colab_pipeline_v22** (cell-12): `_is_noise_transcript()` nach Whisper – zählt + meldet Copyright-Stems
  (gleiche Regex wie pipeline.py). Erkennung auch bei Resume (bestehende TXTs werden geprüft).
- Logik aus `repair_lsw_copyright.py` in pipeline.py eingebaut (Option A)
- **Schritt 3**: `noise_stems`-Set trackt erkannte Copyright-Stems; leere Übersetzung wird
  IMMER geschrieben (nicht nur wenn noch keine existiert) → überschreibt alte falsche Übersetzungen
- **Vor Schritt 5**: Aufräum-Pass löscht alte falsche TTS-Dateien (MP3+OGG) für Copyright-Stems
- `repair_lsw_copyright.py` entfernt (→ `backup/`)
### gme_patch.py v4 Integration
- Schritt 6 (`--use-patcher`): nutzt neues `patch_gme()` API mit `force=True` + Result-Dict
- Erkennt Safe/Experimentell-Modus, zeigt Label in Ausgabe
- `[ALPHA]` aus Überschrift entfernt

## colab_pipeline_v21 + pipeline.py (backup v3.22) – 2026-03-24
### Bugfix (cell-9)
- `k_max < 2` (≤2 Samples): Guard verhindert `max()` auf leerem Dict + IndexError
- `MIN_K > k_max`: Fallback auf gesamten K-Bereich statt leerem `proposals`-Array
### Neu
- `pipeline.py`: neues Argument `--min-k K` (Standard: 4) – schreibt `MIN_K = K` in `colab_config.py`
- `colab_pipeline_v21` cell-4: `MIN_K` wird aus `colab_config.py` geladen statt hardcoded (`globals().get('MIN_K', 4)`)
- `colab_pipeline_v21` cell-9 (Clustering): komplett neu
  - Berechnet Silhouette für alle K=2..MAX_K
  - ASCII-Chart der gesamten Kurve mit Markierung der MIN_K-Grenze
  - Findet lokale Maxima im Bereich K≥MIN_K
  - Präsentiert 3 Vorschläge (lokale Maxima nach Score, Rest auffüllen) mit `input()`-Abfrage
  - Nutzer wählt [1/2/3] oder gibt direkte Zahl ein; Enter = Vorschlag 1

## pipeline.py (v32, backup v3.21) – 2026-03-24
### Neu
- `tts_one()`: Retry-Logik mit bis zu 3 Versuchen und steigender Wartezeit (5s, 10s, 15s + Jitter) statt direktem Überspringen bei Fehler (503, "No audio received" etc.)
- Hauptschleife: zufällige Pause von 1,5–3,0 Sekunden zwischen TTS-Anfragen (`asyncio.sleep(random.uniform(1.5, 3.0))`) zur Reduktion von Rate-Limit-Fehlern
- `failed_tts`-Liste: Dateien die nach allen Retries fehlschlagen werden gesammelt und in Schritt 5b erneut versucht (mit längerer Pause 5–10s)
- `_clean_translation()`: Mistral-Preamble-Erkennung (`_PREAMBLE_RE`) – wenn Text Muster wie "Voici la traduction", "je suis prêt à traduire" etc. enthält und kürzer als 200 Zeichen ist, wird leerer String zurückgegeben → TTS wird nicht aufgerufen (verhindert "No audio received"-Fehler bei leerem Transkript)

## colab_sync.sh (v3) – 2026-03-22
### Neu
- Neuer Modus `bench`: lädt nur `gpu_benchmark.csv` von Drive → `backup/gpu_benchmark.csv` (mit Append-Logik)

## colab_sync.sh (v2) – 2026-03-22
### Neu
- `download`: lädt `gpu_benchmark.csv` von Drive herunter → `backup/gpu_benchmark.csv`
- Backup-Logik: falls Datei bereits lokal vorhanden, werden nur neue Zeilen angehängt (kein Überschreiben)

## gme_patch.py (v3) – 2026-03-22
### Bugfix (kritisch)
- Post-Audio-Daten (Binaries, Single Binaries, Special Symbols) werden jetzt korrekt mitgenommen und nach dem neuen Audio angehängt
- Alle absoluten Zeiger darauf (Header + interne Binary-Table-Header) werden um `shift` verschoben
- `last_audio_end` wird korrekt als `max(offset+length)` aller Einträge berechnet

## pipeline.py (v32) – 2026-03-22
### Neu
- `--use-patcher` Flag [ALPHA]: Schritt 6 verwendet `gme_patcher/gme_patch.py` statt `tttool assemble` → Spiele bleiben erhalten (Binary-Patch)
- Ausgabedatei bei `--use-patcher`: `{buch}{sprache}_p_v32.gme` (statt `_v32.gme`)

## pipeline.py (v31) – 2026-03-22
### Neu
- `--language` hat jetzt Kurzform `-l` (z.B. `pipeline.py buch.gme -l ch`)

## colab_pipeline_v20 – 2026-03-22
### Neu
- Clustering (cell-8): alle Silhouette-Scores (K=2..MAX_K) werden als `silhouette_scores`-Dict in speakers.json gespeichert
- Neue letzte Zelle (cell-kill): beendet die Colab-Session automatisch via `runtime.unassign()` → keine weiteren GPU-Kosten nach Abschluss
- Config-Zelle: `MIN_K = 2` – Mindestanzahl Sprecher; falls Silhouette-Optimum < MIN_K, wird MIN_K erzwungen (mit Warnung)
### Bugfix
- `login(token=HF_TOKEN, quiet=True)` → `login(token=HF_TOKEN)` – quiet-Parameter in neueren huggingface_hub-Versionen entfernt

## colab_pipeline_v19 – 2026-03-22
### Neu
- Zelle 11: Zeitmessung der Transkription (start/end)
- Benchmark-Ausgabe am Ende: Laufzeit, CU-Verbrauch, Kosten, normiert auf 1000 OGGs
- CSV-Log `gdrive:tiptoi/gpu_benchmark.csv` – wird pro Durchlauf erweitert (datum, buch, gpu, ogg_anzahl, laufzeit_min, min_per_1000, actual_cu, cu_per_1000, kosten_eur)

## colab_pipeline_v18 – 2026-03-22
### Bugfixes
- Zelle 4: HF_TOKEN fehlte komplett (Pyannote-Login wäre gescheitert)
- Zelle 11: ZIP-Upload-Pfad korrigiert: DRIVE_BASE → TRANSCRIPT_ZIP (gdrive:tiptoi/)

## colab_pipeline_v17 – 2026-03-22 (aktualisiert)
### Ergänzungen
- Config-Zelle: GPU_TYPE Variable (T4/L4/A100_40/A100_80/G4/H100)
- Automatische Kostenberechnung: Zeit + CU + € basierend auf OGG-Anzahl und GPU
- Wenn OGG-Ordner schon befüllt: echte Dateianzahl in Schätzung

## colab_pipeline_v17 – 2026-03-22
### Änderungen
- Zelle 0 (GPU-Check): erkennt ob Pakete bereits installiert → kein doppelter Runtime-Neustart mehr nach Strg+F9
- Startanleitung (Zelle 1) aktualisiert
- GPU-Tabelle: L4 als beste Preis/Leistung, H100 als "Rate unbekannt", sortiert nach Kosten

## colab_pipeline_v16 – 2026-03-22
### Änderungen
- Unzip-Zelle: hardcodiertes `OGG_ZIP = f'{DRIVE_BASE}/...'` entfernt – OGG_ZIP kommt jetzt korrekt aus Config-Zelle (`TIPTOI_DIR`)
- Interne Notebook-Struktur normalisiert (source als Zeilenliste statt Zeichenliste)

## colab_pipeline_v15 – 2026-03-22
### Änderungen
- Konfig-Zelle liest colab_config.py automatisch von gdrive:tiptoi/ (kein manuelles Eintragen mehr)
- pipeline.py-Anweisung vereinfacht: nur noch "Strg+F9" nötig
- v14 ins backup/ verschoben

## colab_pipeline_v14 – 2026-03-22
### Änderungen
- OGG-ZIP wird in `MyDrive/tiptoi/` gesucht (nicht mehr im Buch-Unterordner)
- Transcripts-ZIP wird ebenfalls in `MyDrive/tiptoi/` gespeichert
- Neue Variablen: `TIPTOI_DIR`, `OGG_ZIP`, `TRANSCRIPT_ZIP` in Konfig-Zelle
- v12 ins backup/ verschoben

## colab_pipeline_v12 – 2026-03-22
### Änderungen
- Konfig-Zelle (Zelle 3): Banner `### hier daten für das aktuelle buch eintragen ###` eingefügt
- LANG-Variable als Pflichtfeld hinzugefügt (nur zur Info, Whisper läuft immer auf DE)
- Vorgefüllt mit aktuellem Buch: Mein Wörter-Bilderbuch Unterwegs / v31 / fr
- v10 + v11 ins backup/ verschoben

## colab_sync.sh v4 – 2026-03-22
### Änderungen
- --help / -h: zeigt Verwendung + vollständige rclone-Ersteinrichtung für Google Drive

## colab_sync.sh v3 – 2026-03-22
### Änderungen
- Upload lädt jetzt auch colab_config.py nach gdrive:tiptoi/ hoch

## colab_sync.sh v2 – 2026-03-22
### Änderungen
- Buchname wird automatisch aus neuester colab_config.py gelesen (kein manueller Parameter mehr)
- Kein Sanitize mehr nötig (GME wird von pipeline bereits umbenannt)
- Download-Hinweis zeigt korrekten GME-Pfad

## colab_sync.sh v1 – 2026-03-22
### Neu
- Upload: OGG-ZIP von 07_colab_upload/ → gdrive:tiptoi/
- Download: Transcripts-ZIP von gdrive:tiptoi/ → 03_transcripts/{Buch}/ (entpackt)
- Sanitierung des Buchnamens (Umlaute/Leerzeichen) identisch zu pipeline.py

## pipeline.py v3.24 – 2026-03-22
### Änderungen
- GME-Eingabedatei wird beim Start automatisch umbenannt (Umlaute → ae/oe/ue, Leerzeichen → _)
- Damit sind alle nachgelagerten Ordner/Dateien (02–07) von Anfang an sauber
- `_sanitize`-Hilfsfunktion in ZIP-Erstellung entfernt (redundant)

## pipeline.py v3.23 – 2026-03-22
### Änderungen
- BOOK in Colab-Anweisung zeigt jetzt sanitierten Namen (ohne Umlaute/Leerzeichen)
- colab_pipeline_v14: BOOK ebenfalls auf sanitierten Namen aktualisiert

## pipeline.py v3.22 – 2026-03-22
### Änderungen
- ZIP-Dateiname wird sanitiert: Umlaute → ae/oe/ue/ss, Leerzeichen → _
- Upload-Anweisung zeigt explizit Ziel: "Google Drive / tiptoi /"
- colab_pipeline_v14 referenziert
- Transcripts-ZIP-Pfad in Ausgabe ebenfalls mit sanitiertem Namen

## pipeline.py v3.21 – 2026-03-22
### Änderungen
- Colab-Anweisung: v11 → v12, klarer Hinweis auf 3. Zelle mit visueller Markierung (###-Banner)

## pipeline.py v3.20 – 2026-03-22
### Änderungen
- Colab-Pause-Meldung korrigiert: erklärt ZIP-Inhalt (_ts.json, speakers.json) + Entpack-Ziel
- Entfernt: falsche Angabe dass 04_translated/ von Colab kommt (Mistral läuft immer lokal)

## pipeline.py v3.19 – 2026-03-22
### Änderungen
- Colab-Pause prüft nur fehlende Transkripte (nicht Übersetzungen) – Schritt 4 läuft immer lokal
- Schritt 2 (resemblyzer Clustering) nur noch bei `--offline` – sonst wird speakers.json von Colab geladen
- Fallback wenn kein speakers.json und kein --offline: alle Dateien bekommen Stimme 0

## pipeline.py v3.18 – 2026-03-22
### Änderungen
- Colab-Pause erstellt jetzt automatisch `07_colab_upload/{BOOK}/{BOOK}_ogg.zip` + `colab_config.py`
- `colab_config.py` enthält BOOK, VERSION, LANG zum direkten Copy-Pasten in die Colab Konfig-Zelle
- Neue Konstante `COLAB_DIR = BASE_DIR / "07_colab_upload"`
- `import zipfile` ergänzt

## pipeline.py v3.17 – 2026-03-22
### Änderungen
- `MIN_RESUME_VERSION` zurück auf 29 → v29-Transkripte bleiben gültig, kein Whisper-Neulauf

## pipeline.py v3.16 – 2026-03-22
### Änderungen
- Colab-Pause nach Schritt 1: wenn Transkripte/Übersetzungen fehlen, stoppt die Pipeline und zeigt Colab-Anweisungen
- Neues Flag `--offline`: überspringt die Pause, führt Whisper + Mistral lokal aus (bisheriges Verhalten)

## pipeline.py v3.15 – 2026-03-22
### Änderungen
- `_clean_translation()`: `emoji.replace_emoji()` entfernt Unicode-Emojis vor TTS
  → verhindert dass Emoji-Beschreibungen wie „smiling face with smiling eyes" vorgelesen werden
- `_clean_translation()`: `:emoji_name:`-Kurzform wird zusätzlich per Regex entfernt
- Import `emoji` ergänzt (pip: `emoji==2.15.0`)

## pipeline.py v3.14 – 2026-03-22
### Änderungen
- `repack_gme()`: Temp-Dir verlinkt jetzt alle Audioformate (`.ogg`, `.wav`, `.mp3`, `.flac`), nicht nur `.ogg` → Fix für Bücher mit WAV-Dateien in media/
- `MIN_RESUME_VERSION` wieder auf 31 gesetzt

## pipeline.py v3.13 – 2026-03-22
### Änderungen
- `PIPELINE_VERSION` auf `v31` erhöht
- `MIN_RESUME_VERSION` auf 31 gesetzt → alle v30-Übersetzungen (mit Asterisken/Markdown) werden neu generiert

## pipeline.py v3.12 – 2026-03-22
### Änderungen
- `_clean_translation()`: Gedankenstriche `–` und `—` werden vor TTS zu `, ` (Komma+Leerzeichen) ersetzt, damit edge-tts nicht „Strich" vorliest

## pipeline.py v3.11 – 2026-03-22
### Änderungen
- Übersetzte OGGs werden nicht mehr in `02_unpacked/{BOOK}/media/` geschrieben → Originals bleiben dauerhaft erhalten
- `ogg_out` zeigt jetzt auf `tts_dir` (`05_tts_output/{BOOK}/{language}/`)
- `repack_gme()`: baut Temp-Dir mit Original-OGGs (Symlinks) + übersetzten OGGs als Overlay, assembliert von dort
- Verhindert, dass `prepare_upload.sh` oder Colab übersetzte statt originale OGGs erhält

## pipeline.py v3.10 – 2026-03-22 (2)
### Änderungen
- `repack_gme()`: bevorzugt Haupt-YAML (ohne `.codes.`) beim Assembly – verhindert Fehler wenn tttool mehrere YAML-Dateien exportiert (z.B. `WWW Wald.codes.yaml`)

## pipeline.py v3.10 – 2026-03-22
### Änderungen
- `_clean_translation()`: entfernt Markdown (`**`, `*`, `__`, `` ` ``, `~~`, `#`) und Emojis
  aus Übersetzungstext vor TTS → verhindert „Asterix"-Aussprache durch edge-tts
- Regex `_MD_RE`: trifft 1–3fache `*`, `_`, `` ` ``, `~~`, Headings, non-latin Unicode

## pipeline.py v3.9 – 2026-03-22
### Änderungen
- `PIPELINE_VERSION` → v30
- `--skip-assemble` Flag: überspringt Schritt 6 (tttool assemble)
  → OGGs bleiben in `02_unpacked/.../media/` für direkten Einsatz mit `gme_patch.py`
- Hinweis-Output: zeigt Pfad für gme_patch.py wenn --skip-assemble aktiv

## colab_pipeline_v11.ipynb – 2026-03-22
### Änderungen
- GPU-Check: echter CUDA-Funktionstest (`torch.zeros(1).cuda()`) statt nur `is_available()`
  → fängt "CUDA driver version insufficient" und ähnliche Fehler ab
- Whisper-Load: `_cuda_ok()` Helper → automatischer CPU-Fallback bei CUDA-Fehler
- Beide Fixes gelten auch für pyannote (cell-6 war bereits korrekt)
- speakers.json wird ins Transcripts-ZIP gepackt (von v10-Patch übernommen)

## colab_pipeline_v10.ipynb – 2026-03-22 (Patch)
### Änderungen
- ZIP-Zelle: `speakers.json` wird jetzt ins Transcripts-ZIP eingepackt
  → Verhindert dass pipeline.py lokales resemblyzer-Clustering statt Colab-pyannote nutzt
  → Warnung wenn speakers.json fehlt

## colab_pipeline_v10.ipynb – 2026-03-21
### Änderungen
- GPU-Check und pip install zu einer Zelle zusammengefasst → nur 1 Klick beim Start

## colab_pipeline_v9.ipynb – 2026-03-21
### Änderungen
- GPU-Check als erste Zelle: bricht sofort ab wenn keine T4 GPU zugewiesen

## colab_pipeline_v8.ipynb – 2026-03-21
### Änderungen
- Whisper-Zelle speichert Timestamps als `{stem}_v29_ts.json` neben den TXTs
  Format: `{start, end, duration}` – Sekunden wo Sprache beginnt/endet
- ZIP enthält jetzt auch *.json Timestamp-Dateien

## pipeline.py v3.8 – 2026-03-21
### Änderungen
- `_get_speech_timing()`: lädt `_ts.json` aus 03_transcripts/
- `mix_with_original()`: ffmpeg concat Original-Geräusch + TTS-Stimme
  Unterstützt: Geräusch vorne, Geräusch hinten, Geräusch beidseitig
- Schritt 5: nutzt Mix wenn Timestamps vorhanden und Geräusch > 0.5s
- `NOISE_MIX_MIN_SEC = 0.5` als Schwellwert

## colab_pipeline_v7.ipynb – 2026-03-21
### Änderungen
- Schritt 0: `os.kill(os.getpid(), 9)` nach pip install → Runtime startet automatisch neu
- Warnung vereinfacht: nur noch 2 Schritte (Zelle 0 → Strg+F9)

## colab_pipeline_v6.ipynb – 2026-03-21
### Änderungen
- Bugfix: `\n` in f-string wurde als echtes Newline gespeichert → SyntaxError
  `print(f'\nFertig!')` → `print(''); print(f'Fertig!')`

## colab_pipeline_v5.ipynb – 2026-03-21
### Änderungen
- VAD-Zelle komplett neu: kein Frame-Extraktion mehr (war fehleranfällig)
- Robust gegen SlidingWindowFeature + ndarray: `np.asarray(getattr(vad_raw, 'data', vad_raw))`
- Embedding auf gesamtem Audio statt Speech-Only-Extraktion
- emb_size dynamisch ermittelt (kein hartcodiertes 512 mehr)

## colab_pipeline_v4.ipynb – 2026-03-21
### Änderungen
- Bugfix: `vad_out` ist numpy array, kein SlidingWindowFeature → kein `.sliding_window`
  Framezeit wird jetzt aus Arraylänge berechnet: `frame_dur = len(audio)/sr/n_frames`

## colab_pipeline_v3.ipynb – 2026-03-21
### Änderungen
- Bugfix: `vad_out.data` ist `memoryview` → `np.asarray(vad_out.data)` vor `.max()`

## colab_pipeline_v2.ipynb – 2026-03-21
### Änderungen
- Schritt 0b: OGG-ZIP automatisch entpacken (Resume: überspringt wenn OGGs schon da)
- VAD+Embeddings-Zelle war in v1 fehlend → jetzt vollständig eingebaut
- Alte/doppelte Zellen (altes API, alter Clustering, alter Whisper-Loop) entfernt
- Vollständig saubere Struktur: 10 Zellen, jede mit Schritt-Header

## colab_pipeline_v1.ipynb – 2026-03-21
### Änderungen
- Alle Code-Zellen mit einheitlichem `# ── Schritt X: Beschreibung ───` Header versehen
- Notebook von `colab_pipeline_v29.ipynb` auf `colab_pipeline_v1.ipynb` umbenannt
  (Notebook-Version unabhängig von PIPELINE_VERSION)

## v3.7 – 2026-03-21
### Änderungen
- PIPELINE_VERSION auf "v29" erhöht (Transkripte von Whisper large-v3-turbo via Colab)
- MIN_RESUME_VERSION bleibt 23 → alle bestehenden Bücher (v28) weiter kompatibel
- Neue Colab-Notebooks: `colab_whisper.ipynb` (Whisper) + `colab_pyannote.ipynb` (Speaker)
- Neue Hilfsskripte: `upload_erde.sh` (OGGs → Drive) + `download_erde.sh` (TXTs ← Drive)

## v3.6 – 2026-03-04
### Änderungen
- FR-Stimmen neu geordnet und erweitert (5 Stimmen statt 4):
  Henri(0,Erzähler) · Eloise(1,Kind) · Charline-BE(2,Kind2) · Remy(3,Mann2) · Vivienne(4,Frau)
  → Kinderstimmen jetzt auf Index 1+2, werden ab K=3 genutzt
  → fr-BE-CharlineNeural als 2. Kinderstimme (jünger als Vivienne)
  → Vivienne auf Index 4 (Fallback für Bücher mit K=5)

## v3.5 – 2026-03-04
### Änderungen
- `cluster_speakers()`: `max_k` auf 7 erhöht (war: `min(num_voices, ...)`)
  → Clustering probiert jetzt K=2..7 statt K=2..num_voices
  → Voice-Zuweisung bleibt sicher: `voices[min(idx, len(voices)-1)]` clampt
    Cluster-Indices die größer als die Stimmen-Anzahl sind

## v3.4 – 2026-03-03
### Änderungen
- Sprecher-Erkennung komplett auf resemblyzer (GE2E Embeddings) umgestellt
  → `_mean_pitch()` und librosa-basiertes Pitch-Clustering entfernt
- `cluster_speakers()` nimmt jetzt `ogg_files: list[Path]` statt Pitch-Dict
  → lädt VoiceEncoder, extrahiert Embeddings, KMeans + Silhouette wie zuvor
- `del encoder; gc.collect()` nach Embedding-Extraktion (RAM freigeben)
- Imports: `librosa`, `warnings` entfernt; `resemblyzer`, `normalize` ergänzt
- Vorteil: kein falsches Pitch-Clustering durch Geräusche/Musik mehr

## v3.3 – 2026-03-03
### Änderungen
- CH-Stimmen um `de-AT-JonasNeural` erweitert → jetzt 3 CH-Stimmen
  Jan(0,CH) · Leni(1,CH) · Jonas(2,AT)
- Hintergrund: Unterwegs CH braucht K=3 laut resemblyzer; Österreichisch ist
  näher am Schweizerdeutschen als Hochdeutsch und liest Berner Dialekt gut
- speakers.json für alle Queue-Bücher gespeichert (resemblyzer GE2E):
  WWW Wald K=3 · Unterwegs K=3 · Erste Zahlen K=2 · Flughafen K=2 · Feuerwehr K=2

## v3.2 – 2026-03-03
### Änderungen
- FR-Stimmen um `fr-FR-EloiseNeural` (weibl. Kinderstimme) erweitert → jetzt 4 Stimmen
  Henri(0) · Vivienne(1) · Remy(2) · Eloise(3)
- Hintergrund: resemblyzer-Analyse ergab K=4 als bestes Clustering für LSW
- LSW speakers.json mit K=4 (resemblyzer GE2E) neu gespeichert
- LSW TTS-Dateien gelöscht → nächster Pipeline-Lauf nutzt 4 Stimmen

## v3.1 – 2026-03-03
### Änderungen
- `_is_noise_transcript()`: erkennt Urheberrechts-Einblendungen (WDR, SWR, NDR, MDR,
  BR, HR, RBB, SR, copyright, ©) bei Texten ≤ 60 Zeichen
- Solche OGGs werden wie Stille behandelt: leere Übersetzung, Original-OGG bleibt
- Hintergrund: Tiptoi-Bücher mit WDR/SWR-Audiomaterial enthalten gesprochene
  Copyright-Einblendungen – diese sollen nicht übersetzt/gesprochen werden
- `import re` hinzugefügt
- Begleitend: `repair_lsw_copyright.py` – einmalige Reparatur von LSW_Uhr_und_Zeit

## v3.0 – 2026-03-03
### Änderungen
- `save_speakers()` / `load_speakers()`: Sprecher-Profil wird nach erster Pitch-Analyse
  als `03_transcripts/{buch}/speakers.json` gespeichert (sprach-unabhängig)
- Beim zweiten Lauf (andere Sprache): speakers.json wird geladen → Pitch-Analyse
  und Clustering werden komplett übersprungen
- `cluster_speakers()` gibt jetzt Tupel `(voice_map, num_speakers, silhouette)` zurück
- `import json` hinzugefügt

## v2.9 – 2026-03-03
### Änderungen
- Bugfix `_find_resume()`: Legacy-Fallback für unverstionierte Dateien (vor v2.6)
  Ohne Fix: Whisper re-transkribierte alles neu weil `_v26.txt` nicht gefunden wurde

## v2.8 – 2026-03-03
### Änderungen
- CH-Modell von `mistral-large-latest` auf `mistral-medium-latest` vereinheitlicht
- FR-Temperatur auf 0.8 gesetzt (CH bleibt 0.3)

## v2.7 – 2026-03-03
### Änderungen
- `tts_one()` fängt jetzt alle Exceptions ab (inkl. `NoAudioReceived` von edge-tts)
  → kein Absturz mehr, Datei wird übersprungen, Pipeline läuft weiter
- Rückgabewert bool: True = Erfolg, False = Fehler (Aufrufer überspringt OGG-Konvertierung)

## v2.6 – 2026-03-03
### Änderungen
- `PIPELINE_VERSION = "v26"` – alle erzeugten Dateinamen enthalten jetzt die Version:
  03_transcripts: `{stem}_v26.txt` | 04_translated: `{stem}_v26.txt`
  05_tts_output: `{stem}_v26.mp3` | 06_output: `{buch}_{sprache}_v26.gme`
- `MIN_RESUME_VERSION = 23` – Resume akzeptiert Dateien ab v2.3 aufwärts
  (Breaking Change v2.3: Whisper-Modell auf small umgestellt)
- `_find_resume()` – sucht neueste kompatible Version einer Datei (v26→v25→...→v23)
  Resume funktioniert über Versionen hinweg, veraltete Dateien (< v23) werden ignoriert
- 02_unpacked bleibt unverändert (tttool-kontrolliert)

## v2.5 – 2026-03-03
### Änderungen
- Ordner umbenannt (pipeline.py + alle Skripte + Dateisystem):
  input→01_input, unpacked→02_unpacked, transcripts→03_transcripts,
  translated→04_translated, tts_output→05_tts_output, output→06_output
- readme.txt komplett überarbeitet: alle Parameter dokumentiert,
  neue Ordnerstruktur, Stimmenübersicht FR+CH, Resume-Hinweis

## v2.4 – 2026-03-03
### Änderungen
- ffmpeg-Fehler abfangen: bei CalledProcessError wird die Datei übersprungen
  statt die Pipeline abzubrechen (vorher: exit status 183 bei leerer MP3)
- Leere MP3-Dateien (0 Bytes) von edge-tts werden erkannt, gelöscht und
  übersprungen – nächster Run versucht TTS erneut

## v2.3 – 2026-03-02
### Änderungen
- Standard-Whisper-Modell zurück auf `small` (Modellvergleich zeigt klare Qualitätsvorteile
  gegenüber `base`: seltener falsche Sprache/Englisch, kohärentere Ausgaben)
- RAM-Optimierungen aus v2.2 bleiben: `cpu_threads=2`, `num_workers=1`, `gc.collect()`

## v2.2 – 2026-03-02
### Änderungen
- Standard-Whisper-Modell von `small` (~480 MB RAM) auf `base` (~145 MB RAM) gesenkt
- `cpu_threads=2` + `num_workers=1` beim WhisperModel-Aufruf gesetzt →
  verhindert unbegrenzte Thread-Allokation und reduziert RAM-Spitzen
- Hintergrund: OOM-Killer hat Pipeline-Prozess bei ~500–570 MB anon-rss abgebrochen

## v2.3 – 2026-03-02
### Änderungen
- Whisper-Modell nach Pass 2 explizit aus RAM entladen (`del whisper + gc.collect()`) – verhindert OOM
- `gc` importiert

## v2.2 – 2026-03-01
### Änderungen
- Batch-Übersetzung: `translate_batch()` – 10 Texte pro Mistral-Call statt 1 (bis zu 10x weniger API-Calls)
- 4-Pass-Architektur: Pitch → Whisper → Batch-Mistral → TTS+OGG
- Fallback auf Einzelaufruf wenn Batch-Marker fehlt
- Rate-Limit-Logging pro Batch mit Batch-Nummer

## v2.1 – 2026-03-01
### Änderungen
- Pass-Struktur korrigiert: Pass 1 = nur Pitch (schnell, Batch) → Clustering → Pass 2 = Whisper + Mistral + TTS + OGG pro Datei
- Mistral läuft jetzt im selben Pass wie TTS (kein Split mehr zwischen API und Ausgabe)
- Pitch-Fortschritt alle 100 Dateien

## v2.0 – 2026-03-01
### Änderungen
- Zwei-Pass-Architektur: Pass 1 (Pitch + Whisper + Mistral pro Datei) → Clustering → Pass 2 (TTS + OGG pro Datei)
- `pyin` → `yin` (librosa): 10x schneller, keine Batch-Blockierung mehr
- Sprecher-Analyse inline im Per-Datei-Loop (Pass 1), kein Vorlauf über alle Dateien
- Fortschrittsausgabe pro Datei in beiden Passes mit `flush=True`
- `analyze_speakers()` → `cluster_speakers()` umbenannt (nur noch Clustering, kein IO)
- `--whisper-model` Auswahl um `large-v3-turbo` erweitert

## v1.9 – 2026-03-01
### Änderungen
- Default Whisper-Modell auf `small` geändert (war: `base`) – basierend auf Modell-Vergleich (base halluziniert Sprachmix, small liefert saubere Transkripte)

## v1.8 – 2026-03-01
### Änderungen
- Rate Limit: 3 Versuche mit Wartezeiten 60s / 90s / 180s (war: 1 Retry à 60s)

## v1.7 – 2026-03-01
### Änderungen
- Rate Limit Handling vereinfacht: 1 Retry nach fest 60s (war: 5 Versuche mit 60/120/180/240/300s)

## v1.6 – 2026-03-01
### Änderungen
- Mistral Temperatur für CH auf 0.3 festgesetzt (konsistenterer Dialekt-Output)
- FR nutzt weiterhin Mistral-Standard-Temperatur

## v1.5 – 2026-03-01
### Änderungen
- Mehrsprachigkeit: `--language fr/ch` Parameter, LANG_CONFIG pro Sprache
- Schweizerdeutsch (Berner Dialekt): Stimme `de-CH-LeniNeural` + `de-CH-JanNeural`
- Automatische Sprecher-Erkennung via Pitch-Analyse (librosa) + K-Means-Clustering
  mit Silhouette-Score zur automatischen Bestimmung der Sprecher-Anzahl (K=1..4)
- Mehrere Stimmen pro Sprache (voices-Liste, nach Pitch sortiert zugewiesen)
- Geräusch-Erkennung: leeres Whisper-Ergebnis → Original-OGG wird übernommen
- Pro-Sprache Unterordner: `translated/{buch}/{lang}/`, `tts_output/{buch}/{lang}/`
- Mistral-Modell pro Sprache: `mistral-medium-latest` (FR), `mistral-large-latest` (CH)
- CH-Prompt auf Berner Dialekt + phonetisch für TTS optimiert
- `--voice` bleibt als manueller Override (deaktiviert Sprecher-Analyse)
- Schritte neu nummeriert (5 Schritte statt 4)
- requirements.txt: librosa, scikit-learn ergänzt

## v1.4 – 2026-03-01
### Änderungen
- Kompletter Umbau: pro OGG-Datei wird der ganze Weg gemacht
  (Transkript → Übersetzung → MP3 → OGG), bevor die nächste Datei beginnt
- Whisper-Modell und Mistral-Client werden einmalig geladen, dann pro Datei genutzt
- Einzel-Funktionen: `transcribe_one`, `translate_one`, `tts_one`, `convert_to_ogg`
- Rate Limit Wartezeit auf 60s × Versuch erhöht (war 30s)
- Default-Stimme auf `fr-FR-VivienneMultilingualNeural` gesetzt (war DeniseNeural)
- Default-Whisper auf `base` gesetzt (war small)

## v1.3 – 2026-03-01
### Änderungen
- Unterordner pro Buch: `transcripts/{buch}/`, `translated/{buch}/`, `tts_output/{buch}/`
- `translate_all()` erhält `translated_dir` als Parameter (statt globale Variable)
- Doppelte Zuweisung von `tts_book_dir` in `run()` entfernt

## v1.2 – 2026-03-01
### Änderungen
- Mistral Rate Limit Handling: automatischer Retry mit Wartezeit (30s, 60s, 90s...)
- 0.5s Pause zwischen jeder Mistral API-Anfrage
- Resume-Funktion: bereits gespeicherte Übersetzungen aus `translated/` werden
  beim Neustart übersprungen (kein doppeltes Übersetzen nach Abbruch)
- TTS Resume: bereits vorhandene MP3-Dateien werden übersprungen
- YAML-Bereinigung: vorhandene YAML wird vor tttool export automatisch gelöscht

## v1.1 – 2026-03-01
### Änderungen
- tttool-Befehle korrigiert: `unpack` → `export` + `media`
  (tttool 1.11 kennt keinen `unpack`-Befehl)
- `--limit N` Option hinzugefügt (nur die ersten N Dateien verarbeiten,
  für Testläufe)
- `--voice` und `--whisper-model` Parameter dokumentiert

## v1.0 – 2026-03-01
### Initiale Version
- Grundstruktur: 6-Schritte-Pipeline (unpack → STT → translate → TTS → convert → repack)
- faster-whisper für DE-Transkription
- Mistral API für DE→FR Übersetzung
- edge-tts für französische Sprachausgabe
- ffmpeg für OGG-Konvertierung (Mono, 22050 Hz)
- tttool für GME-Verarbeitung

## prepare_upload.sh v2 – 2026-03-22
### Änderungen
- OGGs werden jetzt immer frisch aus der Original-GME extrahiert (`tttool media` in tmpdir)
- Vorher: ZIP von `02_unpacked/{BOOK}/media/` → konnte übersetzte OGGs enthalten wenn Pipeline schon gelaufen
- Neu: Suche nach GME in `01_input/` (exakter Name + Fuzzy-Fallback)
