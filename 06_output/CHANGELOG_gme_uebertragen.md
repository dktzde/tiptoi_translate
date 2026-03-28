# Changelog für gme_uebertragen.sh

## 2026-03-28

### Added
- **`--pruefe-stift` Phase 3: Sprachprüfung** (nur wenn `FORCE_LANGUAGE=true`):
  - Prüft alle GME/GMEX-Dateien auf dem Stift via `tttool info` auf vorhandene Sprache.
  - Dateien ohne Sprache: `tttool set-language <PEN_LANG>` wird **automatisch ohne Rückfrage** ausgeführt.
  - `LANG_CHECK=pending` nur wenn `set-language` fehlschlägt (z.B. beschädigte Datei).
  - Ergebnis wird in `pen.conf` gespeichert (nur wenn `FORCE_LANGUAGE=true`):
    - `LANG_CHECK=ok` / `LANG_CHECK=pending`
    - `LANG_ERRORS=N` – Anzahl Dateien, bei denen `set-language` fehlschlug
  - Wenn `LANG_CHECK=ok` bereits in `pen.conf`: Nutzer wird über den Stand informiert und gefragt,
    ob er die Prüfung trotzdem erneut ausführen möchte.

### Fixed
- `FORCE_LANGUAGE` wird jetzt korrekt erkannt wenn der Key in `pen.conf` **fehlt**:
  - Vorher: `FORCE_LANGUAGE="${FORCE_LANGUAGE:-false}"` setzte den Wert still auf `false`,
    bevor der Check lief → Nutzer wurde nie gefragt.
  - Jetzt: `unset FORCE_LANGUAGE` vor `source pen.conf`, dann explizite Prüfung mit
    `[ -z "${FORCE_LANGUAGE+x}" ]` – unterscheidet zwischen *fehlt* und *ungültiger Wert*.
  - Fehlermeldung differenziert: "fehlt in pen.conf" vs. "ungültiger Wert: '...'"

### Backup
- Backup erstellt: `backup/gme_uebertragen_v3.sh`

---

## 2026-03-27

### Added
- Neue Option `FORCE_LANGUAGE` in `pen.conf` (Boolean: `true`/`false`):
  - Wenn `true`: Erzwingt, dass **alle** GME-Dateien die Stift-Sprache (`PEN_LANG`) haben.
  - Prüft die GME-Sprache via `tttool info` und überspringt Dateien mit falscher Sprache.
  - Versucht, fehlende Sprachinformationen via `tttool set-language` zu setzen.
  - Wird interaktiv abgefragt, wenn `pen.conf` neu angelegt wird.
  - Falls `FORCE_LANGUAGE` in `pen.conf` fehlt oder ungültig ist:
    - Das Skript fragt den Nutzer nach dem Wert (`true`/`false`).
    - Die `pen.conf` wird um den neuen Eintrag erweitert oder der bestehende Wert wird aktualisiert.
- **Dry-Run-Modus** (`--dry-run` / `-n`):
  - Simuliert alle Aktionen **ohne Änderungen** (keine Dateien übertragen, `pen.conf` nicht ändern).
  - Nützlich zum Testen oder Debugging (Ausgabe mit `[DRY RUN]` gekennzeichnet).

### Changed
- **Robustere Fehlerbehandlung**:
  - Prüft vorab, ob `tttool` installiert ist (`command -v`).
  - Korrigiert automatisch Schreibrechte für `pen.conf` (`chmod u+w`).
- **Benutzerfreundlichkeit**:
  - **Farben in Ausgaben**: Fehler (rot), Warnungen (gelb), Erfolge (grün) für bessere Lesbarkeit.
  - **Timeout für Eingaben**: Alle `read`-Befehle brechen nach 30 Sekunden ab (verhindert Hängen).

### Changed
- `FORCE_LANGUAGE` wird nun als Boolean (`true`/`false`) behandelt (nicht als Sprachcode).
- Sprachprüfung: Bei `FORCE_LANGUAGE=true` wird die GME-Sprache strikt erzwungen.
- Ausgabe der `pen.conf`-Informationen zeigt den aktuellen `FORCE_LANGUAGE`-Wert an.

### Backup
- Backup erstellt: `gme_uebertragen.sh.backup_20260327_203311`

### Notes
- **Wichtig für Stift 2**: Dieser unterstützt nur Französisch, hat aber keine Sprachprüfung in `.tiptoi.log`.
  Setze `FORCE_LANGUAGE=true` und `PEN_LANG=FRENCH`, um sicherzustellen, dass nur französische GME-Dateien übertragen werden.
- Beispiel:
  ```
  FORCE_LANGUAGE=true
  PEN_LANG=FRENCH
  ```
  → Nur GME-Dateien mit `Language: FRENCH` werden übertragen. Fehlende Sprachinformationen werden automatisch gesetzt.
