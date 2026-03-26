# gme_patch.py – Tiptoi GME Audio Patcher

**[English](#english)** | **[Deutsch](#deutsch)** | **[Français](#français)** | **[Español](#español)**

---

<a id="english"></a>

## English

### Table of Contents

- [What is this?](#what-is-this)
- [The Problem](#the-problem)
- [The Solution](#the-solution)
- [How It Works (Technical Details)](#how-it-works-technical-details)
- [Installation](#installation)
- [Usage](#usage-en)
- [Pipeline Integration](#pipeline-integration)
- [Design Decisions](#design-decisions)
- [File Format Reference](#file-format-reference)
- [Credits](#credits)

---

### What is this?

`gme_patch.py` replaces audio files inside Ravensburger Tiptoi `.gme` files using a **direct binary patch**. Unlike the standard workflow with `tttool export` + `tttool assemble`, this tool preserves all game logic, scripts, and unknown binary segments bit-for-bit.

This means interactive features like quizzes, puzzles, and mini-games **continue to work** after replacing the audio.

The primary use case is translating Tiptoi books from German into other languages (e.g. French, Swiss German) while keeping all interactive features intact.

---

### The Problem

The standard Tiptoi tool (`tttool`) uses a YAML-based round-trip to modify GME files:

```
Original GME → tttool export → YAML + Audio → tttool assemble → New GME
```

This round-trip **loses 8 unknown binary segments** (~4,500 bytes) containing game logic and firmware data. After reassembly, interactive games (quizzes, puzzles) no longer work — the pen may loop, crash, or play the wrong audio.

This issue was confirmed by `tttool` author Joachim Breitner on the tip-toi-reveng mailing list (2026-02-26), who pointed to `libtiptoi.c` as a reference implementation that patches the binary directly.

---

### The Solution

`gme_patch.py` patches the GME binary directly — no YAML export, no round-trip. Everything that is not audio data is preserved bit-for-bit.

The tool operates in two modes:

**Safe Mode** (automatic when no post-audio data exists):

```
Original GME                         Output GME
┌──────────────────┐                 ┌──────────────────┐
│ Header + Scripts │ ──────────────► │ Header + Scripts │  (bit-for-bit copy)
│ Audio Table      │                 │ Audio Table      │  (new offsets + lengths)
│ Audio Files      │  + New OGGs ──► │ Audio Files      │  (replaced + XOR encrypted)
│ Checksum         │                 │ Checksum         │  (recalculated)
└──────────────────┘                 └──────────────────┘
```

**Experimental Mode** (when post-audio data like game binaries exists):

```
Original GME                         Output GME
┌──────────────────┐                 ┌──────────────────┐
│ Header + Scripts │ ──────────────► │ Header + Scripts │  (targeted pointer fix)
│ Audio Table      │                 │ Audio Table      │  (new offsets + lengths)
│ Audio Files      │  + New OGGs ──► │ Audio Files      │  (replaced + XOR encrypted)
│ Game Binaries    │ ──────────────► │ Game Binaries    │  (bit-for-bit copy)
│ Checksum         │                 │ Checksum         │  (recalculated)
└──────────────────┘                 └──────────────────┘
```

In experimental mode, the output filename automatically receives an `_experimentell` suffix so you can clearly tell which files are from the safe path and which are experimental.

---

### How It Works (Technical Details)

#### Safe Mode (modeled after libtiptoi.c)

The safe mode follows the exact same algorithm as Michael Wolf's `libtiptoi.c` reference implementation:

1. **Copy everything before the audio table** — header, scripts, OID code tables, jump tables — bit-for-bit, untouched.
2. **Write a new audio table** — N entries of `(offset: uint32, length: uint32)`. Offsets are recalculated based on the new file sizes.
3. **Write audio data** — each file is read from disk (or kept from the original GME), then XOR-encrypted and appended sequentially.
4. **Append checksum** — additive sum of all preceding bytes, stored as 4 bytes little-endian.

Key behaviors matching libtiptoi.c:
- **No deduplication**: if two table entries point to the same original audio, each gets its own copy in the output. This is safer than deduplicating and avoids complications with offset references.
- **Abort on post-audio data**: libtiptoi.c refuses to patch files that have data after the audio block. Our safe mode does the same — it only activates when `filesize == last_audio_end + 4`.

#### Experimental Mode (extension beyond libtiptoi.c)

When post-audio data exists (game binaries, single binaries, special symbols), the tool:

1. Performs all safe-mode steps (1–3).
2. **Appends post-audio data** bit-for-bit after the new audio block.
3. **Fixes only known header pointers** at positions `0x005C` (binaries table), `0x0064` (single binaries table), and `0x0068` (special symbols table). These three offsets are well-documented in the GME format specification.
4. **Fixes binary table internals** — each binary table has a known structure (`count + count × offset`), so internal pointers are shifted by the same delta.
5. **No blind scanning** — previous versions scanned every 4-byte position looking for values that "might be pointers." This corrupted script commands, timer values, and OID codes, causing loops and crashes. v4 eliminates this entirely.

#### XOR Encryption

Tiptoi GME files use a simple XOR cipher for audio data. The key is derived from the first audio file's magic bytes (`OggS` or `RIFF`). The XOR rules (from the format specification):

- Bytes `0x00`, `0xFF`, `key`, `key ^ 0xFF` are left unchanged
- All other bytes are XOR'd with the key

The codec is symmetric — applying it twice returns the original data.

---

### Installation

#### Requirements

- **Python 3.10+** (uses type hints with `|`, `match` syntax)
- No external dependencies — stdlib only (`struct`, `re`, `argparse`, `pathlib`)

#### requirements.txt

```
# gme_patch.py has no external dependencies.
# Python 3.10+ with stdlib is sufficient.
```

#### Optional (for the full translation pipeline)

If you use `gme_patch.py` as part of a Tiptoi translation pipeline, the pipeline itself requires additional tools. See the pipeline documentation for details. The patcher itself is standalone.

#### Setup

```bash
# Clone the repository
git clone https://github.com/YOUR_USER/tiptoi-gme-patcher.git
cd tiptoi-gme-patcher

# No install needed — run directly
python gme_patch.py --help
```

---

<a id="usage-en"></a>

### Usage

The CLI is designed to match `tttool`'s command names, making it easy to swap into existing workflows.

#### Extract audio files

```bash
python gme_patch.py media -d output_dir/ input.gme
```

Extracts all audio files from a GME, XOR-decrypted, with tttool-compatible filenames (`BookName_0.ogg`, `BookName_1.ogg`, ...). Duplicate entries (multiple table indices pointing to the same audio) are detected and written as separate files.

#### Replace audio files

```bash
# Standard (safe mode if no post-audio data, asks for confirmation otherwise):
python gme_patch.py assemble original.gme media_dir/ output.gme

# Skip confirmation for experimental mode:
python gme_patch.py assemble original.gme media_dir/ output.gme --force
```

Files in `media_dir/` are matched to audio table indices by the last number in the filename:

```
media_dir/
  Feuerwehr_0.ogg      → replaces index 0
  Feuerwehr_1.ogg      → replaces index 1
  Feuerwehr_42.ogg     → replaces index 42
  Feuerwehr_42_v32.ogg → replaces index 42 (pipeline version suffix ignored)
```

Indices without a replacement file keep their original audio from the GME.

#### Show file information

```bash
python gme_patch.py info input.gme
```

Displays header data, audio table details, post-audio data presence, known pointer locations, duplicate count, and checksum verification.

#### Help

```bash
python gme_patch.py --help
python gme_patch.py assemble --help
python gme_patch.py media --help
python gme_patch.py info --help
```

---

### Pipeline Integration

`patch_gme()` can be imported and called directly from Python:

```python
from pathlib import Path
from gme_patch import patch_gme

result = patch_gme(
    original_gme=Path("input.gme"),
    media_dir=Path("tts_output/"),
    output_gme=Path("output.gme"),
    force=True,  # skip interactive confirmation
)

# result = {
#     "mode": "safe" | "experimental" | "aborted",
#     "output": Path,       # actual output path (may include _experimentell)
#     "entries": int,       # total audio table entries
#     "replaced": int,      # entries with new audio
#     "kept": int,          # entries kept from original
# }
```

Example integration in a translation pipeline:

```python
result = patch_gme(gme_path, tts_dir, out_gme, force=True)
if result["mode"] == "aborted":
    print("Aborted — no GME produced.")
else:
    out_gme = result["output"]
    label = " (experimental)" if result["mode"] == "experimental" else ""
    print(f"Done! Output{label}: {out_gme}")
```

---

### Design Decisions

| Decision | Rationale |
|----------|-----------|
| **No deduplication** | libtiptoi.c writes each table entry as its own audio copy. Deduplicating saves space but introduces risk if some firmware behavior depends on sequential layout. We follow the proven approach. |
| **No blind pointer scanning** | v3 scanned every 4-byte position for values that looked like pointers. This corrupted non-pointer data (script commands, timer values, OID codes) and caused pen crashes. v4 only touches 3 known, documented header offsets. |
| **Two explicit modes** | Rather than silently attempting experimental patches, the tool clearly separates safe (proven) from experimental (best-effort) and marks output files accordingly. |
| **tttool-compatible CLI** | Using the same command names (`media`, `assemble`, `info`) makes it a drop-in replacement in existing scripts. Only `assemble` differs semantically (binary patch vs. YAML round-trip). |
| **No external dependencies** | The patcher uses only Python stdlib, making it easy to install and use on any system with Python 3.10+. |
| **Filename convention** | The `_experimentell` suffix in output filenames ensures you never accidentally deploy an untested experimental patch to a pen. |

---

### File Format Reference

Brief overview of the Tiptoi GME format (see [GME-Format.md](https://github.com/entropia/tip-toi-reveng/blob/master/GME-Format.md) for full documentation):

| Offset | Content |
|--------|---------|
| `0x0000` | Main table offset (scripts, OID codes) |
| `0x0004` | Audio file table offset |
| `0x0014` | Book code |
| `0x005C` | Binaries table offset (games) |
| `0x0060` | Additional audio table offset |
| `0x0064` | Single binaries table offset |
| `0x0068` | Special symbols table offset |

Audio table entries: `N × (offset: uint32, length: uint32)`, where `N = (first_audio_offset - table_offset) / 8`.

Checksum: last 4 bytes of file, additive sum of all preceding bytes (little-endian uint32).

---

### Credits

- GME format reverse-engineered by the [tip-toi-reveng](https://github.com/entropia/tip-toi-reveng) community
- `libtiptoi.c` by Michael Wolf (MIT License) — the reference implementation this tool is modeled after
- `tttool` by Joachim Breitner — the standard Tiptoi tool for YAML-based workflows

---
---

<a id="deutsch"></a>

## Deutsch

### Inhaltsverzeichnis

- [Was ist das?](#was-ist-das)
- [Das Problem](#das-problem-de)
- [Die Lösung](#die-lösung)
- [Funktionsweise (Technische Details)](#funktionsweise-technische-details)
- [Installation](#installation-de)
- [Verwendung](#verwendung)
- [Pipeline-Integration](#pipeline-integration-de)
- [Design-Entscheidungen](#design-entscheidungen)
- [Dateiformat-Referenz](#dateiformat-referenz)
- [Credits](#credits-de)

---

### Was ist das?

`gme_patch.py` ersetzt Audio-Dateien in Ravensburger Tiptoi `.gme`-Dateien per **direktem Binary-Patch**. Im Gegensatz zum Standard-Workflow mit `tttool export` + `tttool assemble` bleiben Spiele-Logik, Scripts und alle unbekannten Binär-Segmente bitgenau erhalten.

Interaktive Funktionen wie Quiz, Puzzle und Minispiele **funktionieren weiterhin** nach dem Austausch der Audio-Dateien.

Hauptanwendungsfall: Tiptoi-Bücher von Deutsch in andere Sprachen übersetzen (z.B. Französisch, Schweizerdeutsch) und dabei alle interaktiven Features beibehalten.

---

<a id="das-problem-de"></a>

### Das Problem

Das Standard-Tool (`tttool`) nutzt einen YAML-Roundtrip:

```
Original-GME → tttool export → YAML + Audio → tttool assemble → Neue GME
```

Dieser Roundtrip **verliert 8 unbekannte Binär-Segmente** (~4.500 Bytes) mit Spiele-Logik und Firmware-Daten. Nach dem Zusammenbau funktionieren interaktive Spiele nicht mehr — der Stift loopt, stürzt ab oder spielt falsches Audio.

Dieses Problem wurde von `tttool`-Autor Joachim Breitner auf der [tip-toi-reveng Mailingliste](https://github.com/entropia/tip-toi-reveng) bestätigt (26.02.2026). Er verwies auf `libtiptoi.c` als Referenz-Implementierung für direktes Binary-Patching.

---

### Die Lösung

`gme_patch.py` patcht die GME-Datei direkt — kein YAML-Export, kein Roundtrip. Alles was nicht Audio ist, bleibt bitgenau erhalten.

**Safe-Modus** (automatisch wenn keine Post-Audio-Daten vorhanden):

```
Original-GME                          Ausgabe-GME
┌──────────────────┐                  ┌──────────────────┐
│ Header + Scripts │ ───────────────► │ Header + Scripts │  (bitgenaue Kopie)
│ Audio-Tabelle    │                  │ Audio-Tabelle    │  (neue Offsets + Längen)
│ Audio-Dateien    │  + Neue OGGs ──► │ Audio-Dateien    │  (ersetzt + XOR)
│ Prüfsumme        │                  │ Prüfsumme        │  (neu berechnet)
└──────────────────┘                  └──────────────────┘
```

**Experimenteller Modus** (wenn Post-Audio-Daten wie Spiele-Binaries existieren):

```
Original-GME                          Ausgabe-GME
┌──────────────────┐                  ┌──────────────────┐
│ Header + Scripts │ ───────────────► │ Header + Scripts │  (gezielte Pointer-Fixes)
│ Audio-Tabelle    │                  │ Audio-Tabelle    │  (neue Offsets + Längen)
│ Audio-Dateien    │  + Neue OGGs ──► │ Audio-Dateien    │  (ersetzt + XOR)
│ Spiele-Binaries  │ ───────────────► │ Spiele-Binaries  │  (bitgenaue Kopie)
│ Prüfsumme        │                  │ Prüfsumme        │  (neu berechnet)
└──────────────────┘                  └──────────────────┘
```

Im experimentellen Modus erhält die Ausgabedatei automatisch den Zusatz `_experimentell` im Dateinamen, sodass klar erkennbar ist, welche Dateien sicher gepatcht und welche experimentell sind.

---

### Funktionsweise (Technische Details)

#### Safe-Modus (nach Vorbild libtiptoi.c)

Der Safe-Modus folgt exakt dem Algorithmus von Michael Wolfs `libtiptoi.c` Referenz-Implementierung:

1. **Alles vor der Audio-Tabelle kopieren** — Header, Scripts, OID-Code-Tabellen, Jump-Tabellen — bitgenau, unverändert.
2. **Neue Audio-Tabelle schreiben** — N Einträge à `(Offset: uint32, Länge: uint32)`. Offsets werden basierend auf den neuen Dateigrößen berechnet.
3. **Audio-Daten schreiben** — jede Datei wird gelesen (oder aus dem Original übernommen), XOR-verschlüsselt und sequenziell angehängt.
4. **Prüfsumme anhängen** — Additive Summe aller vorherigen Bytes, 4 Bytes Little-Endian.

Wichtige Verhaltensweisen analog zu libtiptoi.c:
- **Kein Duplikate-Dedup**: Wenn zwei Tabelleneinträge auf dasselbe Original-Audio zeigen, bekommt jeder seine eigene Kopie in der Ausgabe. Das ist sicherer als Deduplizierung und vermeidet Probleme mit Offset-Referenzen.
- **Abbruch bei Post-Audio-Daten**: libtiptoi.c verweigert den Patch wenn nach dem Audio-Block Daten folgen. Unser Safe-Modus macht dasselbe — er aktiviert sich nur wenn `filesize == last_audio_end + 4`.

#### Experimenteller Modus (Erweiterung über libtiptoi.c hinaus)

Wenn Post-Audio-Daten existieren (Spiele-Binaries, Single-Binaries, Special Symbols):

1. Alle Safe-Modus-Schritte (1–3) durchführen.
2. **Post-Audio-Daten bitgenau anhängen** nach dem neuen Audio-Block.
3. **Nur bekannte Header-Pointer korrigieren** an den Positionen `0x005C` (Binaries-Tabelle), `0x0064` (Single-Binaries-Tabelle) und `0x0068` (Special-Symbols-Tabelle). Diese drei Offsets sind in der GME-Format-Spezifikation gut dokumentiert.
4. **Binary-Table-Interna verschieben** — jede Binary-Tabelle hat ein bekanntes Format (`count + count × offset`), sodass interne Pointer um denselben Delta verschoben werden.
5. **Kein Blind-Scan** — frühere Versionen scannten jede 4-Byte-Position auf Werte die „Pointer sein könnten". Das korrumpierte Script-Befehle, Timer-Werte und OID-Codes und verursachte Loops und Abstürze. v4 eliminiert dies vollständig.

#### XOR-Verschlüsselung

Tiptoi-GME-Dateien nutzen eine einfache XOR-Verschlüsselung für Audio-Daten. Der Schlüssel wird aus den Magic-Bytes der ersten Audio-Datei abgeleitet (`OggS` oder `RIFF`). Die XOR-Regeln (aus der Format-Spezifikation):

- Bytes `0x00`, `0xFF`, `key`, `key ^ 0xFF` bleiben unverändert
- Alle anderen Bytes werden mit dem Schlüssel XOR-verknüpft

Der Codec ist symmetrisch — zweimaliges Anwenden ergibt die Original-Daten.

---

<a id="installation-de"></a>

### Installation

#### Voraussetzungen

- **Python 3.10+** (nutzt Type-Hints mit `|`)
- Keine externen Abhängigkeiten — nur Python-Standardbibliothek (`struct`, `re`, `argparse`, `pathlib`)

#### requirements.txt

```
# gme_patch.py hat keine externen Abhängigkeiten.
# Python 3.10+ mit Standardbibliothek genügt.
```

#### Optional (für die vollständige Übersetzungs-Pipeline)

Wenn `gme_patch.py` als Teil einer Tiptoi-Übersetzungs-Pipeline verwendet wird, benötigt die Pipeline selbst zusätzliche Tools. Siehe Pipeline-Dokumentation für Details. Der Patcher selbst ist standalone.

#### Setup

```bash
# Repository klonen
git clone https://github.com/YOUR_USER/tiptoi-gme-patcher.git
cd tiptoi-gme-patcher

# Keine Installation nötig — direkt starten
python gme_patch.py --help
```

---

### Verwendung

Die CLI-Befehle entsprechen `tttool`, sodass bestehende Workflows einfach umgestellt werden können.

#### Audio extrahieren

```bash
python gme_patch.py media -d ausgabe_ordner/ eingabe.gme
```

Extrahiert alle Audio-Dateien aus einer GME, XOR-entschlüsselt, mit tttool-kompatiblen Dateinamen (`Buchname_0.ogg`, `Buchname_1.ogg`, ...). Duplikate (mehrere Tabellenindices zeigen auf dasselbe Audio) werden erkannt und als separate Dateien geschrieben.

#### Audio ersetzen

```bash
# Standard (Safe-Modus wenn möglich, sonst Rückfrage):
python gme_patch.py assemble original.gme media_ordner/ ausgabe.gme

# Ohne Rückfrage (experimenteller Modus automatisch):
python gme_patch.py assemble original.gme media_ordner/ ausgabe.gme --force
```

Dateinamen in `media_ordner/` werden per letzter Zahl im Dateinamen dem Audio-Tabellenindex zugeordnet:

```
media_ordner/
  Feuerwehr_0.ogg      → ersetzt Index 0
  Feuerwehr_1.ogg      → ersetzt Index 1
  Feuerwehr_42.ogg     → ersetzt Index 42
  Feuerwehr_42_v32.ogg → ersetzt Index 42 (Pipeline-Versionssuffix wird ignoriert)
```

Indices ohne Ersatz-Datei behalten ihr Original-Audio aus der GME.

#### Info anzeigen

```bash
python gme_patch.py info eingabe.gme
```

Zeigt Header-Daten, Audio-Tabellen-Details, Post-Audio-Daten-Präsenz, bekannte Pointer-Positionen, Duplikat-Anzahl und Prüfsummen-Verifikation.

#### Hilfe

```bash
python gme_patch.py --help
python gme_patch.py assemble --help
python gme_patch.py media --help
python gme_patch.py info --help
```

---

<a id="pipeline-integration-de"></a>

### Pipeline-Integration

`patch_gme()` kann direkt aus Python importiert und aufgerufen werden:

```python
from pathlib import Path
from gme_patch import patch_gme

result = patch_gme(
    original_gme=Path("eingabe.gme"),
    media_dir=Path("tts_output/"),
    output_gme=Path("ausgabe.gme"),
    force=True,  # Interaktive Bestätigung überspringen
)

# result = {
#     "mode": "safe" | "experimental" | "aborted",
#     "output": Path,       # tatsächlicher Ausgabepfad (ggf. mit _experimentell)
#     "entries": int,       # Gesamt-Einträge in Audio-Tabelle
#     "replaced": int,      # ersetzte Einträge
#     "kept": int,          # beibehaltene Einträge
# }
```

Beispiel-Integration in eine Übersetzungs-Pipeline:

```python
result = patch_gme(gme_path, tts_dir, out_gme, force=True)
if result["mode"] == "aborted":
    print("Abgebrochen — keine GME erzeugt.")
else:
    out_gme = result["output"]
    label = " (experimentell)" if result["mode"] == "experimental" else ""
    print(f"Fertig! Ausgabe{label}: {out_gme}")
```

---

### Design-Entscheidungen

| Entscheidung | Begründung |
|---|---|
| **Kein Duplikate-Dedup** | libtiptoi.c schreibt jeden Tabellenindex als eigene Audio-Kopie. Deduplizierung spart Platz, birgt aber Risiken wenn Firmware-Verhalten von sequenziellem Layout abhängt. Wir folgen dem bewährten Ansatz. |
| **Kein Blind-Scan** | v3 scannte alle 4-Byte-Positionen nach Werten die „Pointer sein könnten". Das korrumpierte Nicht-Pointer-Daten (Script-Befehle, Timer-Werte, OID-Codes) und verursachte Stift-Abstürze. v4 fasst nur 3 bekannte, dokumentierte Header-Offsets an. |
| **Zwei explizite Modi** | Statt still experimentelle Patches zu versuchen, trennt das Tool klar Safe (bewährt) von Experimentell (Best-Effort) und markiert Ausgabedateien entsprechend. |
| **tttool-kompatible CLI** | Gleiche Befehlsnamen (`media`, `assemble`, `info`) → Drop-in-Ersatz in bestehenden Scripts. Nur `assemble` weicht semantisch ab (Binary-Patch statt YAML-Roundtrip). |
| **Keine externen Abhängigkeiten** | Nur Python-Stdlib → keine Installation nötig, läuft überall mit Python 3.10+. |
| **Dateinamen-Konvention** | Der `_experimentell`-Zusatz in Ausgabedateien stellt sicher, dass nie versehentlich ein ungetesteter experimenteller Patch auf einen Stift übertragen wird. |

---

### Dateiformat-Referenz

Kurzübersicht des Tiptoi-GME-Formats (vollständige Dokumentation: [GME-Format.md](https://github.com/entropia/tip-toi-reveng/blob/master/GME-Format.md)):

| Offset | Inhalt |
|--------|--------|
| `0x0000` | Main-Table-Offset (Scripts, OID-Codes) |
| `0x0004` | Audio-Tabellen-Offset |
| `0x0014` | Buch-Code |
| `0x005C` | Binaries-Tabellen-Offset (Spiele) |
| `0x0060` | Zusatz-Audio-Tabellen-Offset |
| `0x0064` | Single-Binaries-Tabellen-Offset |
| `0x0068` | Special-Symbols-Tabellen-Offset |

Audio-Tabelleneinträge: `N × (Offset: uint32, Länge: uint32)`, wobei `N = (erster_Audio_Offset - Tabellen_Offset) / 8`.

Prüfsumme: letzte 4 Bytes der Datei, additive Summe aller vorherigen Bytes (Little-Endian uint32).

---

<a id="credits-de"></a>

### Credits

- GME-Format reverse-engineered von der [tip-toi-reveng](https://github.com/entropia/tip-toi-reveng)-Community
- `libtiptoi.c` von Michael Wolf (MIT License) — Referenz-Implementierung, nach deren Vorbild dieses Tool modelliert ist
- `tttool` von Joachim Breitner — Standard-Tool für YAML-basierte Workflows

---
---

<a id="français"></a>

## Français

### Table des matières

- [Qu'est-ce que c'est ?](#quest-ce-que-cest)
- [Le problème](#le-problème)
- [La solution](#la-solution-fr)
- [Fonctionnement technique](#fonctionnement-technique)
- [Installation](#installation-fr)
- [Utilisation](#utilisation)
- [Intégration pipeline](#intégration-pipeline)
- [Choix de conception](#choix-de-conception)
- [Référence du format](#référence-du-format)
- [Crédits](#crédits-fr)

---

### Qu'est-ce que c'est ?

`gme_patch.py` remplace les fichiers audio dans les fichiers `.gme` Ravensburger Tiptoi par un **patch binaire direct**. Contrairement au workflow standard avec `tttool export` + `tttool assemble`, cet outil préserve toute la logique de jeu, les scripts et les segments binaires inconnus bit à bit.

Les fonctionnalités interactives comme les quiz, puzzles et mini-jeux **continuent de fonctionner** après le remplacement de l'audio.

Cas d'utilisation principal : traduire les livres Tiptoi de l'allemand vers d'autres langues (p. ex. français, suisse allemand) tout en conservant toutes les fonctionnalités interactives.

---

### Le problème

L'outil standard (`tttool`) utilise un aller-retour YAML :

```
GME original → tttool export → YAML + Audio → tttool assemble → Nouveau GME
```

Cet aller-retour **perd 8 segments binaires inconnus** (~4 500 octets) contenant la logique de jeu et des données firmware. Après réassemblage, les jeux interactifs ne fonctionnent plus — le stylo peut boucler, planter ou jouer le mauvais audio.

Ce problème a été confirmé par l'auteur de `tttool`, Joachim Breitner, sur la liste de diffusion [tip-toi-reveng](https://github.com/entropia/tip-toi-reveng) (26/02/2026), qui a renvoyé vers `libtiptoi.c` comme implémentation de référence pour le patch binaire direct.

---

<a id="la-solution-fr"></a>

### La solution

`gme_patch.py` patche le binaire directement — pas d'export YAML, pas d'aller-retour. Tout ce qui n'est pas audio reste identique bit à bit.

**Mode sûr** (automatique quand il n'y a pas de données post-audio) :

Construction identique à `libtiptoi.c` : Header → Table → Audio → Checksum.

**Mode expérimental** (quand des données post-audio comme les binaires de jeu existent) :

Confirmation interactive avant le patch (ou `--force`). Les données post-audio sont ajoutées bit à bit, seuls 3 pointeurs d'en-tête connus sont corrigés. Pas de scan aveugle. Le fichier de sortie reçoit le suffixe `_experimentell`.

---

### Fonctionnement technique

#### Mode sûr (basé sur libtiptoi.c)

1. **Copier tout avant la table audio** — en-tête, scripts, tables OID, tables de saut — bit à bit, sans modification.
2. **Écrire une nouvelle table audio** — N entrées de `(offset: uint32, longueur: uint32)`. Les offsets sont recalculés selon les nouvelles tailles de fichiers.
3. **Écrire les données audio** — chaque fichier est lu (ou conservé de l'original), chiffré XOR et ajouté séquentiellement.
4. **Ajouter la somme de contrôle** — somme additive de tous les octets précédents, 4 octets little-endian.

Pas de déduplication : chaque index de table reçoit sa propre copie audio (comme libtiptoi.c).

#### Mode expérimental (extension au-delà de libtiptoi.c)

En plus des étapes du mode sûr :

1. **Ajouter les données post-audio** bit à bit après le nouveau bloc audio.
2. **Corriger uniquement les pointeurs d'en-tête connus** aux positions `0x005C` (table de binaires), `0x0064` (table de binaires individuels) et `0x0068` (table de symboles spéciaux).
3. **Corriger les structures internes des tables binaires** — chaque table a un format connu (`count + count × offset`).
4. **Pas de scan aveugle** — les versions précédentes scannaient chaque position de 4 octets, corrompant les commandes de script, valeurs de timer et codes OID → crashs. v4 élimine cela entièrement.

#### Chiffrement XOR

Tiptoi chiffre l'audio avec un XOR simple. La clé est dérivée des octets magiques du premier fichier audio (`OggS` ou `RIFF`). Règles : `0x00`, `0xFF`, `key`, `key^0xFF` restent inchangés ; tous les autres octets sont XOR avec la clé. Le codec est symétrique.

---

<a id="installation-fr"></a>

### Installation

#### Prérequis

- **Python 3.10+** (utilise les type hints avec `|`)
- Aucune dépendance externe — bibliothèque standard uniquement (`struct`, `re`, `argparse`, `pathlib`)

#### requirements.txt

```
# gme_patch.py n'a aucune dépendance externe.
# Python 3.10+ avec la bibliothèque standard suffit.
```

#### Mise en place

```bash
git clone https://github.com/YOUR_USER/tiptoi-gme-patcher.git
cd tiptoi-gme-patcher
python gme_patch.py --help
```

---

### Utilisation

Les commandes CLI correspondent à celles de `tttool` pour faciliter l'intégration dans les workflows existants.

#### Extraire l'audio

```bash
python gme_patch.py media -d dossier_sortie/ fichier.gme
```

Extrait tous les fichiers audio d'un GME, déchiffrés XOR, avec des noms de fichiers compatibles tttool (`NomLivre_0.ogg`, `NomLivre_1.ogg`, ...).

#### Remplacer l'audio

```bash
# Standard (mode sûr si possible, sinon confirmation) :
python gme_patch.py assemble original.gme dossier_media/ sortie.gme

# Sans confirmation (mode expérimental automatique) :
python gme_patch.py assemble original.gme dossier_media/ sortie.gme --force
```

Noms de fichiers dans `dossier_media/` (convention tttool) :

```
Feuerwehr_0.ogg      → remplace l'index 0
Feuerwehr_42.ogg     → remplace l'index 42
Feuerwehr_42_v32.ogg → remplace l'index 42 (suffixe de version ignoré)
```

Les index sans fichier de remplacement conservent l'audio original.

#### Afficher les informations

```bash
python gme_patch.py info fichier.gme
```

#### Aide

```bash
python gme_patch.py --help
python gme_patch.py assemble --help
```

---

### Intégration pipeline

```python
from pathlib import Path
from gme_patch import patch_gme

result = patch_gme(Path("entree.gme"), Path("tts_output/"), Path("sortie.gme"), force=True)

# result = {
#     "mode": "safe" | "experimental" | "aborted",
#     "output": Path,       # chemin de sortie réel (peut inclure _experimentell)
#     "entries": int,       # total des entrées dans la table audio
#     "replaced": int,      # entrées remplacées
#     "kept": int,          # entrées conservées de l'original
# }
```

---

### Choix de conception

| Choix | Justification |
|---|---|
| **Pas de déduplication** | libtiptoi.c écrit chaque index comme copie séparée. Plus sûr, évite les risques liés aux références d'offset. |
| **Pas de scan aveugle** | v3 scannait toutes les positions 4 octets → corrompait les scripts → crashs. v4 ne corrige que 3 offsets d'en-tête documentés. |
| **Deux modes explicites** | Séparation claire entre sûr (éprouvé) et expérimental (best-effort), avec marquage des fichiers de sortie. |
| **CLI compatible tttool** | Mêmes noms de commandes (`media`, `assemble`, `info`) → remplacement direct dans les scripts existants. |
| **Aucune dépendance** | Stdlib Python uniquement → fonctionne partout avec Python 3.10+. |

---

### Référence du format

| Offset | Contenu |
|--------|---------|
| `0x0000` | Offset table principale (scripts, codes OID) |
| `0x0004` | Offset table audio |
| `0x0014` | Code du livre |
| `0x005C` | Offset table binaires (jeux) |
| `0x0060` | Offset table audio supplémentaire |
| `0x0064` | Offset table binaires individuels |
| `0x0068` | Offset table symboles spéciaux |

Documentation complète : [GME-Format.md](https://github.com/entropia/tip-toi-reveng/blob/master/GME-Format.md)

---

<a id="crédits-fr"></a>

### Crédits

- Format GME rétro-ingéniéré par la communauté [tip-toi-reveng](https://github.com/entropia/tip-toi-reveng)
- `libtiptoi.c` par Michael Wolf (licence MIT) — implémentation de référence
- `tttool` par Joachim Breitner — outil standard pour les workflows YAML

---
---

<a id="español"></a>

## Español

### Tabla de contenidos

- [¿Qué es esto?](#qué-es-esto)
- [El problema](#el-problema-es)
- [La solución](#la-solución)
- [Funcionamiento técnico](#funcionamiento-técnico)
- [Instalación](#instalación)
- [Uso](#uso)
- [Integración en pipelines](#integración-en-pipelines)
- [Decisiones de diseño](#decisiones-de-diseño)
- [Referencia del formato](#referencia-del-formato)
- [Créditos](#créditos-es)

---

### ¿Qué es esto?

`gme_patch.py` reemplaza archivos de audio dentro de archivos `.gme` de Ravensburger Tiptoi mediante un **parche binario directo**. A diferencia del flujo estándar con `tttool export` + `tttool assemble`, esta herramienta preserva toda la lógica de juego, scripts y segmentos binarios desconocidos bit a bit.

Las funcionalidades interactivas como cuestionarios, puzzles y minijuegos **siguen funcionando** después de reemplazar el audio.

Caso de uso principal: traducir libros Tiptoi del alemán a otros idiomas (p. ej. francés, suizo alemán) manteniendo todas las funcionalidades interactivas.

---

<a id="el-problema-es"></a>

### El problema

La herramienta estándar (`tttool`) usa un viaje de ida y vuelta YAML:

```
GME original → tttool export → YAML + Audio → tttool assemble → Nuevo GME
```

Este proceso **pierde 8 segmentos binarios desconocidos** (~4.500 bytes) que contienen lógica de juego y datos de firmware. Después del reensamblaje, los juegos interactivos dejan de funcionar — el lápiz entra en bucle, se cuelga o reproduce audio incorrecto.

Este problema fue confirmado por el autor de `tttool`, Joachim Breitner, en la lista de correo de [tip-toi-reveng](https://github.com/entropia/tip-toi-reveng) (26/02/2026), quien señaló a `libtiptoi.c` como implementación de referencia para el parcheado binario directo.

---

### La solución

`gme_patch.py` parchea el binario directamente — sin exportación YAML, sin viaje de ida y vuelta. Todo lo que no es audio permanece idéntico bit a bit.

**Modo seguro** (automático cuando no hay datos post-audio):

Construcción idéntica a `libtiptoi.c`: Header → Tabla → Audio → Checksum.

**Modo experimental** (cuando existen datos post-audio como binarios de juego):

Confirmación interactiva antes del parche (o `--force`). Los datos post-audio se añaden bit a bit, solo 3 punteros de cabecera conocidos se corrigen. Sin escaneo ciego. El archivo de salida recibe el sufijo `_experimentell`.

---

### Funcionamiento técnico

#### Modo seguro (basado en libtiptoi.c)

1. **Copiar todo antes de la tabla de audio** — cabecera, scripts, tablas OID, tablas de salto — bit a bit, sin modificar.
2. **Escribir nueva tabla de audio** — N entradas de `(offset: uint32, longitud: uint32)`. Los offsets se recalculan según los nuevos tamaños de archivo.
3. **Escribir datos de audio** — cada archivo se lee (o se conserva del original), se cifra XOR y se añade secuencialmente.
4. **Añadir checksum** — suma aditiva de todos los bytes anteriores, 4 bytes little-endian.

Sin deduplicación: cada índice de tabla recibe su propia copia de audio (como libtiptoi.c).

#### Modo experimental (extensión más allá de libtiptoi.c)

Además de los pasos del modo seguro:

1. **Añadir datos post-audio** bit a bit después del nuevo bloque de audio.
2. **Corregir solo punteros de cabecera conocidos** en las posiciones `0x005C` (tabla de binarios), `0x0064` (tabla de binarios individuales) y `0x0068` (tabla de símbolos especiales).
3. **Corregir estructuras internas de tablas binarias** — cada tabla tiene un formato conocido (`count + count × offset`).
4. **Sin escaneo ciego** — las versiones anteriores escaneaban cada posición de 4 bytes, corrompiendo comandos de script, valores de timer y códigos OID → cuelgues. v4 elimina esto por completo.

#### Cifrado XOR

Tiptoi cifra el audio con un XOR simple. La clave se deriva de los bytes mágicos del primer archivo de audio (`OggS` o `RIFF`). Reglas: `0x00`, `0xFF`, `key`, `key^0xFF` permanecen sin cambios; todos los demás bytes se someten a XOR con la clave. El codec es simétrico.

---

### Instalación

#### Requisitos

- **Python 3.10+** (usa type hints con `|`)
- Sin dependencias externas — solo biblioteca estándar (`struct`, `re`, `argparse`, `pathlib`)

#### requirements.txt

```
# gme_patch.py no tiene dependencias externas.
# Python 3.10+ con la biblioteca estándar es suficiente.
```

#### Configuración

```bash
git clone https://github.com/YOUR_USER/tiptoi-gme-patcher.git
cd tiptoi-gme-patcher
python gme_patch.py --help
```

---

### Uso

Los comandos CLI corresponden a los de `tttool` para facilitar la integración en flujos de trabajo existentes.

#### Extraer audio

```bash
python gme_patch.py media -d directorio_salida/ archivo.gme
```

Extrae todos los archivos de audio de un GME, descifrados XOR, con nombres de archivo compatibles con tttool (`NombreLibro_0.ogg`, `NombreLibro_1.ogg`, ...).

#### Reemplazar audio

```bash
# Estándar (modo seguro si es posible, si no confirmación):
python gme_patch.py assemble original.gme directorio_media/ salida.gme

# Sin confirmación (modo experimental automático):
python gme_patch.py assemble original.gme directorio_media/ salida.gme --force
```

Nombres de archivo en `directorio_media/` (convención tttool):

```
Feuerwehr_0.ogg      → reemplaza índice 0
Feuerwehr_42.ogg     → reemplaza índice 42
Feuerwehr_42_v32.ogg → reemplaza índice 42 (sufijo de versión ignorado)
```

Los índices sin archivo de reemplazo conservan su audio original.

#### Mostrar información

```bash
python gme_patch.py info archivo.gme
```

#### Ayuda

```bash
python gme_patch.py --help
python gme_patch.py assemble --help
```

---

### Integración en pipelines

```python
from pathlib import Path
from gme_patch import patch_gme

result = patch_gme(Path("entrada.gme"), Path("tts_output/"), Path("salida.gme"), force=True)

# result = {
#     "mode": "safe" | "experimental" | "aborted",
#     "output": Path,       # ruta de salida real (puede incluir _experimentell)
#     "entries": int,       # total de entradas en la tabla de audio
#     "replaced": int,      # entradas reemplazadas
#     "kept": int,          # entradas conservadas del original
# }
```

---

### Decisiones de diseño

| Decisión | Justificación |
|---|---|
| **Sin deduplicación** | libtiptoi.c escribe cada índice como copia separada. Más seguro, evita riesgos con referencias de offset. |
| **Sin escaneo ciego** | v3 escaneaba todas las posiciones de 4 bytes → corrompía scripts → crashes. v4 solo corrige 3 offsets de cabecera documentados. |
| **Dos modos explícitos** | Separación clara entre seguro (probado) y experimental (mejor esfuerzo), con marcado de archivos de salida. |
| **CLI compatible con tttool** | Mismos nombres de comandos (`media`, `assemble`, `info`) → reemplazo directo en scripts existentes. |
| **Sin dependencias** | Solo stdlib de Python → funciona en cualquier lugar con Python 3.10+. |

---

### Referencia del formato

| Offset | Contenido |
|--------|-----------|
| `0x0000` | Offset tabla principal (scripts, códigos OID) |
| `0x0004` | Offset tabla de audio |
| `0x0014` | Código del libro |
| `0x005C` | Offset tabla de binarios (juegos) |
| `0x0060` | Offset tabla de audio adicional |
| `0x0064` | Offset tabla de binarios individuales |
| `0x0068` | Offset tabla de símbolos especiales |

Documentación completa: [GME-Format.md](https://github.com/entropia/tip-toi-reveng/blob/master/GME-Format.md)

---

<a id="créditos-es"></a>

### Créditos

- Formato GME ingeniería inversa por la comunidad [tip-toi-reveng](https://github.com/entropia/tip-toi-reveng)
- `libtiptoi.c` por Michael Wolf (licencia MIT) — implementación de referencia
- `tttool` por Joachim Breitner — herramienta estándar para flujos de trabajo YAML

---

## License

MIT License — see [libtiptoi.c](https://github.com/entropia/tip-toi-reveng/blob/master/libtiptoi.c) for the original reference implementation.
