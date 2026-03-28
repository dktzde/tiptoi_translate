# Tiptoi DE → FR / CH / VO / BY / ND

[English](#english) · [Français](#français) · [Deutsch](#deutsch)

---

## English

A personal hobby project: automatically translating Tiptoi books (Ravensburger)
from German into another language. Takes a GME file, replaces the audio files,
and produces a new playable GME file.

Supported target languages: French, Swiss German, Vogtlandish, Bavarian, Low German.

> **Note:** This is not an official tool and not a polished product.
> It works for my use case — but there will certainly be books where it breaks.
> Feedback and improvements are welcome.

### Built on tttool and tip-toi-reveng

This project depends entirely on the work of the
[tip-toi-reveng](https://github.com/entropia/tip-toi-reveng) community.
Without `tttool` (GME unpacking, YAML, assemble) and the format documentation
maintained there, this project would not be possible.

### Why Google Colab for transcription?

My PC has no GPU, so no CUDA. Whisper runs on CPU only.

A typical Tiptoi book has **1,000–2,000 OGG files**. With the `small` model on CPU
that takes several hours; the more accurate `large-v3-turbo` model would be
practically unusable locally.

**Solution: offload step 2 (transcription) to Google Colab.**
Colab provides a free NVIDIA T4 GPU — `large-v3-turbo` runs ~1–2 seconds per file
there instead of minutes. The finished TXT transcripts are placed back into
`03_transcripts/`; all other steps run locally.

```
Local PC:  unpack GME → zip OGGs → upload
Colab:     unzip OGGs → Whisper large-v3-turbo → zip TXTs → download
Local PC:  unzip TXTs → translate → TTS → pack GME
```

### Workflow (6 steps)

| Step | Description | Tool |
|------|-------------|------|
| 1 | Unpack GME (YAML + OGG) | `tttool export` / `tttool media` |
| 2 | Transcribe DE | faster-whisper (`small` local / `large-v3-turbo` Colab) |
| 3 | Translate DE → target language | Mistral API (`magistral-medium-latest`) |
| 4 | TTS | edge-tts |
| 5 | OGG conversion | ffmpeg (mono, 22050 Hz) |
| 6 | Repack GME | `tttool assemble` or `gme_patch.py` (binary patch) |

### Requirements

- Python 3.13+
- ffmpeg 7.1+ (`sudo apt install ffmpeg`)
- tttool 1.11 at `~/.local/bin/tttool`
  → Download: https://github.com/entropia/tip-toi-reveng/releases
- Mistral API key (https://console.mistral.ai/)

### Setup

```bash
mkdir -p ~/.local/bin && cp tttool ~/.local/bin/tttool && chmod +x ~/.local/bin/tttool
python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
cp .env.example .env && nano .env   # MISTRAL_API_KEY=your_key_here
```

### Usage

```bash
./tiptoi.sh 01_input/book.gme                          # French (default)
./tiptoi.sh 01_input/book.gme --language ch            # Swiss German
./tiptoi.sh 01_input/book.gme --language by            # Bavarian
./tiptoi.sh 01_input/book.gme --language vo            # Vogtlandish
./tiptoi.sh 01_input/book.gme --language nd            # Low German
./tiptoi.sh 01_input/book.gme --use-patcher            # binary patch (experimental)
./tiptoi.sh 01_input/book.gme --limit 10               # test run (first 10 files)
```

The finished file ends up in `06_output/book_fr.gme` (or `_ch`, `_vo`, `_by`, `_nd`).
Resume works automatically — just run the same command again.

<details>
<summary>All pipeline options</summary>

```bash
python pipeline.py 01_input/book.gme [OPTIONS]

  --language LANG         Target language: fr, ch, vo, by, nd  (default: fr)
  --voice VOICE           edge-tts voice (overrides language default)
  --whisper-model MODEL   Whisper model: tiny, base, small, medium, large-v3-turbo
  --limit N               Process only the first N audio files (0 = all)
  --use-patcher           [experimental] binary patch instead of tttool assemble
  --skip-assemble         Skip step 6 (keep OGGs for manual patching)
  --offline               Run everything locally
  --min-k N               Minimum speaker clusters (default: 2)
```
</details>

### A note on dialects

**Swiss German** works reasonably well — the CH voices in edge-tts sound convincing
and Mistral translates into Swiss German solidly.

**Vogtlandish, Bavarian, and Low German** unfortunately tend to sound like standard
German. There are no proper dialect TTS voices available, and Mistral's translation
quality for these dialects is limited. These options are therefore more experimental
than practical.

### Voices (8 per language)

<details>
<summary>French · Swiss German · Vogtlandish · Bavarian · Low German</summary>

**French (`--language fr`)**

| # | Voice | Type |
|---|-------|------|
| 0 | `fr-FR-HenriNeural` | m, deep narrator |
| 1 | `fr-FR-EloiseNeural` | f, child voice |
| 2 | `fr-BE-CharlineNeural` | f, Belgian (child 2) |
| 3 | `fr-FR-RemyMultilingualNeural` | m, natural |
| 4 | `fr-FR-VivienneMultilingualNeural` | f, narrator |
| 5 | `fr-FR-DeniseNeural` | f, warm/mature |
| 6 | `fr-BE-GerardNeural` | m, Belgian |
| 7 | `fr-CH-FabriceNeural` | m, Swiss FR |

**Swiss German (`--language ch`)**

| # | Voice | Type |
|---|-------|------|
| 0 | `de-CH-JanNeural` | m, Swiss German |
| 1 | `de-CH-LeniNeural` | f, Swiss German |
| 2 | `de-AT-JonasNeural` | m, Austrian |
| 3 | `de-AT-IngridNeural` | f, Austrian |
| 4 | `de-DE-FlorianMultilingualNeural` | m, multilingual |
| 5 | `de-DE-SeraphinaMultilingualNeural` | f, multilingual |
| 6 | `de-DE-ConradNeural` | m, standard German |
| 7 | `de-DE-KatjaNeural` | f, standard German |

**Vogtlandish (`--language vo`)**

| # | Voice | Type |
|---|-------|------|
| 0 | `de-DE-FlorianMultilingualNeural` | m, multilingual |
| 1 | `de-DE-SeraphinaMultilingualNeural` | f, multilingual |
| 2 | `de-DE-ConradNeural` | m |
| 3 | `de-DE-KatjaNeural` | f |
| 4 | `de-DE-KillianNeural` | m |
| 5 | `de-DE-AmalaNeural` | f |
| 6 | `de-CH-JanNeural` | m |
| 7 | `de-AT-IngridNeural` | f |

**Bavarian (`--language by`)**

| # | Voice | Type |
|---|-------|------|
| 0 | `de-AT-JonasNeural` | m, Austrian |
| 1 | `de-AT-IngridNeural` | f, Austrian |
| 2 | `de-DE-FlorianMultilingualNeural` | m, multilingual |
| 3 | `de-DE-SeraphinaMultilingualNeural` | f, multilingual |
| 4 | `de-CH-JanNeural` | m |
| 5 | `de-CH-LeniNeural` | f |
| 6 | `de-DE-ConradNeural` | m |
| 7 | `de-DE-KatjaNeural` | f |

**Low German (`--language nd`)**

| # | Voice | Type |
|---|-------|------|
| 0 | `de-DE-FlorianMultilingualNeural` | m, multilingual |
| 1 | `de-DE-SeraphinaMultilingualNeural` | f, multilingual |
| 2 | `de-DE-KillianNeural` | m |
| 3 | `de-DE-KatjaNeural` | f |
| 4 | `de-DE-ConradNeural` | m |
| 5 | `de-DE-AmalaNeural` | f |
| 6 | `de-AT-JonasNeural` | m |
| 7 | `de-CH-LeniNeural` | f |

</details>

### Acknowledgements

This project would not exist without the groundwork laid by the
[tip-toi-reveng](https://github.com/entropia/tip-toi-reveng) community —
in particular the complete GME format documentation, `tttool`, and
`libtiptoi.c` by Michael Wolf. Thank you for years of reverse-engineering work.

### License

MIT License — see [LICENSE](LICENSE)

---

## Français

Un projet personnel : traduire automatiquement des livres Tiptoi (Ravensburger)
de l'allemand vers une autre langue. Le programme prend un fichier GME,
remplace les fichiers audio et produit un nouveau fichier GME lisible.

Langues cibles disponibles : français, alémanique suisse, vogtlandais,
bavarois, bas allemand.

> **Remarque :** Ce n'est pas un outil officiel ni un produit finalisé.
> Ça fonctionne pour mon usage — mais il y a certainement des livres pour
> lesquels ça coince. Retours et améliorations bienvenus.

### Basé sur tttool et tip-toi-reveng

Ce projet repose entièrement sur le travail de la communauté
[tip-toi-reveng](https://github.com/entropia/tip-toi-reveng).
Sans `tttool` et la documentation du format maintenue là-bas,
ce projet ne serait pas possible.

### Pourquoi Google Colab pour la transcription ?

Mon PC n'a pas de GPU. Whisper tourne uniquement sur CPU, ce qui prend plusieurs
heures pour un livre typique (1 000–2 000 fichiers OGG).

**Solution : externaliser la transcription sur Google Colab** (GPU T4 gratuit,
~1–2 s par fichier avec `large-v3-turbo`). Les TXT reviennent dans `03_transcripts/` ;
tout le reste tourne en local.

### Workflow (6 étapes)

| Étape | Description | Outil |
|-------|-------------|-------|
| 1 | Décompresser GME (YAML + OGG) | `tttool export` / `tttool media` |
| 2 | Transcription DE | faster-whisper |
| 3 | Traduction DE → langue cible | Mistral API (`magistral-medium-latest`) |
| 4 | TTS | edge-tts |
| 5 | Conversion OGG | ffmpeg (mono, 22050 Hz) |
| 6 | Repackager GME | `tttool assemble` ou `gme_patch.py` |

### Utilisation

```bash
./tiptoi.sh 01_input/livre.gme                         # français (défaut)
./tiptoi.sh 01_input/livre.gme --language ch           # alémanique suisse
./tiptoi.sh 01_input/livre.gme --language by           # bavarois
./tiptoi.sh 01_input/livre.gme --language vo           # vogtlandais
./tiptoi.sh 01_input/livre.gme --language nd           # bas allemand
./tiptoi.sh 01_input/livre.gme --use-patcher           # patch binaire (expérimental)
./tiptoi.sh 01_input/livre.gme --limit 10              # test (10 premiers fichiers)
```

### Note sur les dialectes

**L'alémanique suisse** fonctionne plutôt bien — les voix CH d'edge-tts sont
convaincantes et Mistral traduit correctement.

**Le vogtlandais, le bavarois et le bas allemand** sonnent malheureusement
comme de l'allemand standard. Il n'existe pas de vraies voix TTS pour ces
dialectes, et la qualité de traduction de Mistral y est limitée.
Ces options sont donc plutôt expérimentales.

### Remerciements

Ce projet n'existerait pas sans le travail de la communauté
[tip-toi-reveng](https://github.com/entropia/tip-toi-reveng) —
notamment `tttool` et `libtiptoi.c` de Michael Wolf.
Merci pour des années de rétro-ingénierie.

### Licence

MIT License — voir [LICENSE](LICENSE)

---

## Deutsch

Ein persönliches Bastelprojekt: Tiptoi-Bücher (Ravensburger) automatisch
von Deutsch in eine andere Sprache übersetzen. Nimmt eine GME-Datei,
tauscht die Audiodateien aus und erzeugt eine neue abspielbare GME-Datei.

Unterstützte Zielsprachen: Französisch, Schweizerdeutsch, Vogtländisch,
Bairisch, Plattdeutsch.

> **Hinweis:** Das ist kein offizielles Tool und kein fertig poliertes Produkt.
> Es funktioniert für meinen Anwendungsfall — aber es gibt sicher Bücher,
> bei denen es hakt. Feedback und Verbesserungen sind willkommen.

### Abhängigkeit von tttool und tip-toi-reveng

Dieses Projekt baut vollständig auf der Arbeit der
[tip-toi-reveng](https://github.com/entropia/tip-toi-reveng)-Community auf.
Ohne `tttool` und die dort dokumentierten Formatdetails wäre dieses Projekt
nicht möglich.

### Warum Google Colab für die Transkription?

Mein PC hat keine GPU. Whisper läuft auf CPU, was für ein typisches Buch
(1.000–2.000 OGG-Dateien) mehrere Stunden dauert.

**Lösung: Transkription auf Google Colab auslagern** (kostenlose T4-GPU,
~1–2 Sekunden pro Datei mit `large-v3-turbo`). Die TXTs kommen zurück
in `03_transcripts/`; alle anderen Schritte laufen lokal.

### Workflow (6 Schritte)

| Schritt | Beschreibung | Tool |
|---------|-------------|------|
| 1 | GME entpacken (YAML + OGG) | `tttool export` / `tttool media` |
| 2 | Transkription DE | faster-whisper |
| 3 | Übersetzung DE → Zielsprache | Mistral API (`magistral-medium-latest`) |
| 4 | TTS | edge-tts |
| 5 | OGG-Konvertierung | ffmpeg (Mono, 22050 Hz) |
| 6 | GME neu packen | `tttool assemble` oder `gme_patch.py` |

### Einmalige Einrichtung

```bash
mkdir -p ~/.local/bin && cp tttool ~/.local/bin/tttool && chmod +x ~/.local/bin/tttool
python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
cp .env.example .env && nano .env   # MISTRAL_API_KEY=dein_key_hier
```

### Verwendung

```bash
./tiptoi.sh 01_input/buch.gme                          # Französisch (Standard)
./tiptoi.sh 01_input/buch.gme --language ch            # Schweizerdeutsch
./tiptoi.sh 01_input/buch.gme --language by            # Bairisch
./tiptoi.sh 01_input/buch.gme --language vo            # Vogtländisch
./tiptoi.sh 01_input/buch.gme --language nd            # Plattdeutsch
./tiptoi.sh 01_input/buch.gme --use-patcher            # Binary-Patch (experimentell)
./tiptoi.sh 01_input/buch.gme --limit 10               # Testlauf (erste 10 Dateien)
```

Die fertige Datei liegt in `06_output/buch_fr.gme` (bzw. `_ch`, `_vo`, `_by`, `_nd`).
Resume funktioniert automatisch — denselben Befehl einfach erneut ausführen.

<details>
<summary>Alle Pipeline-Optionen</summary>

```bash
python pipeline.py 01_input/buch.gme [OPTIONEN]

  --language SPRACHE      Zielsprache: fr, ch, vo, by, nd  (Standard: fr)
  --voice STIMME          edge-tts Stimme (überschreibt Sprachstandard)
  --whisper-model MODELL  Whisper-Modell: tiny, base, small, medium, large-v3-turbo
  --limit N               Nur die ersten N Audiodateien verarbeiten (0 = alle)
  --use-patcher           [experimentell] Binary-Patch statt tttool assemble
  --skip-assemble         Schritt 6 überspringen (OGGs für manuellen Patch)
  --offline               Alles lokal ausführen
  --min-k N               Mindestanzahl Sprecher-Cluster (Standard: 2)
```
</details>

### Dialekte: ein Hinweis

**Schweizerdeutsch** funktioniert erfahrungsgemäß gut — die CH-Stimmen von
edge-tts klingen überzeugend und Mistral übersetzt solide ins Schweizerdeutsche.

**Vogtländisch, Bairisch und Plattdeutsch** klingen leider weitgehend wie
Hochdeutsch. Echte Dialekt-TTS-Stimmen gibt es nicht; die verfügbaren Stimmen
geben den Dialektcharakter kaum wieder. Auch die Übersetzungsqualität von Mistral
ist für diese Dialekte eingeschränkt. Diese Optionen sind daher eher experimentell.

### Stimmen (8 pro Sprache)

<details>
<summary>Französisch · Schweizerdeutsch · Vogtländisch · Bairisch · Plattdeutsch</summary>

**Französisch (`--language fr`)**

| # | Stimme | Typ |
|---|--------|-----|
| 0 | `fr-FR-HenriNeural` | m, tiefer Erzähler |
| 1 | `fr-FR-EloiseNeural` | f, Kinderstimme |
| 2 | `fr-BE-CharlineNeural` | f, belgisch (Kind 2) |
| 3 | `fr-FR-RemyMultilingualNeural` | m, natürlich |
| 4 | `fr-FR-VivienneMultilingualNeural` | f, Erzählerin |
| 5 | `fr-FR-DeniseNeural` | f, warm/reif |
| 6 | `fr-BE-GerardNeural` | m, belgisch |
| 7 | `fr-CH-FabriceNeural` | m, Schweizer FR |

**Schweizerdeutsch (`--language ch`)**

| # | Stimme | Typ |
|---|--------|-----|
| 0 | `de-CH-JanNeural` | m, Schweizerdeutsch |
| 1 | `de-CH-LeniNeural` | f, Schweizerdeutsch |
| 2 | `de-AT-JonasNeural` | m, Österreichisch |
| 3 | `de-AT-IngridNeural` | f, Österreichisch |
| 4 | `de-DE-FlorianMultilingualNeural` | m, multilingual |
| 5 | `de-DE-SeraphinaMultilingualNeural` | f, multilingual |
| 6 | `de-DE-ConradNeural` | m, Hochdeutsch |
| 7 | `de-DE-KatjaNeural` | f, Hochdeutsch |

**Vogtländisch (`--language vo`)**

| # | Stimme | Typ |
|---|--------|-----|
| 0 | `de-DE-FlorianMultilingualNeural` | m, multilingual |
| 1 | `de-DE-SeraphinaMultilingualNeural` | f, multilingual |
| 2 | `de-DE-ConradNeural` | m |
| 3 | `de-DE-KatjaNeural` | f |
| 4 | `de-DE-KillianNeural` | m |
| 5 | `de-DE-AmalaNeural` | f |
| 6 | `de-CH-JanNeural` | m |
| 7 | `de-AT-IngridNeural` | f |

**Bairisch (`--language by`)**

| # | Stimme | Typ |
|---|--------|-----|
| 0 | `de-AT-JonasNeural` | m, Österreichisch |
| 1 | `de-AT-IngridNeural` | f, Österreichisch |
| 2 | `de-DE-FlorianMultilingualNeural` | m, multilingual |
| 3 | `de-DE-SeraphinaMultilingualNeural` | f, multilingual |
| 4 | `de-CH-JanNeural` | m |
| 5 | `de-CH-LeniNeural` | f |
| 6 | `de-DE-ConradNeural` | m |
| 7 | `de-DE-KatjaNeural` | f |

**Plattdeutsch (`--language nd`)**

| # | Stimme | Typ |
|---|--------|-----|
| 0 | `de-DE-FlorianMultilingualNeural` | m, multilingual |
| 1 | `de-DE-SeraphinaMultilingualNeural` | f, multilingual |
| 2 | `de-DE-KillianNeural` | m |
| 3 | `de-DE-KatjaNeural` | f |
| 4 | `de-DE-ConradNeural` | m |
| 5 | `de-DE-AmalaNeural` | f |
| 6 | `de-AT-JonasNeural` | m |
| 7 | `de-CH-LeniNeural` | f |

</details>

### Ordnerstruktur

```
01_input/       GME-Eingabedateien
02_unpacked/    tttool-Output (YAML + OGG)
03_transcripts/ Whisper-Transkripte (DE)
04_translated/  Mistral-Übersetzungen
05_tts_output/  edge-tts MP3-Dateien
06_output/      Fertige *_fr / *_ch / *_vo / *_by / *_nd .gme
backup/         Versionierte Skript-Backups
```

### Danke

Dieses Projekt wäre ohne die Vorarbeit der
[tip-toi-reveng](https://github.com/entropia/tip-toi-reveng)-Community
nicht möglich — insbesondere `tttool` und `libtiptoi.c` (Michael Wolf).
Vielen Dank für die jahrelange Reverse-Engineering-Arbeit.

### Lizenz

MIT License — siehe [LICENSE](LICENSE)
