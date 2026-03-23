# GME Patcher – Projekt-Anweisungen für Claude

## Was macht dieses Projekt?

`gme_patch.py` ersetzt Audio-Dateien in Tiptoi-GME-Dateien direkt im Binary –
ohne tttool-Roundtrip (export → YAML → assemble). Das bewahrt alle interaktiven
Spiele, die tttool sonst beim Reassemble verliert.

## Warum kein tttool assemble?

tttool verliert beim `export` + `assemble` 8 unbekannte Segmente (4526 Bytes)
(z.B. Spiel-Logik, Header-Erweiterungen). Diese werden einfach nicht ins YAML
geschrieben und fehlen danach.

**Bestätigt vom tttool-Autor**: Binary-Patch ist der richtige Weg.

## Algorithmus (Kern)

1. Audio-Tabelle parsen: Offset bei 0x0004, jeder Eintrag = (offset, length) × 8 Bytes
2. Eintragsanzahl: `(erster_audio_offset - tabellen_offset) / 8`
3. XOR-Schlüssel bestimmen: findet Wert, sodass erste 4 Bytes = `OggS` oder `RIFF`
4. Alles vor erster Audio-Datei **unverändert** kopieren (Header, Scripts, Spiele)
5. Neue OGGs (XOR-verschlüsselt) sequenziell schreiben
6. Audio-Tabelle + Zusatz-Tabelle (0x0060) mit neuen Offsets aktualisieren
7. Prüfsumme neu berechnen (einfache Byte-Summe, letzte 4 Bytes)

## Regeln für Änderungen

- **Changelog**: Bei jeder Änderung CHANGELOG.md aktualisieren (Version erhöhen)
- **Backup**: Vorgänger-Version in `backup/` ablegen (v1, v2, ...)
- **Tests**: Immer `python gme_patch.py -i original.gme` zur Verifikation laufen lassen
- **Kein tttool** in diesem Ordner – gme_patch.py ist absichtlich eigenständig

## Dateinamen-Konvention (media_dir)

gme_patch.py erkennt automatisch:
- `0000.ogg`, `0001.ogg`, ...           (libtiptoi-Style)
- `Feuerwehr_0000.ogg`, ...             (tttool-Style, mit Präfix)

Letzter numerischer Block im Dateinamen = Index in der Audio-Tabelle.

## Referenzen (lokal verfügbar in tip-toi-reveng/)

- `tip-toi-reveng/GME-Format.md` – vollständige Format-Dokumentation
- `tip-toi-reveng/libtiptoi.c`   – C-Referenzimplementierung (MIT License)
- `tip-toi-reveng/src/GMEParser.hs` + `GMEWriter.hs` – Haskell-Impl. von tttool

## Stack

- Python 3.13, keine externen Abhängigkeiten (nur stdlib: struct, re, sys, pathlib)
- ffmpeg für MP3→OGG Konvertierung (in Hilfsskripten)
