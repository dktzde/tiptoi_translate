# GME Patcher – Hintergrund & Idee

## Problem: tttool zerstört Spiele beim Reassemble

Wenn ein Tiptoi-Buch mit interaktiven Spielen (Quiz, Rätsel etc.) via tttool
`export` + `assemble` neu gebaut wird, funktionieren die Spiele danach nicht mehr.

**Ursache:** tttool hat beim `export` 8 unbekannte Segmente (4526 Bytes) die nicht
ins YAML geschrieben werden – beim `assemble` fehlen sie:

```
Unknown file segments: 8 (4526 bytes total)
   Offset: 000000D0 to 00000200 (304 bytes)   ← vermutl. Header-Erweiterung
   Offset: 0001066B to 000115F9 (3982 bytes)  ← vermutl. Spiel-Logik
   ...
```

**Bestätigt durch tttool-Autor Joachim Breitner (Mailing-Liste, 26.02.2026):**

> an sich sollte das gehen, zumindest wenn alle Audiodateien wirklich nur
> über ihre Adresse in der Tabelle referenziert werden (oder tatsächlich
> nur kürzere Dateien erlauben).
>
> Das in tttool einzubauen braucht vermutlich ein bisschen refactoring,
> weil man beim Parsen der Datei die Positionen der Audio-Dateien
> festhalten will. Prinzipiell machbar, aber ich bezweifel dass ich bald
> dazu kommen würde.
>
> Hatte nicht jemand mal ein separates Tool dafür geschrieben?
> https://github.com/entropia/tip-toi-reveng/blob/master/libtiptoi.c

## Lösung: Binary-Patch statt YAML-Roundtrip

Statt `export → YAML bearbeiten → assemble` (verliert Spiel-Daten):

**Neuer Ansatz:**
1. Original-GME parsen → Audio-Offset-Tabelle lesen
2. Alle Non-Audio-Segmente (inkl. Spiele, Scripts) unverändert behalten
3. Neue OGG-Dateien einsetzen
4. Offset-Tabelle neu berechnen
5. Neue GME schreiben: Alles außer Audio bleibt bitgenau gleich

## Referenz

- libtiptoi.c: https://github.com/entropia/tip-toi-reveng/blob/master/libtiptoi.c
- tip-toi-reveng Projekt: https://github.com/entropia/tip-toi-reveng
- tttool Quellcode: https://github.com/entropia/tip-toi-reveng (tttool ist Teil des gleichen Repos)

## GME Dateiformat (bekannt)

- Header: Offset-Tabelle die auf Audio-Segmente zeigt
- Audio-Segmente: OGG-Dateien sequenziell gespeichert
- Scripts/Spiele: separate Segmente, von tttool nur teilweise verstanden
- Jede Audio-Datei hat eine ID (Index in der Tabelle) + Offset + Länge

## Nächste Schritte

1. libtiptoi.c analysieren → GME-Format vollständig verstehen
2. Python-Tool `gme_patch.py` bauen:
   - GME parsen (Audio-Tabelle extrahieren)
   - Neue OGGs einsetzen
   - Offsets neu berechnen
   - GME schreiben (Non-Audio-Teile bitgenau kopiert)
