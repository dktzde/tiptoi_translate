#!/usr/bin/env bash
# gme_uebertragen.sh – GME-Dateien auf Tiptoi-Stift übertragen
#
# Optionen:
#   -k / --kein-unmount   Stift nach der Übertragung NICHT auswerfen
#   -p / --pruefe-stift   PIDs scannen, Dateien umbenennen, Konflikte lösen (kein Transfer)
#   -h / --help           Hilfe anzeigen

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MOUNTPOINT="/media/dom/tiptoi"
TTTOOL="${HOME}/.local/bin/tttool"
KEIN_UNMOUNT=0
PRUEFE_STIFT=0

# PIDs die mehrfach auf dem Stift vorkommen dürfen (tiptoi-global, kein Konflikt)
SHARED_PIDS="53"

for ARG in "$@"; do
    case "$ARG" in
        --kein-unmount|-k) KEIN_UNMOUNT=1 ;;
        --pruefe-stift|-p) PRUEFE_STIFT=1 ;;
        --help|-h)
            echo "Verwendung: $(basename "$0") [OPTIONEN]"
            echo ""
            echo "Überträgt passende GME-Dateien aus diesem Verzeichnis auf den Tiptoi-Stift."
            echo "Liest Stift-Konfiguration aus /media/dom/tiptoi/pen.conf."
            echo ""
            echo "Optionen:"
            echo "  --pruefe-stift / -p   PIDs aller GME-Dateien auf dem Stift prüfen:"
            echo "                        - Dateien ohne _pid_XXX im Namen werden umbenannt"
            echo "                        - PID-Konflikte werden interaktiv aufgelöst"
            echo "                        - kein Transfer, kein Unmount"
            echo "  --kein-unmount / -k   Stift nach der Übertragung NICHT auswerfen"
            echo "  --help / -h           Diese Hilfe anzeigen"
            echo ""
            echo "Dateiformat auf Stift: <Name>_pid_XXX.gme  (XXX = 3-stellig, z.B. _pid_033)"
            echo "Shared PIDs (kein Konflikt): $SHARED_PIDS"
            exit 0
            ;;
        *) echo "Unbekannte Option: $ARG (--help für Hilfe)"; exit 1 ;;
    esac
done

# ════════════════════════════════════════════════════════
# Hilfsfunktionen
# ════════════════════════════════════════════════════════

# PID aus Dateiname lesen – Format _pid_033 – gibt Zahl zurück (keine führenden Nullen)
pid_from_name() {
    local name; name=$(basename "$1")
    local raw
    raw=$(echo "$name" | sed -n 's/.*_pid_\([0-9][0-9]*\)\.\(gme\|gmex\)$/\1/p')
    [ -n "$raw" ] && printf '%d' "$((10#$raw))" || true
}

# PID via tttool lesen
pid_from_tttool() {
    "$TTTOOL" info "$1" 2>/dev/null | grep "^Product ID:" | awk '{print $3}' || true
}

# Dateiname mit _pid_XXX versehen
name_with_pid() {
    local file="$1" pid="$2"
    local dir; dir=$(dirname "$file")
    local base; base=$(basename "$file")
    local ext="${base##*.}"
    local stem="${base%.*}"
    # _pid_XXX-Suffix entfernen falls vorhanden
    stem=$(echo "$stem" | sed -E 's/_pid_[0-9]+$//')
    echo "${dir}/${stem}_pid_$(printf '%03d' "$((10#$pid))").${ext}"
}

# Versionsnummer aus Dateiname lesen (_vXXX), gibt Zahl zurück oder 0
version_from_name() {
    local name; name=$(basename "$1")
    local raw
    raw=$(echo "$name" | sed -n 's/.*_v\([0-9][0-9]*\)[._].*/\1/p' | head -1)
    [ -n "$raw" ] && printf '%d' "$((10#$raw))" || echo "0"
}

# Ist eine PID in der Shared-Liste?
is_shared_pid() {
    case ",$SHARED_PIDS," in *",$1,"*) return 0 ;; esac
    return 1
}

# Alle GME/GMEX auf dem Stift ohne _pid_XXX im Namen umbenennen (still, kein Dialog)
rename_pids_on_pen() {
    local f base pid newpath count=0
    while IFS= read -r -d '' f; do
        base=$(basename "$f")
        # Bereits im neuen Format (_pid_XXX mit genau 3 Stellen)?
        if echo "$base" | grep -qE '_pid_[0-9]{3}\.(gme|gmex)$'; then
            continue
        fi
        # _pid_XXX fehlt → PID via tttool lesen
        pid=$(pid_from_name "$base")
        if [ -z "$pid" ]; then
            pid=$(pid_from_tttool "$f")
        fi
        if [ -z "$pid" ]; then
            echo "  WARNUNG: PID nicht lesbar, übersprungen: $base"
            continue
        fi
        newpath=$(name_with_pid "$f" "$pid")
        mv "$f" "$newpath"
        echo "  Umbenannt: $base → $(basename "$newpath")"
        count=$((count + 1))
    done < <(find "$MOUNTPOINT" -maxdepth 1 \( -name "*.gme" -o -name "*.gmex" \) -print0)
    [ "$count" -gt 0 ] && echo "  $count Datei(en) umbenannt." || true
}

# Alle GME/GMEX auf dem Stift mit einer bestimmten PID finden
find_by_pid_on_pen() {
    local target_pid="$1"
    local f base fpid
    while IFS= read -r -d '' f; do
        base=$(basename "$f")
        fpid=$(pid_from_name "$base")
        [ -z "$fpid" ] && fpid=$(pid_from_tttool "$f")
        [ "$fpid" = "$target_pid" ] && echo "$f"
    done < <(find "$MOUNTPOINT" -maxdepth 1 \( -name "*.gme" -o -name "*.gmex" \) -print0)
}

# ════════════════════════════════════════════════════════
# 1. Stift-Check (mit automatischem Mount-Versuch)
# ════════════════════════════════════════════════════════
if ! findmnt "$MOUNTPOINT" > /dev/null 2>&1; then
    echo "Stift nicht gemountet – versuche zu mounten ..."
    DEV=$(blkid -L tiptoi 2>/dev/null | head -1 || true)
    [ -z "$DEV" ] && [ -b /dev/sdc ] && DEV=/dev/sdc
    if [ -z "$DEV" ]; then
        echo "Kein Tiptoi-Gerät gefunden. Bitte Stift einschalten und verbinden."
        exit 1
    fi
    if ! udisksctl mount -b "$DEV" > /dev/null 2>&1; then
        echo "Mount fehlgeschlagen ($DEV). Bitte Stift prüfen (Einschalten?)."
        exit 1
    fi
    if ! findmnt "$MOUNTPOINT" > /dev/null 2>&1; then
        echo "Stift nicht verbunden, bitte prüfen (Einschalten)."
        exit 1
    fi
    echo "Stift gemountet."
fi
DEVICE=$(findmnt -n -o SOURCE "$MOUNTPOINT")
echo "Stift erkannt: $DEVICE → $MOUNTPOINT"

# ════════════════════════════════════════════════════════
# 2. pen.conf lesen (oder neu anlegen)
# ════════════════════════════════════════════════════════
PEN_CONF="$MOUNTPOINT/pen.conf"
if [ ! -f "$PEN_CONF" ]; then
    echo "pen.conf nicht gefunden."
    read -r -p "Soll sie jetzt angelegt werden? [j/n]: " ANS
    if [[ ! "$ANS" =~ ^[jJyY]$ ]]; then
        echo "Abbruch."
        exit 1
    fi
    echo ""

    # Seriennummer und Sprache aus .tiptoi.log vorschlagen
    _LOG="$MOUNTPOINT/.tiptoi.log"
    _SUGGEST_SERIAL=""
    _SUGGEST_LANG=""
    if [ -f "$_LOG" ]; then
        _SUGGEST_SERIAL=$(dd if="$_LOG" bs=1 count=16 skip=0  2>/dev/null | tr -cd '[:print:]')
        _SUGGEST_LANG=$(  dd if="$_LOG" bs=1 count=16 skip=32 2>/dev/null | tr -cd '[:print:]')
    fi

    read -r -p "PEN_ID (z.B. 03): " PEN_ID

    if [ -n "$_SUGGEST_SERIAL" ]; then
        read -r -p "PEN_SERIAL [$_SUGGEST_SERIAL]: " PEN_SERIAL
        PEN_SERIAL="${PEN_SERIAL:-$_SUGGEST_SERIAL}"
    else
        read -r -p "PEN_SERIAL: " PEN_SERIAL
    fi

    if [ -n "$_SUGGEST_LANG" ]; then
        read -r -p "PEN_LANG [$_SUGGEST_LANG]: " PEN_LANG
        PEN_LANG="${PEN_LANG:-$_SUGGEST_LANG}"
    else
        read -r -p "PEN_LANG (z.B. GERMAN, FRENCH): " PEN_LANG
    fi

    read -r -p "PEN_VARIANT (z.B. CH, FR): " PEN_VARIANT

    if [ -z "$PEN_ID" ] || [ -z "$PEN_SERIAL" ] || [ -z "$PEN_LANG" ] || [ -z "$PEN_VARIANT" ]; then
        echo "FEHLER: Alle Felder müssen ausgefüllt sein."
        exit 1
    fi

    printf 'PEN_ID=%s\nPEN_SERIAL=%s\nPEN_LANG=%s\nPEN_VARIANT=%s\n' \
        "$PEN_ID" "$PEN_SERIAL" "$PEN_LANG" "$PEN_VARIANT" > "$PEN_CONF"
    echo ""
    echo "pen.conf angelegt: $PEN_CONF"
else
    # shellcheck source=/dev/null
    source "$PEN_CONF"
    if [ -z "${PEN_ID:-}" ] || [ -z "${PEN_SERIAL:-}" ] || [ -z "${PEN_LANG:-}" ] || [ -z "${PEN_VARIANT:-}" ]; then
        echo "FEHLER: pen.conf unvollständig (PEN_ID, PEN_SERIAL, PEN_LANG, PEN_VARIANT erforderlich)"
        exit 1
    fi
fi
echo "pen.conf:    PEN_ID=$PEN_ID  PEN_SERIAL=$PEN_SERIAL  PEN_LANG=$PEN_LANG  PEN_VARIANT=$PEN_VARIANT"

# ════════════════════════════════════════════════════════
# 3. .tiptoi.log prüfen (Seriennummer + Sprache)
# ════════════════════════════════════════════════════════
LOG_FILE="$MOUNTPOINT/.tiptoi.log"
if [ ! -f "$LOG_FILE" ]; then
    echo "FEHLER: .tiptoi.log nicht gefunden."
    exit 1
fi
LOG_SERIAL=$(dd if="$LOG_FILE" bs=1 count=16 skip=0  2>/dev/null | tr -cd '[:print:]')
LOG_LANG=$(  dd if="$LOG_FILE" bs=1 count=16 skip=32 2>/dev/null | tr -cd '[:print:]')
echo ".tiptoi.log: serial=$LOG_SERIAL  lang=$LOG_LANG"

if [ "$LOG_SERIAL" != "$PEN_SERIAL" ]; then
    echo "FEHLER: Seriennummer stimmt nicht überein!"
    echo "  pen.conf: $PEN_SERIAL  /  .tiptoi.log: $LOG_SERIAL"
    echo "  Falsche pen.conf auf diesem Stift? Abbruch."
    exit 1
fi
if [ "$LOG_LANG" != "$PEN_LANG" ]; then
    echo "FEHLER: Sprache stimmt nicht überein!"
    echo "  pen.conf: $PEN_LANG  /  .tiptoi.log: $LOG_LANG"
    exit 1
fi
echo "Stift verifiziert: Seriennummer und Sprache OK."
echo ""

# ════════════════════════════════════════════════════════
# --pruefe-stift  (kein Transfer, kein Unmount danach)
# ════════════════════════════════════════════════════════
if [ "$PRUEFE_STIFT" -eq 1 ]; then
    echo "════════════════════════════════════════════════════════"
    echo "Stift-Prüfung gestartet"
    echo ""

    # ── Phase 1: Umbenennen ───────────────────────────────────────────────────
    echo "Phase 1: Dateien auf neues PID-Format prüfen (_pid_XXX) ..."
    rename_pids_on_pen
    echo ""

    # ── Phase 2: Konflikte erkennen ──────────────────────────────────────────
    echo "Phase 2: PID-Konflikte erkennen ..."

    declare -A PID_MAP
    while IFS= read -r -d '' FILE; do
        BASE=$(basename "$FILE")
        PID=$(pid_from_name "$BASE")
        [ -z "$PID" ] && continue
        is_shared_pid "$PID" && continue
        if [ -n "${PID_MAP[$PID]+x}" ]; then
            PID_MAP[$PID]="${PID_MAP[$PID]}"$'\n'"$FILE"
        else
            PID_MAP[$PID]="$FILE"
        fi
    done < <(find "$MOUNTPOINT" -maxdepth 1 \( -name "*.gme" -o -name "*.gmex" \) -print0)

    CONFLICTS=0
    for PID in $(echo "${!PID_MAP[@]}" | tr ' ' '\n' | sort -n); do
        mapfile -t FILES <<< "${PID_MAP[$PID]}"
        [ "${#FILES[@]}" -le 1 ] && continue
        CONFLICTS=$((CONFLICTS + 1))

        echo ""
        echo "  KONFLIKT PID $PID (${#FILES[@]} Dateien):"
        echo ""

        echo "  Welche Datei soll gelöscht werden?"
        echo ""
        for i in "${!FILES[@]}"; do
            echo "    [$(( i + 1 ))] $(basename "${FILES[$i]}")"
        done
        echo "    [0] Keine – Konflikt behalten"
        echo ""

        CHOICE=""
        while true; do
            read -r -p "  Löschen [1-${#FILES[@]}/0]: " CHOICE
            if [ "$CHOICE" = "0" ]; then
                echo "  Konflikt behalten."
                break
            fi
            if [[ "$CHOICE" =~ ^[0-9]+$ ]] && [ "$CHOICE" -ge 1 ] && [ "$CHOICE" -le "${#FILES[@]}" ]; then
                IDX=$(( CHOICE - 1 ))
                rm "${FILES[$IDX]}"
                echo "  Gelöscht: $(basename "${FILES[$IDX]}")"
                break
            fi
            echo "  Ungültige Eingabe, bitte erneut."
        done
    done

    if [ "$CONFLICTS" -eq 0 ]; then
        echo "  Keine Konflikte gefunden."
    fi
    echo ""
    echo "════════════════════════════════════════════════════════"
    echo "Stift-Prüfung abgeschlossen. Kein Transfer, kein Unmount."
    read -r -s -n1 -p "Taste drücken zum Beenden ..." < /dev/tty
    echo ""
    exit 0
fi

# ════════════════════════════════════════════════════════
# 4. Stift: alle GME auf neues PID-Format bringen
# ════════════════════════════════════════════════════════
echo "Prüfe PID-Benennung auf Stift ..."
rename_pids_on_pen
echo ""

# ════════════════════════════════════════════════════════
# 5. Zielordner suchen oder anlegen
# ════════════════════════════════════════════════════════
VARIANT_LOWER=$(echo "$PEN_VARIANT" | tr '[:upper:]' '[:lower:]')
# Aliases: vo (Vogtländisch), by (Bayrisch), nd (Plattdeutsch) → alle auf CH-Stift
case "$VARIANT_LOWER" in
    ch) SEARCH_VARIANTS=("ch" "vo" "by" "nd") ;;
    *)  SEARCH_VARIANTS=("$VARIANT_LOWER") ;;
esac
TARGET_DIR=$(find "$SCRIPT_DIR" -maxdepth 1 -type d -name "uebertragen_${PEN_ID}_*" | head -1)
if [ -z "$TARGET_DIR" ]; then
    TARGET_DIR="${SCRIPT_DIR}/uebertragen_${PEN_ID}_${PEN_VARIANT}"
    mkdir -p "$TARGET_DIR"
    echo "Unterordner angelegt: $(basename "$TARGET_DIR")"
else
    echo "Unterordner gefunden: $(basename "$TARGET_DIR")"
fi

# ════════════════════════════════════════════════════════
# 6. GME-Kandidaten finden
# ════════════════════════════════════════════════════════
echo ""
echo "Suche nach GME-Dateien für Variante $PEN_VARIANT (${SEARCH_VARIANTS[*]}) ..."
CANDIDATES=()
for V in "${SEARCH_VARIANTS[@]}"; do
    while IFS= read -r f; do
        CANDIDATES+=("$f")
    done < <(find "$SCRIPT_DIR" -maxdepth 1 -name "*_${V}_*.gme" -type f | sort)
done
mapfile -t CANDIDATES < <(printf '%s\n' "${CANDIDATES[@]}" | sort -u)

if [ "${#CANDIDATES[@]}" -eq 0 ]; then
    echo "Keine passenden GME-Dateien gefunden (Variante: $PEN_VARIANT)."
else
    echo "Gefunden: ${#CANDIDATES[@]} Datei(en)"
    echo ""

    TRANSFERRED=()
    WARNINGS=()

    for FILE in "${CANDIDATES[@]}"; do
        BASENAME=$(basename "$FILE")
        echo "── $BASENAME"

        # ── Sprachcheck ──────────────────────────────────────────────────────
        LANG_INFO=$("$TTTOOL" info "$FILE" 2>/dev/null | grep -i "^Language:" | awk '{print $2}' || true)
        if [ -n "$LANG_INFO" ] && [ "$LANG_INFO" != "$PEN_LANG" ]; then
            echo "   ÜBERSPRUNGEN: Sprache '$LANG_INFO' passt nicht zu Stift ($PEN_LANG)"
            WARNINGS+=("$BASENAME: falsche Sprache ($LANG_INFO statt $PEN_LANG)")
            continue
        fi

        # ── PID auslesen und _pid_XXX in Dateinamen einfügen ─────────────────
        PID=$(pid_from_name "$BASENAME")
        [ -z "$PID" ] && PID=$(pid_from_tttool "$FILE")
        if [ -z "$PID" ]; then
            echo "   WARNUNG: PID nicht lesbar – Datei übersprungen."
            WARNINGS+=("$BASENAME: PID nicht lesbar")
            continue
        fi
        echo "   PID: $PID"

        NEW_FILE=$(name_with_pid "$FILE" "$PID")
        NEW_BASENAME=$(basename "$NEW_FILE")
        if [ "$FILE" != "$NEW_FILE" ]; then
            mv "$FILE" "$NEW_FILE"
            echo "   Umbenannt: $NEW_BASENAME"
            FILE="$NEW_FILE"
            BASENAME="$NEW_BASENAME"
        fi

        # ── Alte Version(en) auf Stift per PID suchen und löschen ────────────
        OLD_DELETED=0
        while IFS= read -r OLD_PATH; do
            [ -z "$OLD_PATH" ] && continue
            OLD_VER=$(version_from_name "$OLD_PATH")
            NEW_VER=$(version_from_name "$BASENAME")
            if [ "$OLD_VER" -gt 0 ] && [ "$NEW_VER" -gt 0 ] && [ "$OLD_VER" -gt "$NEW_VER" ]; then
                echo "   ACHTUNG: Stift hat v${OLD_VER}, zu übertragen ist v${NEW_VER}."
                read -r -p "   Trotzdem übertragen? [j/n]: " ANS < /dev/tty
                if [[ ! "$ANS" =~ ^[jJyY]$ ]]; then
                    echo "   Übersprungen."
                    WARNINGS+=("$BASENAME: übersprungen (Stift hat neuere Version v${OLD_VER})")
                    continue 2
                fi
            fi
            rm "$OLD_PATH"
            echo "   Alte Version gelöscht: $(basename "$OLD_PATH")"
            OLD_DELETED=1
        done < <(find_by_pid_on_pen "$PID")
        if [ "$OLD_DELETED" -eq 0 ]; then
            echo "   WARNUNG: Keine alte Version auf Stift gefunden (neue Datei)."
            WARNINGS+=("$BASENAME: keine alte Version gelöscht (neue Datei)")
        fi

        # ── Übertragen ────────────────────────────────────────────────────────
        cp "$FILE" "$MOUNTPOINT/$BASENAME"
        echo "   Übertragen auf Stift."

        # ── In Unterordner verschieben ────────────────────────────────────────
        mv "$FILE" "$TARGET_DIR/$BASENAME"
        echo "   Verschoben nach: $(basename "$TARGET_DIR")/"

        TRANSFERRED+=("$BASENAME")
    done

    # ── Zusammenfassung ───────────────────────────────────────────────────────
    echo ""
    echo "════════════════════════════════════════════════════════"
    if [ "${#TRANSFERRED[@]}" -gt 0 ]; then
        echo "Übertragen: ${#TRANSFERRED[@]} Datei(en)"
        for F in "${TRANSFERRED[@]}"; do
            echo "  OK  $F"
        done
    else
        echo "Keine Dateien übertragen."
    fi

    if [ "${#WARNINGS[@]}" -gt 0 ]; then
        echo ""
        echo "Warnungen:"
        for W in "${WARNINGS[@]}"; do
            echo "  !!  $W"
        done
    fi
fi

# ════════════════════════════════════════════════════════
# Unmount
# ════════════════════════════════════════════════════════
echo ""
sync
if [ "$KEIN_UNMOUNT" -eq 1 ]; then
    echo "Stift bleibt eingehängt (--kein-unmount)."
elif udisksctl unmount -b "$DEVICE" 2>/dev/null; then
    echo "Stift sicher ausgeworfen ($DEVICE)."
else
    echo "HINWEIS: Unmount fehlgeschlagen – bitte manuell auswerfen."
fi

read -r -s -n1 -p "Taste drücken zum Beenden ..." < /dev/tty
echo ""
