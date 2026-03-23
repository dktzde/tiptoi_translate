# gme_uebertragen.sh

[English](#english) · [Français](#français) · [Deutsch](#deutsch)

---

## English

### Background

I own several Tiptoi pens configured for different languages. Using an automated pipeline, I translate Tiptoi book audio from German into French and Swiss German — producing new GME files for each book. I needed a reliable tool to transfer these translated files onto the correct pen, handle versioning, and avoid mistakes like copying a French file onto a German pen.

This script does exactly that.

### Features

- Auto-mounts the pen if not already mounted
- Verifies pen identity via serial number and language (`.tiptoi.log` vs `pen.conf`)
- Filters files by variant (`CH`, `FR`, …) from the pen config
- Reads Product ID (PID) from each GME file via `tttool` and embeds it in the filename (`_pid_033`)
- Detects and replaces older versions on the pen by PID (not just filename)
- Warns if the pen already has a newer version and asks before overwriting
- `--pruefe-stift`: scans all GME files on pen, renames missing PIDs, resolves conflicts interactively
- Safe unmount after transfer

### Requirements

- [`tttool`](https://github.com/entropia/tip-toi-reveng) ≥ 1.11 at `~/.local/bin/tttool`
- Tiptoi pen mounted at `/media/$USER/tiptoi`
- `udisksctl` (part of `udisks2`, standard on Ubuntu/Debian)

### Setup: pen.conf

Create a file `pen.conf` in the **root of the pen** (e.g. `/media/tintifax/tiptoi/pen.conf`):

```ini
PEN_ID=03
PEN_SERIAL=HS595239
PEN_LANG=GERMAN
PEN_VARIANT=CH
```

| Field | Description |
|-------|-------------|
| `PEN_ID` | Unique pen number – used to find the local archive folder (`uebertragen_03_*`) |
| `PEN_SERIAL` | Serial number from `.tiptoi.log` offset 0x00 – prevents wrong pen.conf on wrong pen |
| `PEN_LANG` | Language the pen expects, consistent with tttool (`GERMAN`, `FRENCH`, …) |
| `PEN_VARIANT` | Which file variant belongs on this pen (`CH`, `FR`, …) |

If `pen.conf` is missing, the script will offer to create it interactively. Serial and language are suggested automatically from `.tiptoi.log`.

### File naming on the pen

All GME files on the pen get a PID suffix: `<name>_pid_<XXX>.gme` (3 digits, zero-padded).

Example: `WWW_Flughafen_ch_v30_pid_003.gme`

### Usage

```bash
./gme_uebertragen.sh           # transfer matching files and eject pen
./gme_uebertragen.sh -k        # transfer but keep pen mounted
./gme_uebertragen.sh -p        # scan pen: rename PIDs, resolve conflicts (no transfer)
./gme_uebertragen.sh -h        # help
```

| Option | Short | Description |
|--------|-------|-------------|
| `--pruefe-stift` | `-p` | Scan pen, rename files, resolve PID conflicts |
| `--kein-unmount` | `-k` | Skip unmount after transfer |
| `--help` | `-h` | Show help |

### How it works

1. Check if pen is mounted – if not, attempt auto-mount via `udisksctl`
2. Read and validate `pen.conf`
3. Read serial + language from `.tiptoi.log` and compare with `pen.conf`
4. Rename any files on the pen that are missing `_pid_XXX` in their name
5. Find matching GME files in this directory (by `PEN_VARIANT` in filename)
6. For each file: read PID via `tttool`, add `_pid_XXX` to filename, find and delete old version on pen by PID, copy new file
7. Move transferred file to archive subfolder (`uebertragen_<PEN_ID>_*/`)
8. Sync and unmount

### Notes on `.tiptoi.log`

The Tiptoi pen firmware writes a 64-byte binary file to the pen root on every connect. Layout (16 bytes per field, padded with `\x00`/`\xFF`):

| Offset | Content | Meaning |
|--------|---------|---------|
| `0x00` | e.g. `HS595239` | Serial number |
| `0x10` | e.g. `5GE008` | Firmware version |
| `0x20` | e.g. `GERMAN` | Language setting |
| `0x30` | e.g. `3203L` | Hardware revision |

---

## Français

### Contexte

Je possède plusieurs stylos Tiptoi configurés pour différentes langues. Grâce à un pipeline automatisé, je traduis l'audio des livres Tiptoi de l'allemand vers le français et le suisse-allemand — ce qui produit de nouveaux fichiers GME pour chaque livre. J'avais besoin d'un outil fiable pour transférer ces fichiers traduits sur le bon stylo, gérer les versions et éviter les erreurs comme copier un fichier français sur un stylo allemand.

Ce script fait exactement cela.

### Fonctionnalités

- Monte automatiquement le stylo s'il n'est pas encore monté
- Vérifie l'identité du stylo via numéro de série et langue (`.tiptoi.log` vs `pen.conf`)
- Filtre les fichiers par variante (`CH`, `FR`, …) selon la config du stylo
- Lit le Product ID (PID) de chaque fichier GME via `tttool` et l'intègre dans le nom (`_pid_033`)
- Détecte et remplace les anciennes versions sur le stylo par PID (pas seulement par nom de fichier)
- Avertit si le stylo possède déjà une version plus récente et demande confirmation
- `--pruefe-stift` : scanne tous les fichiers GME du stylo, renomme les PIDs manquants, résout les conflits interactivement
- Éjection sécurisée après le transfert

### Prérequis

- [`tttool`](https://github.com/entropia/tip-toi-reveng) ≥ 1.11 dans `~/.local/bin/tttool`
- Stylo Tiptoi monté sur `/media/$USER/tiptoi`
- `udisksctl` (inclus dans `udisks2`, standard sur Ubuntu/Debian)

### Configuration : pen.conf

Créer un fichier `pen.conf` à la **racine du stylo** (ex. `/media/tintifax/tiptoi/pen.conf`) :

```ini
PEN_ID=03
PEN_SERIAL=HS595239
PEN_LANG=GERMAN
PEN_VARIANT=CH
```

| Champ | Description |
|-------|-------------|
| `PEN_ID` | Numéro unique du stylo – pour trouver le dossier d'archive local (`uebertragen_03_*`) |
| `PEN_SERIAL` | Numéro de série lu dans `.tiptoi.log` offset 0x00 – évite un pen.conf sur le mauvais stylo |
| `PEN_LANG` | Langue attendue par le stylo, cohérent avec tttool (`GERMAN`, `FRENCH`, …) |
| `PEN_VARIANT` | Variante de fichiers à transférer sur ce stylo (`CH`, `FR`, …) |

Si `pen.conf` est absent, le script propose de le créer interactivement. Le numéro de série et la langue sont suggérés automatiquement depuis `.tiptoi.log`.

### Nommage des fichiers sur le stylo

Tous les fichiers GME reçoivent un suffixe PID : `<nom>_pid_<XXX>.gme` (3 chiffres, zéros en tête).

Exemple : `WWW_Flughafen_ch_v30_pid_003.gme`

### Utilisation

```bash
./gme_uebertragen.sh           # transférer les fichiers et éjecter le stylo
./gme_uebertragen.sh -k        # transférer sans éjecter
./gme_uebertragen.sh -p        # scanner le stylo : renommer PIDs, résoudre conflits (sans transfert)
./gme_uebertragen.sh -h        # aide
```

| Option | Court | Description |
|--------|-------|-------------|
| `--pruefe-stift` | `-p` | Scanner le stylo, renommer les fichiers, résoudre les conflits PID |
| `--kein-unmount` | `-k` | Ne pas éjecter après le transfert |
| `--help` | `-h` | Afficher l'aide |

---

## Deutsch

### Hintergrund

Ich besitze mehrere Tiptoi-Stifte, die jeweils für verschiedene Sprachen konfiguriert sind. Mit einer automatisierten Pipeline übersetze ich Tiptoi-Buchaudio von Deutsch nach Französisch und Schweizerdeutsch — das ergibt neue GME-Dateien für jedes Buch. Ich brauchte ein zuverlässiges Tool, das diese übersetzten Dateien auf den richtigen Stift überträgt, Versionen verwaltet und Fehler wie das Kopieren einer französischen Datei auf einen deutschen Stift verhindert.

Genau das macht dieses Skript.

### Funktionen

- Mountet den Stift automatisch, falls er noch nicht eingehängt ist
- Prüft Stift-Identität via Seriennummer und Sprache (`.tiptoi.log` vs `pen.conf`)
- Filtert Dateien nach Variante (`CH`, `FR`, …) aus der Stift-Konfiguration
- Liest die Product ID (PID) jeder GME-Datei via `tttool` und bettet sie in den Dateinamen ein (`_pid_033`)
- Erkennt und ersetzt ältere Versionen auf dem Stift anhand der PID (nicht nur des Dateinamens)
- Warnt, wenn der Stift bereits eine neuere Version hat, und fragt vor dem Überschreiben nach
- `--pruefe-stift`: scannt alle GME-Dateien auf dem Stift, benennt fehlende PIDs um, löst Konflikte interaktiv
- Sicheres Unmounten nach der Übertragung

### Voraussetzungen

- [`tttool`](https://github.com/entropia/tip-toi-reveng) ≥ 1.11 unter `~/.local/bin/tttool`
- Tiptoi-Stift gemountet unter `/media/$USER/tiptoi`
- `udisksctl` (Teil von `udisks2`, Standard auf Ubuntu/Debian)

### Einrichtung: pen.conf

Eine Datei `pen.conf` im **Root des Stifts** anlegen (z.B. `/media/tintifax/tiptoi/pen.conf`):

```ini
PEN_ID=03
PEN_SERIAL=HS595239
PEN_LANG=GERMAN
PEN_VARIANT=CH
```

| Feld | Beschreibung |
|------|--------------|
| `PEN_ID` | Eindeutige Stift-Nummer – zum Auffinden des lokalen Archiv-Unterordners (`uebertragen_03_*`) |
| `PEN_SERIAL` | Seriennummer aus `.tiptoi.log` Offset 0x00 – verhindert falsche pen.conf auf anderem Stift |
| `PEN_LANG` | Vom Stift erwartete Sprache, konsistent mit tttool (`GERMAN`, `FRENCH`, …) |
| `PEN_VARIANT` | Welche Datei-Variante auf diesen Stift gehört (`CH`, `FR`, …) |

Fehlt `pen.conf`, bietet das Skript an, sie interaktiv anzulegen. Seriennummer und Sprache werden automatisch aus `.tiptoi.log` vorgeschlagen.

### Dateibenennung auf dem Stift

Alle GME-Dateien auf dem Stift erhalten ein PID-Suffix: `<Name>_pid_<XXX>.gme` (3 Stellen, führende Nullen).

Beispiel: `WWW_Flughafen_ch_v30_pid_003.gme`

### Aufruf

```bash
./gme_uebertragen.sh           # passende Dateien übertragen und Stift auswerfen
./gme_uebertragen.sh -k        # übertragen, Stift eingehängt lassen
./gme_uebertragen.sh -p        # Stift prüfen: PIDs umbenennen, Konflikte lösen (kein Transfer)
./gme_uebertragen.sh -h        # Hilfe
```

| Option | Kurz | Beschreibung |
|--------|------|--------------|
| `--pruefe-stift` | `-p` | Stift scannen, Dateien umbenennen, PID-Konflikte lösen |
| `--kein-unmount` | `-k` | Nach der Übertragung NICHT unmounten |
| `--help` | `-h` | Hilfe anzeigen |

### Ablauf

1. Stift-Check – falls nicht gemountet, automatischer Mount-Versuch via `udisksctl`
2. `pen.conf` lesen und prüfen
3. Seriennummer + Sprache aus `.tiptoi.log` lesen und mit `pen.conf` vergleichen
4. Alle GME-Dateien auf dem Stift ohne `_pid_XXX` im Namen umbenennen
5. Passende GME-Dateien in diesem Verzeichnis finden (nach `PEN_VARIANT` im Dateinamen)
6. Pro Datei: PID via `tttool` lesen, `_pid_XXX` in Dateiname einfügen, alte Version auf Stift per PID suchen und löschen, neue Datei kopieren
7. Übertragene Datei in Archiv-Unterordner verschieben (`uebertragen_<PEN_ID>_*/`)
8. Sync und Unmount

### Hinweise zu `.tiptoi.log`

Die Tiptoi-Stift-Firmware schreibt bei jedem Verbinden eine 64-Byte-Binärdatei ins Root. Aufbau (je 16 Bytes, aufgefüllt mit `\x00`/`\xFF`):

| Offset | Inhalt | Bedeutung |
|--------|--------|-----------|
| `0x00` | z.B. `HS595239` | Seriennummer |
| `0x10` | z.B. `5GE008` | Firmware-Version |
| `0x20` | z.B. `GERMAN` | Sprach-Einstellung |
| `0x30` | z.B. `3203L` | Hardware-Revision |
