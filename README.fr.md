# Traducteur Tiptoi DE → FR / CH / VO / BY / ND

Un projet personnel : traduire automatiquement des livres Tiptoi (Ravensburger)
de l'allemand vers une autre langue. Le programme prend un fichier GME,
remplace les fichiers audio et produit un nouveau fichier GME lisible.

Langues cibles disponibles : français, alémanique suisse, vogtlandais,
bavarois, bas allemand.

> **Remarque :** Ce n'est pas un outil officiel ni un produit finalisé.
> Ça fonctionne pour mon usage — mais il y a certainement des livres pour
> lesquels ça coince. Retours et améliorations bienvenus.

---

## Basé sur tttool et tip-toi-reveng

Ce projet repose entièrement sur le travail de la communauté
[tip-toi-reveng](https://github.com/entropia/tip-toi-reveng).
Sans `tttool` (décompression GME, YAML, assemblage) et la documentation
du format maintenue là-bas, ce projet ne serait pas possible.

---

## Pourquoi Google Colab pour la transcription ?

Mon PC n'a pas de GPU, donc pas de CUDA. Whisper tourne uniquement sur CPU.

Un livre Tiptoi typique contient **1 000 à 2 000 fichiers OGG**. Avec le modèle
`small` sur CPU, la transcription prend plusieurs heures ; le modèle plus précis
`large-v3-turbo` serait pratiquement inutilisable en local.

**Solution : externaliser l'étape 2 (transcription) sur Google Colab.**
Colab fournit gratuitement un GPU NVIDIA T4 — `large-v3-turbo` y tourne
en ~1–2 secondes par fichier au lieu de plusieurs minutes. Les fichiers TXT
de transcription sont ensuite replacés dans `03_transcripts/` ; toutes les
autres étapes tournent en local.

```
PC local :  décompresser GME → zipper OGGs → uploader
Colab :     dézipper OGGs → Whisper large-v3-turbo → zipper TXTs → télécharger
PC local :  dézipper TXTs → traduire → TTS → repackager GME
```

---

## Workflow (6 étapes)

| Étape | Description | Outil |
|-------|-------------|-------|
| 1 | Décompresser GME (YAML + OGG) | `tttool export` / `tttool media` |
| 2 | Transcription DE | faster-whisper (`small` local / `large-v3-turbo` Colab) |
| 3 | Traduction DE → langue cible | Mistral API (`magistral-medium-latest`) |
| 4 | TTS | edge-tts |
| 5 | Conversion OGG | ffmpeg (mono, 22050 Hz) |
| 6 | Repackager GME | `tttool assemble` ou `gme_patch.py` (patch binaire) |

---

## Prérequis

- Python 3.13+
- ffmpeg 7.1+ (`sudo apt install ffmpeg`)
- tttool 1.11 dans `~/.local/bin/tttool`
  → Téléchargement : https://github.com/entropia/tip-toi-reveng/releases
- Clé API Mistral (https://console.mistral.ai/)

---

## Installation

```bash
# installer tttool
mkdir -p ~/.local/bin
cp tttool ~/.local/bin/tttool
chmod +x ~/.local/bin/tttool

# environnement Python
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# clé API
cp .env.example .env
nano .env   # MISTRAL_API_KEY=ta_clé_ici
```

---

## Utilisation

```bash
# placer le GME dans 01_input/, puis :
./tiptoi.sh 01_input/livre.gme

# alémanique suisse
./tiptoi.sh 01_input/livre.gme --language ch

# bavarois
./tiptoi.sh 01_input/livre.gme --language by

# vogtlandais
./tiptoi.sh 01_input/livre.gme --language vo

# bas allemand
./tiptoi.sh 01_input/livre.gme --language nd

# patch binaire (conserve la logique de jeu, expérimental) :
./tiptoi.sh 01_input/livre.gme --use-patcher

# seulement les 10 premiers fichiers (test)
./tiptoi.sh 01_input/livre.gme --limit 10

# modèle Whisper plus grand
./tiptoi.sh 01_input/livre.gme --whisper-model medium
```

Le fichier final se trouve dans `06_output/livre_fr.gme` (ou `_ch`, `_vo`, `_by`, `_nd`).
La reprise fonctionne automatiquement — relancer simplement la même commande.

### Toutes les options

```bash
python pipeline.py 01_input/livre.gme [OPTIONS]

  --language LANGUE       Langue cible : fr, ch, vo, by, nd  (défaut : fr)
  --voice VOIX            Voix edge-tts (remplace le défaut de la langue)
  --whisper-model MODÈLE  Modèle Whisper : tiny, base, small, medium, large-v3-turbo
                          (défaut : small)
  --limit N               Traiter seulement les N premiers fichiers audio (0 = tous)
  --use-patcher           [expérimental] étape 6 via gme_patch.py au lieu de tttool assemble
  --skip-assemble         Sauter l'étape 6 (les OGGs restent pour un patch manuel)
  --offline               Tout exécuter en local (pas de pause Colab)
  --min-k N               Nombre minimum de clusters de locuteurs (défaut : 2)
```

---

## Note sur les dialectes

**L'alémanique suisse** fonctionne plutôt bien — les voix CH d'edge-tts sont
convaincantes et Mistral traduit correctement vers le suisse-allemand.

**Le vogtlandais, le bavarois et le bas allemand** sonnent malheureusement
comme de l'allemand standard. Il n'existe pas de vraies voix TTS pour ces
dialectes ; les voix DE/AT/CH disponibles ne restituent pas vraiment le
caractère dialectal. La qualité de traduction de Mistral pour ces dialectes
est également limitée. Ces options de langue sont donc plutôt expérimentales.

---

## Voix (8 par langue)

Chaque langue dispose de 8 voix edge-tts (4h/4f). Les locuteurs sont détectés
automatiquement via **resemblyzer** (embeddings GE2E) et associés aux voix.
Le résultat est sauvegardé dans `speakers.json` par livre.

**Français (`--language fr`)**

| # | Voix | Type |
|---|------|------|
| 0 | `fr-FR-HenriNeural` | h, narrateur grave |
| 1 | `fr-FR-EloiseNeural` | f, voix enfant |
| 2 | `fr-BE-CharlineNeural` | f, belge (enfant 2) |
| 3 | `fr-FR-RemyMultilingualNeural` | h, naturel |
| 4 | `fr-FR-VivienneMultilingualNeural` | f, narratrice |
| 5 | `fr-FR-DeniseNeural` | f, chaleureuse/mature |
| 6 | `fr-BE-GerardNeural` | h, belge |
| 7 | `fr-CH-FabriceNeural` | h, suisse FR |

**Alémanique suisse (`--language ch`)**

| # | Voix | Type |
|---|------|------|
| 0 | `de-CH-JanNeural` | h, suisse allemand |
| 1 | `de-CH-LeniNeural` | f, suisse allemand |
| 2 | `de-AT-JonasNeural` | h, autrichien |
| 3 | `de-AT-IngridNeural` | f, autrichienne |
| 4 | `de-DE-FlorianMultilingualNeural` | h, multilingue |
| 5 | `de-DE-SeraphinaMultilingualNeural` | f, multilingue |
| 6 | `de-DE-ConradNeural` | h, allemand standard |
| 7 | `de-DE-KatjaNeural` | f, allemand standard |

**Vogtlandais (`--language vo`)**

| # | Voix | Type |
|---|------|------|
| 0 | `de-DE-FlorianMultilingualNeural` | h, multilingue |
| 1 | `de-DE-SeraphinaMultilingualNeural` | f, multilingue |
| 2 | `de-DE-ConradNeural` | h |
| 3 | `de-DE-KatjaNeural` | f |
| 4 | `de-DE-KillianNeural` | h |
| 5 | `de-DE-AmalaNeural` | f |
| 6 | `de-CH-JanNeural` | h |
| 7 | `de-AT-IngridNeural` | f |

**Bavarois (`--language by`)**

| # | Voix | Type |
|---|------|------|
| 0 | `de-AT-JonasNeural` | h, autrichien |
| 1 | `de-AT-IngridNeural` | f, autrichienne |
| 2 | `de-DE-FlorianMultilingualNeural` | h, multilingue |
| 3 | `de-DE-SeraphinaMultilingualNeural` | f, multilingue |
| 4 | `de-CH-JanNeural` | h |
| 5 | `de-CH-LeniNeural` | f |
| 6 | `de-DE-ConradNeural` | h |
| 7 | `de-DE-KatjaNeural` | f |

**Bas allemand (`--language nd`)**

| # | Voix | Type |
|---|------|------|
| 0 | `de-DE-FlorianMultilingualNeural` | h, multilingue |
| 1 | `de-DE-SeraphinaMultilingualNeural` | f, multilingue |
| 2 | `de-DE-KillianNeural` | h |
| 3 | `de-DE-KatjaNeural` | f |
| 4 | `de-DE-ConradNeural` | h |
| 5 | `de-DE-AmalaNeural` | f |
| 6 | `de-AT-JonasNeural` | h |
| 7 | `de-CH-LeniNeural` | f |

---

## Structure des dossiers

```
01_input/       fichiers GME en entrée
02_unpacked/    sortie tttool (YAML + OGG)
03_transcripts/ transcriptions Whisper (DE)
04_translated/  traductions Mistral
05_tts_output/  fichiers MP3 edge-tts
06_output/      fichiers *_fr / *_ch / *_vo / *_by / *_nd .gme finis
backup/         sauvegardes versionnées des scripts
```

---

## Stack

- Python 3.13, faster-whisper, mistralai (Magistral), edge-tts, resemblyzer, python-dotenv
- tttool 1.11 (binaire Haskell, par la communauté tip-toi-reveng)
- gme_patch.py / gme_patch_same_lenght.py (patch binaire, expérimental)
- ffmpeg 7.1

---

## Remerciements

Ce projet n'existerait pas sans le travail préalable de la communauté
[tip-toi-reveng](https://github.com/entropia/tip-toi-reveng) —
notamment la documentation complète du format GME, `tttool` et
`libtiptoi.c` de Michael Wolf. Merci pour des années de rétro-ingénierie.

---

## Licence

MIT License — voir [LICENSE](LICENSE)
